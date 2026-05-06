# ArchiSurance Claims Processing — Synthetic Demo Dataset

A self-contained, multi-layer dataset for the KnowledgeForge demo,
themed after **The Open Group ArchiSurance reference architecture**. All
content here is original, Apache-2.0-licensed, and authored for this
repository; no Open Group figures or copyrighted material are
redistributed.

## What's inside

```
archisurance/
├── architecture/        # 4 markdown docs (Business / App / Tech / Data)
├── code/                # Python services (claims_api, claims_worker, fraud_scorer)
├── sql/schema.sql       # 7-table Postgres DDL with explicit FKs
└── dbt/                 # dbt project: 4 staging views + 3 marts
```

The dataset is a single coherent slice of an insurance-claims subsystem,
designed so that the resulting knowledge graph spans multiple ArchiMate
layers:

- **Business layer** — actors, processes, services, business objects
  (described in `architecture/01-business-architecture.md`).
- **Application layer** — components, services, interfaces (described in
  `architecture/02-application-architecture.md` and implemented as Python
  modules under `code/`).
- **Technology layer** — GKE/CloudSQL/BigQuery nodes and the Pub/Sub
  bus (`architecture/03-technology-architecture.md`).
- **Data layer** — DataObjects mirrored 1:1 by `sql/schema.sql` and
  consumed by the dbt project under `dbt/`.

## Ingestion

`demo/scripts/seed.sh` builds an ephemeral local git repository from
this directory and POSTs it to `/ingest/git`, with include globs
`**/*.py,**/*.sql,**/*.md`. The Python and SQL AST parsers extract
ApplicationComponent and DataObject entities respectively. Markdown
docs are included so any document-extraction pass can lift Business and
Strategy entities; in plain code-only ingestion they are skipped.

## License & attribution

- Code, SQL, dbt, and architecture text: Apache-2.0, original to
  KnowledgeForge.
- The *ArchiSurance* name is a trademark of The Open Group; this
  dataset is themed after their reference architecture but does not
  redistribute their figures or text.
