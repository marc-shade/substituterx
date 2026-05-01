# 03 — PrimeKG + QKG repo research

*Source: research fork, 2026-05-01.*

## A. PrimeKG (Harvard, mims-harvard/PrimeKG) — VERIFIED

**Source:**
- Project: https://zitniklab.hms.harvard.edu/projects/PrimeKG/
- Repo (MIT): https://github.com/mims-harvard/PrimeKG
- Dataverse DOI: https://doi.org/10.7910/DVN/IXA7BM
- Direct CSV: `wget -O kg.csv https://dataverse.harvard.edu/api/access/datafile/6180620`
- Citation: Chandak, Huang, Zitnik. *Building a knowledge graph to enable precision medicine.* Scientific Data, 2023. https://www.nature.com/articles/s41597-023-01960-3
- License: code MIT; dataset CC0-equivalent via Dataverse — verify before redistribution.

**Schema:**
- ~129K nodes across 10 types: `disease`, `drug`, `gene/protein`, `anatomy`, `biological_process`, `molecular_function`, `cellular_component`, `pathway`, `phenotype`, `exposure`.
- ~4.05M edges across 29 relation types. Drug-relevant relations:
  - `drug_indication`, `drug_contraindication`, `drug_off-label_use` (DrugBank + DrugCentral)
  - `drug_drug` (interactions)
  - `drug_protein` (target/transporter/enzyme/carrier — sub-typed via `display_relation`)
  - `drug_effect` (side effects, SIDER)
  - `disease_phenotype_positive/_negative` (HPO)
- CSV columns: `relation, display_relation, x_id, x_type, x_name, x_source, y_id, y_type, y_name, y_source`.
- **Drug nodes keyed to DrugBank IDs.** RxNorm→DrugBank crosswalk is non-trivial — expect manual/UMLS mapping for the prototype subset.
- Companion files: drug feature files (DrugBank parsing, ~12 files) and `dc_features.csv` (DrugCentral) — useful free-text source for `constraint_items` generation.

**Loading + diabetes subset:**
```python
import pandas as pd
kg = pd.read_csv("kg.csv", low_memory=False)

dd = kg[kg["relation"].isin(
    ["drug_indication", "drug_contraindication", "drug_off-label_use"]
)]

seeds = kg[(kg["x_type"]=="disease") & kg["x_name"].str.contains("diabetes", case=False, na=False)]
seed_ids = set(seeds["x_id"]) | set(seeds["y_id"])
sub = kg[kg["x_id"].isin(seed_ids) | kg["y_id"].isin(seed_ids)]
```

For storage: DuckDB direct on CSV (`duckdb.sql("SELECT * FROM 'kg.csv' WHERE …")`) avoids loading 1–2 GB into RAM. NetworkX OK for diabetes subgraph (≤~100K edges). Kùzu or Neo4j desktop for triple-store at scale. Alternative loader: `pykeen.datasets.PrimeKG`.

## B. QKG paper repo — **NOT FOUND**

Three searches:
1. WebSearch `"quantum knowledge graph" "context-dependent" triplet validity github 2026` — no match.
2. arXiv 2604/2605 with title — no hit.
3. GitHub UI search — 0 results.

Video host claimed repo exists but did not show URL, and no author handle was named. **Per Never-Fabricate rule, stopping rather than guessing.**

**Adjacent useful work:**
- arXiv 2604.04190 *Schema-Aware Planning and Hybrid Knowledge Toolset for Reliable KG Triple Verification* — directly relevant to validator/auditor pattern.
- arXiv 2604.10384 *Context-KG* — context-aware KG visualization.
- LMU/Siemens *Quantum ML on Knowledge Graphs* (Ma, Tresp) — canonical quantum-embedding-on-KG reference.

**Decision:** build validator against the paper's *described* architecture (reasoner / context-extractor / KG-validator / parametric-leakage auditor) using PrimeKG diabetes-cardiac subgraph + LLM-generated `constraint_items` per edge. Do not block on locating the repo.
