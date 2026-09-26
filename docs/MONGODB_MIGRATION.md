# SQL → MongoDB migration

The platform previously stored its corpus in MySQL 8 (with an automatic SQLite fallback) through
SQLAlchemy 2. It now stores it in MongoDB through PyMongo. This document records what moved
where, what changed in behaviour, and how to roll back.

## Why PyMongo and not Motor

The application is synchronous: 37 of its 39 route handlers are `def`, and the two `async def`
handlers are async only to `await file.read()` on a multipart upload — their database work goes
through the same synchronous service layer. FastAPI runs `def` handlers in a threadpool, so
blocking PyMongo calls are correct there. Motor would have forced every service, every
repository call and every handler to become async for no gain.

## Schema mapping

11 tables became **9 collections**. Two tables are embedded rather than collections of their own.

| SQL table | MongoDB | Why |
|---|---|---|
| `standards` | `standards` | — |
| `standard_clauses` | `standard_clauses` | Queried independently by `chunk_id` constantly, and the whole collection is loaded to build the BM25 index. Embedding would bloat `standards` and turn a chunk lookup into an `$unwind`. |
| `compliance_requirements` | `compliance_requirements` | Queried by `standard_id` *and* by `requirement_code` across standards |
| `qcos` | `qcos` | Reseeded wholesale; counted independently; it is the audit table regulatory status is read from |
| `amendments` | `amendments` | Reseeded wholesale, queried by `standard_id` |
| `standard_relationships` | `standard_relationships` | Graph edges queried in **both** directions; embedding breaks the reverse query |
| `products` | `products` | — |
| `product_standard_matches` | **embedded** in `products.matches[]` | Only ever read/written for one product, always replaced wholesale |
| `compliance_results` | **embedded** in `products.results[]` | Same |
| `product_evidence` | `product_evidence` | `extracted_text` holds up to 200 KB per document and evidence is addressed individually by id, so embedding risks the 16 MB ceiling |
| `ingestion_runs` | `ingestion_runs` | — |

### Identifiers

All identifiers are the application's own strings and are stored as `_id` **verbatim**:
`DEMO-STD-001`, `prd-1a2b3c4d5e6f`, `psm-…`, `ev-…`, `cr-…`,
`DEMO-STD-001::D1-R05`, `IS-2082-2018-PM::c4.5.2`.

No ObjectIds were introduced. This is not a style preference: the ChromaDB vector store is keyed
by these same strings, so renaming them would silently break retrieval while every test still
passed.

### Constructs

| SQL | MongoDB |
|---|---|
| `db.get(Entity, id)` | `find_one({"_id": id})` |
| `db.query(E).filter(...).all()` | `find(filter)` |
| `func.count(E.id)` | `count_documents(filter)` |
| `E.x.in_(ids)` | `{"x": {"$in": ids}}` |
| `E.x.startswith(p)` | `{"x": {"$regex": f"^{re.escape(p)}"}}` |
| `JSONType` (MySQL JSON / SQLite TEXT) | native BSON sub-documents and arrays |
| `db.add()` + `db.commit()` | `replace_one(..., upsert=True)` / `insert_many` |
| `query.delete(synchronize_session=False)` | `delete_many(filter)` |
| `corpus.apply_mode(query)` | `corpus.apply_mode(filter_dict)` — returns a filter fragment callers merge |
| `UNIQUE(product_id, standard_id)` | structural: the embedded array is replaced as a whole |
| `UNIQUE(standard_clauses.chunk_id)` | a unique index — it is the citation key the Evidence Shield validates |

### The two JOINs

There were only two.

1. `/api/trust` counted standards having at least one QCO via
   `SELECT COUNT(DISTINCT standards.id) … JOIN qcos`. That is just the number of distinct
   `standard_id` values in `qcos`, so it became `len(qcos.distinct("standard_id"))`.
2. Amendment impact joined `compliance_results` to `compliance_requirements` for one product.
   Results are now embedded in the product, so it became one lookup of the requirements by code
   plus an in-memory pairing. No `$lookup` is used anywhere.

### Ordering

`ORDER BY x.effective_date IS NULL, x.effective_date DESC` ("non-null first, newest first")
became a single `sort([("effective_date", -1)])`: BSON orders null and missing below every date,
so descending already puts undated records last. The SQL needed the extra sort key only because
MySQL has no `NULLS LAST`.

## Indexes

Declared in `app/db/indexes.py`, applied on every startup (`create_index` is idempotent). Every
old SQL index is carried over, plus two additions driven by real query patterns:
`standards.is_verified` and `standards.is_demo`, because `corpus.apply_mode()` filters on them in
every discovery, RAG and consumer-lookup path.

`products` has no index beyond `_id`: it is always fetched by id, and its matches and results are
embedded rather than queried independently.

## Behaviour changes

* **No fallback database.** The old stack silently fell back to a local SQLite file when MySQL
  was unreachable, which meant a network problem could change *which corpus answered a
  question*. MongoDB is now the only store: if it is unreachable, `/api/health` and every data
  route return **503** with an explanatory message. Startup does not abort, so `/api/health`
  stays reachable to diagnose the problem.
* **Tests need infrastructure.** They run against `<MONGO_DB_NAME>_test`, dropped and rebuilt per
  session, with a guard refusing any database whose name does not end in `_test`. MongoDB has no
  local-file mode, so the old "pytest with zero setup" property is gone.
