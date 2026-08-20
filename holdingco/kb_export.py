#!/usr/bin/env python3
"""Vault-LD KB export + load runner (Phase 3, HC-1732).

Projects the KB/Wiki vault to RDF with the reference exporter, computes
observability metrics, writes a lint report, and (idempotently) loads the
graph into the Oxigraph SPARQL store.

Run by LaunchAgent com.holdingco.vault-ld-export (daily 09:20, after wiki-lint).
Config via env with sane defaults:

  VAULT      vault root scanned by the exporter   (…/KB/Wiki/wiki)
  ONTOLOGY   hand-authored schema graph           (fork holdingco/hco-ontology.ttl)
  OUTDIR     where artifacts are written          (~/Docker/vault-ld-graph/data)
  VLD_REPO   vault-ld checkout (for scripts/)      (~/github/vault-ld)
  PYBIN      python with rdflib+pyyaml             (stack venv)
  OX_CONTAINER  Oxigraph container name, "" to skip   (vault-ld-oxigraph)

The graph is loaded through a short-lived sidecar that shares the store's
network namespace (`docker run --network container:<name>`), so the load does
NOT depend on host->VM port forwarding (which is wedged under HC-1707). The
query surface is reachable in-VM (and via Traefik); host exposure waits on
HC-1707.
"""
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
VAULT = Path(os.environ.get("VAULT", HOME / "Documents/00-HoldingCompany/KB/Wiki/wiki"))
VLD_REPO = Path(os.environ.get("VLD_REPO", HOME / "github/vault-ld"))
ONTOLOGY = Path(os.environ.get("ONTOLOGY", VLD_REPO / "holdingco/hco-ontology.ttl"))
OUTDIR = Path(os.environ.get("OUTDIR", HOME / "Docker/vault-ld-graph/data"))
PYBIN = os.environ.get("PYBIN", str(HOME / "Docker/vault-ld-graph/venv/bin/python"))
OX_CONTAINER = os.environ.get("OX_CONTAINER", "vault-ld-oxigraph")
ONTO_GRAPH = "https://kb.holdingco.com/graph/ontology"

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def run_export() -> str:
    """Run the reference exporter; return its stderr (warnings)."""
    OUTDIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [PYBIN, str(VLD_REPO / "scripts/vault_to_rdf.py"), str(VAULT),
         "--out-dir", str(OUTDIR)],
        capture_output=True, text=True,
    )
    print(proc.stdout.strip())
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"exporter failed (exit {proc.returncode})")
    return proc.stderr


def categorize(warnings: str) -> dict:
    cats = Counter()
    for line in warnings.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        if "not in context" in line:
            cats["unmapped_predicate"] += 1
        elif "dangling wiki link" in line:
            cats["dangling_link"] += 1
        elif "mint the same IRI" in line:
            cats["subject_merge"] += 1
        elif "ambiguous note name" in line:
            cats["ambiguous_name"] += 1
        elif "is not absolute" in line:
            cats["id_not_absolute"] += 1
        else:
            cats["other"] += 1
    return dict(cats)


def graph_metrics():
    from rdflib import Graph
    g = Graph()
    g.parse(OUTDIR / "data.ttl", format="turtle")
    onto = Graph()
    if ONTOLOGY.exists():
        onto.parse(ONTOLOGY, format="turtle")
    subjects = set(g.subjects())
    classes = Counter(str(o) for s, p, o in g if str(p) == RDF_TYPE)
    # orphan = a typed subject with no inbound hco:related edge
    related_p = "https://kb.holdingco.com/vocab#related"
    linked_to = {str(o) for s, p, o in g if str(p) == related_p}
    typed = {str(s) for s, p, o in g if str(p) == RDF_TYPE}
    orphans = sorted(typed - linked_to)
    return {
        "instance_triples": len(g),
        "ontology_triples": len(onto),
        "distinct_subjects": len(subjects),
        "class_counts": {k.rsplit("/", 1)[-1]: v for k, v in classes.most_common()},
        "orphan_notes": len(orphans),
    }, g, onto


def _sidecar_put(local_file: str, mount_spec: str, target: str) -> str:
    """PUT a Turtle file into the store via a curl sidecar that shares the
    store's netns — independent of host->VM port forwarding (HC-1707)."""
    r = subprocess.run(
        ["docker", "run", "--rm", "--network", f"container:{OX_CONTAINER}",
         "-v", mount_spec, "curlimages/curl:latest", "-sS",
         "-o", "/dev/null", "-w", "%{http_code}",
         "-X", "PUT", "--data-binary", f"@{local_file}",
         "-H", "Content-Type: text/turtle", target],
        capture_output=True, text=True, timeout=120,
    )
    return (r.stdout or r.stderr).strip()


def load_oxigraph() -> str:
    if not OX_CONTAINER:
        return "skipped (no OX_CONTAINER)"
    try:
        c1 = _sidecar_put("/in/data.ttl", f"{OUTDIR}:/in:ro",
                          "http://localhost:7878/store?default")
        c2 = _sidecar_put(f"/onto/{ONTOLOGY.name}", f"{ONTOLOGY.parent}:/onto:ro",
                          "http://localhost:7878/store?graph="
                          + urllib.parse.quote(ONTO_GRAPH, safe=""))
        ok = c1 in ("200", "201", "204") and c2 in ("200", "201", "204")
        return f"loaded (data={c1}, ontology={c2})" if ok else \
               f"load incomplete (data={c1}, ontology={c2})"
    except Exception as e:  # noqa: BLE001 — report, don't abort the metrics write
        return f"load failed: {e.__class__.__name__}: {e}"


def write_lint_report(cats: dict, metrics: dict, load_status: str, stamp: str):
    total = sum(cats.values())
    lines = [
        "# Vault-LD KB export — lint & metrics report",
        "",
        f"_Generated {stamp} · vault `{VAULT}`_",
        "",
        "## Graph",
        f"- instance triples: **{metrics['instance_triples']}**",
        f"- ontology triples: {metrics['ontology_triples']}",
        f"- distinct subjects: **{metrics['distinct_subjects']}**",
        f"- orphan notes (no inbound `related`): {metrics['orphan_notes']}",
        "",
        "### Class distribution",
    ]
    for k, v in metrics["class_counts"].items():
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Warnings", f"- total: **{total}**"]
    for k, v in sorted(cats.items(), key=lambda x: -x[1]):
        flag = " ⚠️" if k == "unmapped_predicate" and v else ""
        lines.append(f"- {k}: {v}{flag}")
    lines += ["", f"## Load\n- Oxigraph: {load_status}", ""]
    (OUTDIR / "lint-report.md").write_text("\n".join(lines))


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    warnings = run_export()
    cats = categorize(warnings)
    metrics, _g, _onto = graph_metrics()
    load_status = load_oxigraph()

    payload = {
        "generated": stamp,
        "vault": str(VAULT),
        "metrics": metrics,
        "warnings": cats,
        "warnings_total": sum(cats.values()),
        "oxigraph": load_status,
    }
    (OUTDIR / "metrics.json").write_text(json.dumps(payload, indent=2))
    write_lint_report(cats, metrics, load_status, stamp)

    unmapped = cats.get("unmapped_predicate", 0)
    print(f"subjects={metrics['distinct_subjects']} "
          f"triples={metrics['instance_triples']} "
          f"unmapped={unmapped} warnings={sum(cats.values())} "
          f"oxigraph={load_status}")
    # Non-zero exit iff a mapping regression appears — the one thing that must page.
    return 1 if unmapped else 0


if __name__ == "__main__":
    raise SystemExit(main())
