# SIH26107 — AI-Powered BIS Standards Intelligence & Pre-Compliance Platform

A standards intelligence engine for Indian Standards. A manufacturer describes a product in
plain English; the platform builds a structured product profile, discovers the applicable
standards from a verified corpus, explains *why* each one applies with clause-level evidence,
extracts the requirements, and compares them against the manufacturer's declared values and
evidence to produce a **pre-compliance** assessment. Consumers can look up a standard code and
get a plain-language explanation of what it covers.

> **This is not an official BIS certification platform.** It provides standards intelligence and
> pre-compliance assistance only. It does not issue certification and does not replace official
> conformity assessment.

---

## 1. Problem

A small manufacturer usually does not know which Indian Standards apply to their product. The
standards themselves are long, cross-referencing, and written for specialists. Which standard
applies? Which clauses are requirements rather than definitions? Which of those requirements
need a test report? Is the standard mandatory under a Quality Control Order? What changed in
the last amendment? Getting any of this wrong is expensive, and getting it *confidently* wrong —
which is what a general-purpose chatbot does — is worse than getting no answer at all.

## 2. Solution

A retrieval-and-verification system where a language model is deliberately **not** the source of
truth:

| Question | Answered by |
|---|---|
| Which standards apply? | Two-stage hybrid retrieval over a closed corpus |
| Why does this one apply? | Matched attributes + the standard's own scope clause |
| What does clause X say? | Clause-level retrieval, cited to a chunk id |
| Is it mandatory? | The structured QCO table — never the model |
| Am I ready? | A rule engine over structured requirements |
| What changed in the amendment? | `difflib` over the stored old/new wording |

The model explains, ranks and simplifies **what was retrieved**. Every claim it makes is
verified against the retrieved evidence before the user sees it, and the whole platform still
works with no API key at all.

## 3. Features

**Tier 1 — the core**

- **Product → Standard discovery.** Free-text description → structured profile → closed
  candidate list → ranked matches. The model may only select from the retrieved candidates; any
  identifier it invents is rejected and reported.
- **Why this standard?** Each match shows the matched product attributes, the standard's scope
  text, the source clauses, and where the explanation came from.
- **Clause-level RAG.** Answers cite standard, clause, heading and page, with the full source
  text one click away.
- **Evidence Shield.** Backend validation, not a prompt. The model returns claims with chunk
  ids; every id is checked against the retrieved context; claims citing anything else are
  dropped; if nothing survives, the answer becomes an explicit abstention.
- **Pre-compliance gap analyzer.** Requirement-by-requirement assessment producing one of seven
  closed statuses, each with a reason and a clause citation.
- **Product Compliance Twin.** One dashboard: profile, standards, requirements, test plan,
  evidence, gaps, amendments, knowledge graph and sources.

**Tier 2**

- **AI product interview.** "We manufacture heaters." → targeted questions instead of a guess.
- **Consumer mode.** IS code, a plain product name ("pressure cooker"), a browse-by-product-type
  grid, or a photographed label (OCR) → the same plain-language explanation, covered areas and
  regulatory status. A misread code degrades to "not found, closest matches shown" — never a
  fabricated standard.
- **Regulatory status** from structured records, with an explicit `UNABLE_TO_VERIFY` state.
- **BIS certification scheme guidance.** Which scheme applies to a product, resolved from the
  Quality Control Order on file and the official BIS list of products under compulsory
  certification - never inferred from the product description. Shows the scheme, why it applies,
  each supporting record with its BIS source URL, and an explicit "unable to verify" where no
  record names one. Answers "Which BIS scheme applies to my product?", "What is Scheme I?" and
  "Do I need BIS certification?" in the assistant.
- **Certification process guidance.** The Scheme-I journey as an ordered set of steps, each
  backed by a clause from the BIS Product Manual or Quality Control Order held for that specific
  product. Includes the implementation dates BIS sets separately for micro, small and other
  enterprises, read from the order's own table. Steps with no supporting document say so, and the
  BIS application stage is marked as not held in this corpus rather than described from memory.
- **Hallmarking guidance.** Consumer and jeweller flows over the official BIS hallmarking corpus:
  what the three marks on a hallmarked gold article are, the permitted purity/fineness grades,
  what a HUID is, what to check before buying, the jeweller's route to getting articles
  hallmarked, and a searchable snapshot of the 1,655 recognised Assaying & Hallmarking Centres.
  The platform explains a HUID but **never verifies one** - it is not connected to the BIS HUID
  service and says so wherever a code is entered.
