# HoldingCo KB integration

Fork-local additions for integrating Vault-LD with the HoldingCo KB/Wiki vault
(`~/Documents/00-HoldingCompany/KB/Wiki/wiki/`). Tracked in Linear project
**Vault-LD / KB Semantic Layer** (HC-1730..1734).

## Files

- `kb-wiki-context.jsonld` — **durable** root `@context` for the KB/Wiki vault
  (Phase 2, HC-1731). The canonical copy lives in the vault at
  `KB/Wiki/wiki/context.jsonld`; this is a tracked mirror. Maps all 11
  frontmatter keys → 0 unmapped predicates; bare `type:` values expand against
  `@base` into five classes. Authors keep writing `type: concept`.
- `hco-ontology.ttl` — **minimal HoldingCo ontology** (Phase 2, HC-1731): the
  hand-authored schema graph (5 classes, 7 properties) that backs the exporter's
  instance graph. Load alongside `data.ttl` for validation / reasoning / SPARQL.

## Namespaces

| Prefix | IRI | Holds |
|---|---|---|
| `kb:`  | `https://kb.holdingco.com/`        | note subjects **and** `type:` classes |
| `hco:` | `https://kb.holdingco.com/vocab#`   | properties (predicates) |

## Reproduce

```sh
python3 -m venv venv && venv/bin/pip install -r scripts/requirements.txt
venv/bin/python scripts/vault_to_rdf.py \
  ~/Documents/00-HoldingCompany/KB/Wiki/wiki --out-dir build
# -> build/data.ttl (instances) ; load with holdingco/hco-ontology.ttl
```

Remotes: `origin` = The-Holding-Company/vault-ld (our fork); `upstream` push disabled.
