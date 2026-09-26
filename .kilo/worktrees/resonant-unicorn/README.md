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
| Backend | Python, FastAPI, Pydantic v2, SQLAlchemy 2 |
| Database | MySQL 8 (automatic SQLite fallback for local demos) |
| Vector store | ChromaDB, persistent (NumPy fallback) |
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
│   │   ├── db/             # engine, session, portable JSON column
│   │   ├── ingestion/      # clause-aware parser, pipeline, seeding
│   │   ├── llm/            # provider abstraction + structured generation
│   │   ├── models/         # SQLAlchemy entities
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

Prerequisites: Python 3.9+, Node 18+, and optionally Docker for MySQL.

### Windows (PowerShell) — one command

```powershell
.\scripts\setup_demo.ps1
```

### Manual, any platform

**1. Database (optional but recommended)**

```bash
docker compose up -d mysql
```

MySQL 8 starts on port **3307** (not 3306, to avoid clashing with a local install).
If you skip this, the backend automatically falls back to a local SQLite file and says so in
`/api/health`.

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
embeds it into ChromaDB, and seeds requirements, regulatory records, amendments and
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
| `DATABASE_URL` | `mysql+pymysql://sih:sihpassword@localhost:3307/sih26107` | SQLAlchemy URL |
| `DB_FALLBACK_SQLITE` | `true` | Fall back to SQLite when the DB is unreachable |
| `LLM_PROVIDER` | `auto` | `auto` \| `openai` \| `anthropic` \| `gemini` |
| `LLM_API_KEY` | *(empty)* | Leave empty to run retrieval-only |
| `LLM_MODEL` | *(provider default)* | Model override |
| `CHROMA_PATH` | `./storage/chroma` | Persistent vector store |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model |
| `EMBEDDING_BACKEND` | `auto` | `auto` \| `sentence-transformers` \| `hashing` |
| `VECTOR_BACKEND` | `auto` | `auto` \| `chroma` \| `numpy` |
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

## 9. MySQL setup

`docker compose up -d mysql` creates database `sih26107` with user `sih` / `sihpassword` on
port 3307, using a named volume so data survives restarts.

This is the default `DATABASE_URL`, so with the container running the application uses MySQL
with no `.env` file at all — `/api/health` will report `"database": {"backend": "mysql"}`.
Verified against **MySQL 8.0.46**: all 11 tables create cleanly, `keywords` / `covered_areas` and
the other JSON columns are stored as native MySQL `JSON` (queryable with `JSON_CONTAINS` /
`JSON_EXTRACT`), data survives `docker compose restart mysql`, and the API reconnects on its own
afterwards thanks to `pool_pre_ping`.

For an existing MySQL server:

```sql
CREATE DATABASE sih26107 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'sih'@'%' IDENTIFIED BY 'a-strong-password';
GRANT ALL PRIVILEGES ON sih26107.* TO 'sih'@'%';
FLUSH PRIVILEGES;
```

Then set `DATABASE_URL` accordingly. Tables are created automatically on startup and by
`scripts/setup_demo.py`; Alembic is installed if you later want versioned migrations.

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
| MySQL | `docker compose up -d mysql` |

## 12. Testing

```bash
cd backend && pytest
```

The suite defaults to a throwaway SQLite file so it needs no infrastructure. Point it at the
real target database to run the identical suite against MySQL:

```bash
docker exec sih26107-mysql mysql -uroot -prootpassword -e "CREATE DATABASE IF NOT EXISTS sih26107_test; GRANT ALL ON sih26107_test.* TO 'sih'@'%';"
```

```bash
cd backend && TEST_DATABASE_URL=mysql+pymysql://sih:sihpassword@localhost:3307/sih26107_test pytest
```

**250 passed** on SQLite (the default backend; run `pytest` with no setup required). The same
suite runs unmodified against MySQL 8 by setting `TEST_DATABASE_URL` before `pytest` — useful to
re-verify after a schema change, since `app/db/migrations.py` is written to be dialect-portable
(SQLite and MySQL 8) but a real run against MySQL is the only way to be sure.

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
1. Provision a MySQL instance (Render, Aiven, Railway, PlanetScale).
2. Deploy the blueprint; set `DATABASE_URL`, `FRONTEND_URL`, `CORS_ORIGINS` and (optionally)
   `LLM_API_KEY` in the dashboard — never in the repository.
3. `DB_FALLBACK_SQLITE=false` in production, so a database problem fails loudly.
4. From the service shell, run once: `python scripts/setup_demo.py`.
5. A 2 GB disk is mounted at `/app/storage` for the persistent Chroma index.

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
`sentence-transformers/all-MiniLM-L6-v2` + ChromaDB + rank-bm25:

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