- **Compliance test planner** derived from test-evidence requirements, cross-referencing the
  standard that actually specifies each test's procedure and linking straight to the evidence
  that satisfied it, with a downloadable checklist.
- **Product evidence upload.** PDF/TXT/PNG/JPEG, with deterministic field extraction (model,
  result, lab, report number) that feeds the gap analyzer without ever asserting a document
  proves compliance.

**Tier 3**

- **Amendment impact** with a deterministic word-level diff and detected numeric limit changes.
- **Standards knowledge graph.** A corpus-wide, interactive explorer (`/graph`) alongside the
  per-product graph in the Compliance Twin — every node a stored standard or QCO record, every
  edge a stored relationship that cites the clause stating it.
- **Measured accuracy.** `scripts/evaluate.py` scores retrieval, both consumer-lookup paths, the
  gap analyzer and amendment impact against ground truth read from the source documents, surfaced
  live on the Trust page — not a claim, a number.

## 4. Architecture

```
                              USER
                 ┌─────────────┴─────────────┐
           MANUFACTURER                  CONSUMER
        describe product                  IS code
                 │                            │
    ProductUnderstandingService      normalize_is_number
      (taxonomy + regex + LLM)               │
                 │                            │
      ProductInterviewService                 │
                 │                            │
          Product Profile                     │
                 └─────────────┬──────────────┘
                               │
                         Query Router
                               │
                  ┌────────────▼────────────┐
                  │   STAGE 1: standards    │
                  │  BM25 + dense + metadata│
                  └────────────┬────────────┘
                        closed candidate list
                               │
                  ┌────────────▼────────────┐
                  │   STAGE 2: clauses      │
                  │  restricted to stage 1  │
                  └────────────┬────────────┘
              ┌────────────────┼────────────────┐
          Standards           QCOs          Amendments
          (clauses)      (structured)      (old/new text)
              └────────────────┼────────────────┘
                         Grounded LLM
                    (claims + chunk ids)
                               │
                     ┌─────────▼─────────┐
                     │  EVIDENCE SHIELD  │  ← rejects unverified claims
                     └─────────┬─────────┘
              ┌────────────────┴────────────────┐
       ComplianceGapAnalyzer            Consumer explanation
        (rule engine, closed             + grounded follow-up
         status vocabulary)
              │
      Product Compliance Twin
```

### Anti-hallucination controls (all backend-enforced)

| Control | What it does | Where |
|---|---|---|
| Closed candidate list | Rejects standard IDs the model returns that were not retrieved | `app/services/standard_discovery.py` |
| Evidence Shield | Rejects claims citing chunks not in the retrieved context | `app/rag/evidence_shield.py` |
| Structured regulatory status | Mandatory/voluntary from the QCO table only; absence → `UNABLE_TO_VERIFY` | `app/services/regulatory.py` |
| Closed status vocabulary | Gap statuses from a rule engine, fixed enumeration | `app/compliance/gap_analyzer.py` |
| Deterministic amendment diff | `difflib` over stored wordings, not model recall | `app/services/amendments.py` |
| Provenance on every record | `source_type`, `is_verified`, `is_mock` on every row | `app/models/entities.py` |

Each control has a failing-if-broken test in `backend/tests/test_guardrails.py`.

## 5. Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, React Router, Axios, Lucide |
| Backend | Python, FastAPI, Pydantic v2, PyMongo 4 |
| Database | MongoDB (PyMongo, synchronous driver) |
| Vector store | MongoDB — Atlas Vector Search, brute-force cosine fallback |
| Embeddings | `all-MiniLM-L6-v2` via sentence-transformers (hashing fallback) |
| Keyword search | `rank-bm25` (pure-python fallback) |
| Documents | PyMuPDF for PDF, plain text/markdown supported |
| LLM | Pluggable: OpenAI / Anthropic / Gemini over plain HTTP, or none |

Every heavy dependency has a working fallback, and the active backend is reported by
`/api/health` — nothing is silently swapped.

## 6. Folder structure