* **Atomic replacement.** Discovery and gap analysis previously did DELETE-then-INSERT, which
  could leave a product with partial state if it failed halfway. Both now swap an embedded array
  in a single update.

## The vector store also moved

ChromaDB has been removed. Embeddings now live in MongoDB alongside the corpus, in
`vectors_standards`, `vectors_clauses` and `vectors_product_evidence` (519 vectors, 384-dim,
`all-MiniLM-L6-v2`). The `vectors_` prefix is required: the unprefixed names collide with the
`standards` and `product_evidence` data collections.

| | Before | After |
|---|---|---|
| Store | ChromaDB, a 12 MB on-disk directory | MongoDB collections |
| Search | HNSW (local) | Atlas `$vectorSearch` ANN index |
| Fallback | `NumpyVectorStore` over `.npz` files | brute-force cosine over the same MongoDB vectors |
| Filtering | Chroma `where` on metadata | `standard_id` promoted to a top-level filter field |
| Config | `CHROMA_PATH`, `VECTOR_BACKEND` | none — follows `MONGO_URI` |

`/api/health` reports the live path under `retrieval.vector_search`: `atlas-vector-search` or
`brute-force-cosine`. Both read the same documents and return the same ranking (verified: same
ids, same order, max score delta 1.2e-07), so the fallback cannot drift from the indexed path.

### Score scale

Atlas returns cosine similarity remapped to `(1 + cos) / 2`. The store converts it back to plain
cosine so scores mean what they did under Chroma and match the brute-force path exactly.

### Index creation

Indexes are created on startup and by `setup_demo.py`, via the raw `createSearchIndexes` command
rather than `Collection.create_search_index()`. PyMongo 4.6's helper predates `vectorSearch`
indexes and drops the `type` field, which the server rejects as a malformed Atlas Search index
("Attribute mappings missing"). The raw command works on every driver version.

Builds are asynchronous — a new index reports `building` and retrieval uses the fallback until it
becomes queryable, which the store re-checks without needing a restart.

> **Atlas M0 allows 3 search indexes.** This uses exactly 3. Adding a fourth needs a paid tier.

### A bug this removed

`backend/.env` used to set `CHROMA_PATH=./storage/chroma`, a *relative* path, so the vector store
resolved against the current working directory. Running `python scripts/evaluate.py` from the
repository root — as the README instructed — pointed at an empty store, the semantic half of
hybrid retrieval silently contributed nothing, and clause-retrieval MRR fell from 0.96 to 0.79
with no error shown. Because the vectors now live in MongoDB, the working directory no longer
affects retrieval and the config option is gone.

## Data migration

Two scripts, both non-destructive and re-runnable.

`scripts/migrate_chroma_to_mongo.py` copies the vectors out of ChromaDB:

```bash
python scripts/migrate_chroma_to_mongo.py --dry-run
python scripts/migrate_chroma_to_mongo.py
```

Embeddings are **copied, not recomputed**. Re-embedding would need the model present and would
silently produce a different corpus if the model or its version ever differed; copying keeps the
vectors bit-identical to the ones retrieval was measured against.

`scripts/migrate_sqlite_to_mongo.py` moves an existing SQL database into MongoDB.

```bash
python scripts/migrate_sqlite_to_mongo.py --dry-run   # report only, writes nothing
python scripts/migrate_sqlite_to_mongo.py             # import
python scripts/migrate_sqlite_to_mongo.py --drop      # clear the target first
```

It opens the SQL database **read-only** (`mode=ro`) and never modifies or deletes it. Documents
are upserted by `_id`, so a partial run can simply be repeated. JSON-TEXT columns are parsed back
into native structures, datetimes are converted, matches and results are folded into their parent
product, and rows whose parent is missing are skipped and reported rather than imported dangling.

## Rollback

The SQL implementation was removed only after the MongoDB one was verified. To roll back, restore
these four files from version control and reinstate `SQLAlchemy`, `PyMySQL`, `alembic` and
`cryptography` in `backend/requirements.txt`:

```
backend/app/db/base.py
backend/app/db/types.py
backend/app/db/migrations.py
backend/app/models/entities.py
```

The original SQLite file at `backend/storage/sih26107.db` was never written to and still holds
the pre-migration data.

## Verification performed

| Check | Result |
|---|---|
| Backend test suite | **274 passed**, 0 failed — identical to the pre-migration baseline |
| Row-level migration fidelity | 640 rows compared field-by-field against SQLite, **0 mismatches** |
| Record count | 2,401 SQL rows → 752 documents + 525 embedded matches + 1,124 embedded results = **2,401** |
| API smoke test | **15/15** endpoints, including both ex-JOIN routes and the 404 paths |
| Retrieval accuracy (`scripts/evaluate.py`) | every headline metric **bit-identical** to the committed baseline |
| Connection failure | returns 503 with an actionable message; missing `MONGO_URI` reports clearly |
| Vector parity | indexed vs brute-force: same ids, same order, max score delta 1.2e-07 |
| Vector migration | 519 vectors copied (17 + 493 + 9), all 3 Atlas indexes queryable |
| Frontend | `tsc --noEmit` and `vite build` clean, **no frontend changes required** |
| SQL audit | zero SQLAlchemy/PyMySQL/alembic references outside the migration script |
