# HoldingCo KB integration

Fork-local additions for integrating Vault-LD with the HoldingCo KB/Wiki vault
(`~/Documents/00-HoldingCompany/KB/Wiki/`). Tracked in Linear project
**Vault-LD / KB Semantic Layer** (HC-1730..1734).

- `probe-context.jsonld` — throwaway Phase-1 benchmark context mapping current
  KB frontmatter (`title→rdfs:label`, `sources→sdo:citation`,
  `related→hco:related`, dates→xsd:date). Superseded by the durable
  `KB/Wiki/context.jsonld` authored in Phase 2 (HC-1731). Do not treat as canonical.

Remotes: `origin` = The-Holding-Company/vault-ld (our fork); `upstream` push disabled.