```
sih26107/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers (health, products, standards)
│   │   ├── compliance/     # gap analyzer + readiness maths
│   │   ├── core/           # config, constants, deterministic text utilities
│   │   ├── db/             # Mongo client, repositories, index definitions
│   │   ├── ingestion/      # clause-aware parser, pipeline, seeding
│   │   ├── llm/            # provider abstraction + structured generation
│   │   ├── models/         # MongoDB document models (dataclasses)
│   │   ├── rag/            # RAG service + Evidence Shield
│   │   ├── schemas/        # Pydantic API contracts
│   │   ├── search/         # embeddings, vector store, BM25, hybrid retriever
│   │   ├── services/       # understanding, interview, discovery, regulatory, consumer
│   │   └── main.py
│   ├── tests/              # 96 tests, including the guardrail suite
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/{components,pages,lib}
├── data/
│   ├── raw/standards/      # source documents (drop real BIS PDFs here)
│   ├── requirements/       # structured requirements per standard
│   ├── seed/               # QCO, amendment and relationship records
│   ├── evaluation/         # ground truth + computed results
│   └── source_manifest.json
├── scripts/                # setup_demo, ingest_documents, seed_database, evaluate
├── docs/DEMO_SCRIPT.md
├── docker-compose.yml
└── render.yaml
```

## 7. Local setup

Prerequisites: Python 3.9+, Node 18+, and a reachable MongoDB (Atlas or self-hosted).

### Windows (PowerShell) — one command

```powershell
.\scripts\setup_demo.ps1
```

### Manual, any platform

**1. Database**

MongoDB is the only database and there is **no local fallback** - if it is unreachable the API
returns 503 rather than quietly answering from a different corpus. Put the connection string in
`backend/.env` (the file is git-ignored; never commit a URI):

```bash
MONGO_URI=mongodb+srv://USER:PASSWORD@YOUR-CLUSTER.mongodb.net/
MONGO_DB_NAME=sih26107
```

An Atlas connection string carries no database name, which is why `MONGO_DB_NAME` is separate.

**2. Backend**

```bash
cd backend
python -m venv .venv
```

```powershell
.venv\Scripts\Activate.ps1
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
cp .env.example .env
```

**3. Build the corpus** (from the repository root)

```bash
python scripts/setup_demo.py --reset
```

This creates the schema, parses every document in `data/raw/standards`, chunks it by clause,
embeds it into MongoDB, and seeds requirements, regulatory records, amendments and
relationships. It is idempotent.

**4. Run the API**

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

Interactive docs at <http://localhost:8000/docs>.

**5. Frontend**

```bash
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173>.

## 8. Environment variables

### Backend (`backend/.env`, see `.env.example`)

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | Environment label |
| `MONGO_URI` | *(required)* | MongoDB connection string. Never hard-coded; read from `.env` |
| `MONGO_DB_NAME` | `sih26107` | Database name (Atlas URIs carry none) |
| `MONGO_TIMEOUT_MS` | `8000` | Server-selection timeout, so a dropped network fails fast |
| `LLM_PROVIDER` | `auto` | `auto` \| `openai` \| `anthropic` \| `gemini` |
| `LLM_API_KEY` | *(empty)* | Leave empty to run retrieval-only |
| `LLM_MODEL` | *(provider default)* | Model override |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model |
| `EMBEDDING_BACKEND` | `auto` | `auto` \| `sentence-transformers` \| `hashing` |
| `WEIGHT_SEMANTIC` / `WEIGHT_BM25` / `WEIGHT_METADATA` | `0.60` / `0.30` / `0.10` | Hybrid fusion weights |
| `FRONTEND_URL`, `CORS_ORIGINS` | localhost | CORS allowlist |
| `MAX_UPLOAD_MB` | `15` | Size limit for evidence uploads and label scans |
| `OCR_BACKEND` | `auto` | `auto` \| `off` — consumer label scanning (Tesseract) |
| `TESSERACT_CMD` | *(auto-detect)* | Path to the tesseract binary; set explicitly outside the Docker image |

With `LLM_PROVIDER=auto` the service also picks up `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`GEMINI_API_KEY` or `GOOGLE_API_KEY` from the environment.

### Frontend (`frontend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` (proxied to `:8000` in dev) | Backend base URL |

No production URL is hard-coded anywhere.

## 9. MongoDB setup

The platform stores everything in **9 collections**, created on first write. Indexes are
declared in `app/db/indexes.py` and applied on every startup (`create_index` is idempotent).

| Collection | Holds |
|---|---|
| `standards` | one document per standard / product manual / QCO document |
| `standard_clauses` | clause-level chunks; `chunk_id` is **unique** and is the citation key |
| `compliance_requirements` | structured requirements, cited to a clause |
| `qcos` | Quality Control Order records - the only source of regulatory status |
| `amendments` | stored old/new wording for the deterministic diff |
| `standard_relationships` | graph edges, each citing the clause that states it |
| `products` | product profile, **with `matches[]` and `results[]` embedded** |
| `product_evidence` | uploaded/declared evidence (kept separate: `extracted_text` is large) |
| `ingestion_runs` | ingestion bookkeeping |
| `certification_schemes` | BIS scheme registry; unsourced fields stay empty and are reported as unverifiable |
| `scheme_product_index` | the official BIS Scheme-I product list, extracted from the BIS index page - the applicability oracle |
| `certification_processes` | process stage templates; they store no clause text, so citations are resolved live against the corpus |
| `hallmarking_knowledge` | purity grades, hallmark components, consumer checks and process stages, each resolved to a BIS clause at query time |
| `hallmarking_centres` | snapshot of the BIS directory of Assaying & Hallmarking Centres, with recognition number, scope, status and retrieval date |

Identifiers are the application's own strings (`DEMO-STD-001`, `prd-1a2b3c`,
`IS-2082-2018-PM::c4.5.2`) stored as `_id`. No ObjectIds are introduced - the vector
store is keyed by these same strings, so changing them would silently break retrieval.

### Vectors

Embeddings live in MongoDB too, in three further collections - `vectors_standards`,
`vectors_clauses` and `vectors_product_evidence`. Each document holds the 384-dimensional
`all-MiniLM-L6-v2` vector, the text it was built from, and the metadata retrieval filters on.
The `vectors_` prefix is load-bearing: the unprefixed names would collide with the `standards`
and `product_evidence` data collections.

Semantic search runs one of two ways, and `/api/health` reports which under
`retrieval.vector_search`:

* **`atlas-vector-search`** - a `$vectorSearch` ANN index (cosine, with `standard_id` as a
  filter field), created automatically on startup by `app/search/vector_store.py`.
* **`brute-force-cosine`** - NumPy cosine over the same stored vectors, used while an index is
  still building or on a deployment without Atlas Search.

Both paths read the same documents and return the same ranking, so the fallback cannot drift
from the indexed one. Index builds are asynchronous; the store re-checks and switches over on
its own once they become queryable.

> Atlas shared tiers (M0) allow **3 search indexes**, which is exactly what this uses.

`matches` and `results` are embedded rather than kept in their own collections because both are
only ever read and written for one product at a time and are replaced wholesale, which an
embedded array does atomically in a single update.

There is **no fallback database**. If MongoDB is unreachable the API answers 503 with an
explanatory message; it never degrades to a different corpus.

## 10. Data ingestion

```bash
# everything at once (schema + ingest + embed + seed)
python scripts/setup_demo.py --reset

# just documents
python scripts/ingest_documents.py --input data/raw/standards
python scripts/ingest_documents.py --file path/to/IS-XXXX.pdf

# just structured knowledge
python scripts/seed_database.py
```

**Adding real BIS documents.** Put the PDF in `data/raw/standards/`, add an entry to
`data/source_manifest.json` with `source_type: "official"`, the retrieval URL, the retrieval
date and `verified: true`, then re-run `ingest_documents.py`. The parser, chunker, retriever and
Evidence Shield work identically on official documents — no code change is needed.

## 11. Run commands

| What | Command |
|---|---|
| Backend | `cd backend && uvicorn app.main:app --reload --port 8000` |
| Frontend | `cd frontend && npm run dev` |
| Backend tests | `cd backend && pytest` |
| Frontend type-check | `cd frontend && npm run lint` |
| Frontend production build | `cd frontend && npm run build` |
| Evaluation | `python scripts/evaluate.py` |
| SQL → MongoDB data migration | `python scripts/migrate_sqlite_to_mongo.py --dry-run` |
| Chroma → MongoDB vector migration | `python scripts/migrate_chroma_to_mongo.py --dry-run` |
| Rebuild the BIS Scheme-I index | `python scripts/extract_scheme_index.py` |
| Fetch the BIS hallmarking sources | `python scripts/fetch_hallmarking_sources.py` |
| Stage + register them for ingestion | `python scripts/prepare_hallmarking_corpus.py` |
| Extract the A&H centre directory | `python scripts/extract_ahc_directory.py` |
| Hallmarking tests (needs the fetched corpus) | `HALLMARKING_TEST_CORPUS=1 pytest tests/test_hallmarking.py` |

## 12. Testing

```bash
cd backend && pytest
```

The suite runs against a **separate database**, `<MONGO_DB_NAME>_test`, which it drops and
rebuilds for every session, so it can never touch development data. A guard in `conftest.py`
refuses to run if the database name does not end in `_test`.

By default it uses the cluster `MONGO_URI` already points at. Override either piece:

```bash
cd backend && TEST_MONGO_URI=mongodb://localhost:27017 TEST_MONGO_DB_NAME=sih26107_test pytest
```

**274 passed.** Unlike the previous SQLite default, the suite now needs a reachable MongoDB -
MongoDB has no local-file mode, so there is no infrastructure-free option.

The tests cover:

- `tests/test_guardrails.py` — the anti-hallucination contract:
  - a model returning `STD-999` / a remembered IS number cannot reach the response;
  - a claim citing `chunk-999` is rejected, and total rejection produces an abstention;
  - a standard with no QCO record returns `UNABLE_TO_VERIFY`, never `VOLUNTARY`;
  - a model asserting "this is voluntary" cannot override the database.
- `tests/test_core.py` — IS-code normalisation, quantity extraction, category detection,
  clause parsing and lineage, rule evaluation, evidence matching, amendment diffs, readiness maths.
- `tests/test_api.py` — the full golden flow end to end, plus error paths.

Frontend: `npm run build` runs `tsc -b` first, so the build fails on any type error.

## 13. Deployment

**Backend → Render** (blueprint in `render.yaml`):
1. Provision a MongoDB deployment (MongoDB Atlas, or any managed MongoDB).
2. Deploy the blueprint; set `MONGO_URI`, `MONGO_DB_NAME`, `FRONTEND_URL`, `CORS_ORIGINS` and
   (optionally) `LLM_API_KEY` in the dashboard — never in the repository.
3. Allow the platform's egress IPs in the MongoDB network-access list.
4. From the service shell, run once: `python scripts/setup_demo.py`.
5. A disk is mounted at `/app/storage` only for uploaded evidence files; the vector index
   lives in MongoDB, so no vector-store volume is required.

**Frontend → Vercel** (`frontend/vercel.json`): import the repo, set root directory to
`frontend`, and set `VITE_API_BASE_URL` to `https://<your-api-host>/api`.

**Everything in Docker:**

```bash
docker compose --profile full up -d
```

## 14. Demo flow

The full click-by-click script with expected results is in
[`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md). In short:

1. Landing → **I'm a Manufacturer**
2. Paste *"We manufacture heaters."* → the platform asks what type instead of guessing
3. Answer: storage / 15 L / 230 V / domestic
4. **Discover applicable standards** → DEMO-STD-001 (HIGH) plus the general safety, test-method
   and marking standards it references
5. **Why this standard?** → matched attributes beside the scope clause
6. Ask *"What temperature rise test is required?"* → clause-level citation
7. **Gap analyzer** → declare values, tick evidence, run
8. **Compliance Twin** → readiness, requirements, test plan, gaps, amendments, graph, sources
9. Switch to **Consumer** → `DEMO-STD-004` → plain-language explanation
10. **Trust** page → the controls, and the dataset's own provenance

## 15. Trust and anti-hallucination design

The core design decision is that **retrieval and rules produce the facts; the model produces the
prose**. Concretely:

- Standard identifiers come from a closed candidate list. The prompt says so, *and the backend
  enforces it* — the prompt alone would not be a control.
- Every generated claim carries chunk ids, which are checked server-side against the ids that
  were actually placed in the context window. A fabricated citation is removed, and the answer
  is rebuilt from surviving claims rather than shown as written.
- Regulatory status is a database read. Absence of a Quality Control Order record returns
  `UNABLE_TO_VERIFY` with an explanatory message — the platform never converts *"we have no
  record"* into *"it is voluntary"*.
- Compliance statuses come from a rule engine with a fixed seven-value vocabulary. A model may
  rewrite a *reason*; it cannot change a *status*.
- Language is chosen carefully: **Pre-Compliance Readiness**, *supported by provided evidence*,
  *potential gap*, *test evidence required*. Never "your product is BIS compliant".
- Without an API key the assistant quotes retrieved clause text verbatim instead of
  paraphrasing. Nothing is invented to fill the gap.

### Dataset honesty

This repository ships a **synthetic demonstration corpus** using `DEMO-STD-nnn` identifiers,
specifically so that nothing here can be mistaken for a real Indian Standard. Every record
carries `is_verified: false` and `is_mock: true`, `data/source_manifest.json` states the
provenance of each document, and the UI shows a **Demo Dataset** banner. Real BIS documents can
be dropped into the same pipeline.

## 16. Evaluation

```bash
python scripts/evaluate.py
```

Ground truth in `data/evaluation/evaluation_queries.json` was written by reading the corpus
documents, not by recording the system's own output. Results are written to
`data/evaluation/results.json` and served read-only at `GET /api/evaluation`, which the Trust
page renders live — expandable to every individual case, not just the headline number.

Measured on the demo corpus, retrieval-only (no LLM key), with
`sentence-transformers/all-MiniLM-L6-v2` + Atlas Vector Search + rank-bm25:

| Metric | Result |
|---|---|
| Standard discovery Recall@1 | **0.91** (11 cases) |
| Standard discovery Recall@3 | **1.00** |
| Standard discovery MRR | **0.95** |
| Supporting-standard recall | **1.00** |
| Clause retrieval Recall@5 | **1.00** (15 cases) |
| Clause retrieval MRR | **0.96** |
| Consumer lookup accuracy (by code) | **1.00** (5 cases) |
| Consumer lookup accuracy (by description) | **1.00** (3 cases) |
| Regulatory status accuracy | **1.00** (8 cases) |
| Absence reported as "voluntary" | **0** |
| Gap analyzer accuracy | **1.00** (2 cases) |
| Amendment impact accuracy | **1.00** (3 cases) |
| Citation validity | **1.00** (60 displayed claims) |
| Unsupported claim rate | **0.00** |

The one Recall@1 miss (a toy-safety query the retriever ranks chemical-safety first, still
recalled at Recall@3) is left as-is rather than tuned away — these are small-corpus numbers on a
synthetic dataset and should be read as a check that the pipeline is wired correctly, not as a
benchmark result.

## 17. Limitations

Stated plainly, because a compliance tool that overstates itself is the problem it claims to solve:

- **The corpus is synthetic.** Every standard is `DEMO-STD-nnn`, authored for this prototype.
  No official BIS text is included, and the QCO and amendment records are illustrative.
- **The platform records that evidence exists; it does not read or judge it.** Ticking "I have a
  temperature rise test report" marks the requirement *supported by provided evidence*. Whether
  that report would be accepted by a certifying body is out of scope.
- **Requirement extraction is curated, not automatic.** Requirements live in
  `data/requirements/*.json` with clause citations. `RequirementExtractionService`-style
  automatic extraction from arbitrary clause text is not yet implemented.
- **Reranker falls back to lexical.** A `CrossEncoderReranker` exists behind the same interface,
  but on a machine without the model cached it falls back to a dependency-free lexical scorer -
  correct, never silently skipped, but not the same ranking quality a downloaded cross-encoder
  would give on a larger corpus.
- **No authentication.** The prototype runs in guest mode by design; products are addressed by
  an unguessable id but are not access-controlled.
- **OCR needs Tesseract installed.** Consumer label scanning (`app/services/ocr.py`) degrades to
  an explicit "OCR unavailable" message, never a fabricated read, when the engine isn't present -
  see the Dockerfile for the apt package that makes it work in the deployed container.
- **Evaluation is still small.** 11 discovery, 15 clause, 5+3 consumer, 8 regulatory, 2 gap-analysis
  and 3 amendment-impact cases - real numbers on a small, synthetic corpus, not a benchmark.

## 18. Future scope

- Ingest the real BIS corpus under its licence terms and flip the dataset to `verified`.
- Pre-download the cross-encoder model so reranking uses it by default instead of the lexical
  fallback.
- Automatic requirement extraction from clause text, with human review before it becomes a rule.
- A what-if simulator: change a design value, see which requirement statuses move.
- Amendment watch with notifications when a standard a product depends on changes.

---

Built for Smart India Hackathon 2026, problem statement **SIH26107**.
