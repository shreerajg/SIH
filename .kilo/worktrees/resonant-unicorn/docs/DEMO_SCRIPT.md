# SIH26107 — Demo Script

Three deterministic scenarios with the exact inputs to use and the results to expect. Every
figure below was produced by running the flow against the seeded demo corpus with **no LLM key
configured** (retrieval-only mode), so the demo is reproducible on any machine.

> With an LLM key configured the *wording* of explanations and answers changes — the standards,
> clauses, statuses, counts and citations do not, because those come from retrieval and rules.

## Before you start

```bash
docker compose up -d mysql          # optional; SQLite fallback works without it
python scripts/setup_demo.py --reset
```

Wait for the container to report healthy (`docker compose ps`) before running setup. With MySQL
up, `/api/health` reports `database.backend: mysql`; without it, `sqlite` — both are fully
functional and the demo is identical either way.

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm run dev
```

Sanity check — <http://localhost:8000/api/health> should report:

| Field | Expected |
|---|---|
| `corpus.standards` | 8 |
| `corpus.clauses` | 258 |
| `corpus.requirements` | 83 |
| `corpus.regulatory_records` | 4 |
| `corpus.amendments` | 3 |
| `corpus.vectors_clauses` | 258 |
| `llm.available` | `false` (or `true` with a key) |

If the counts are zero, `scripts/setup_demo.py` has not been run.

---

## Scenario 1 — Manufacturer, complete description (the headline demo)

**The point:** a manufacturer who does not know a single IS code gets a full pre-compliance
picture, with a real gap found by comparing a declared value against a clause limit.

### Step 1 — Landing → **I'm a Manufacturer**

Route: `/` → `/manufacturer`

### Step 2 — Product description

Click the **Water heater (complete)** sample, or paste:

```
We manufacture a 15 litre domestic electric storage water heater operating at 230 V with a 2000 W heating element and a vitreous enamel coated inner container.
```

Click **Analyse product**.

**Expected — product profile (`/product-analysis/:id`)**

| Field | Value |
|---|---|
| Name | Water Heater |
| Category | Water-Heater |
| Capacity (L) | 15 |
| Voltage (V) | 230 |
| Power (W) | 2000 |
| Application | domestic |
| Power source | electric |
| Heater type | Storage water heater |
| Profile source | Deterministic extraction |

No interview appears — the description already answered everything decisive.

> **Point to make:** none of these values came from a model. They were read out of the sentence by
> the taxonomy and quantity extractor, which is why they are identical every time.

### Step 3 — **Discover applicable standards**

**Expected — 4 standards, in this order**

| Standard | Relevance | Regulatory status |
|---|---|---|
| DEMO-STD-001 — Domestic Electric Storage Water Heaters | **HIGH** | MANDATORY |
| DEMO-STD-002 — Safety of Household Electrical Appliances | MEDIUM | Unable to verify |
| DEMO-STD-003 — Standard Test Methods | MEDIUM | Unable to verify |
| DEMO-STD-008 — Marking, Labelling and Instructions | MEDIUM | Unable to verify |

> **Point to make:** DEMO-STD-004 (pressure cookers) is *not* in the list even though its scope
> also says "domestic". Cross-family matches are penalised. And DEMO-STD-008 is included not
> because it looked similar, but because DEMO-STD-001 Clause 2.3 cites it as a normative
> reference — the card says exactly that.

### Step 4 — **Why this standard?** on DEMO-STD-001

Expect a two-column panel:

- **Your product** — matched factors including `water heater`, `storage water heater`, `domestic`,
  `electric`, `230 v`, `capacity`, and `product category`, each with a sentence explaining the match.
- **Standard scope (source text)** — the literal Clause 1.1 text, with clickable citations
  `DEMO-STD-001 · Clause 1.1` / `1.2` / `1.3`.
- A footer stating the explanation source and the regulatory status source.

Click a citation → the **evidence drawer** opens with the full clause text and its neighbours.

> **Point to make:** no confidence percentage is shown anywhere. Raw retrieval scores stay internal.

### Step 5 — Ask a grounded question

Go to **Assistant** (or click *Ask about this standard*) and ask:

```
What temperature rise test is required?
```

**Expected:** query type `TEST_REQUIREMENT`, an **Evidence verified** badge, and citations into
DEMO-STD-001 Clause 6.2.1 / 6.2.2 and DEMO-STD-003 Clause 4.x (the referenced test method).
Each verified claim lists the exact clause it came from.

Then ask:

```
Is DEMO-STD-002 mandatory?
```

**Expected:** the answer opens with **"Regulatory status: UNABLE TO VERIFY"** and explains that
this is not the same as voluntary.

> **Point to make:** the platform had every opportunity to guess, and refused.

### Step 6 — **Open gap analyzer** (`/product/:id/gap-analysis`)

Fill the **Declared values** panel:

| Field | Value |
|---|---|
| Maximum stored water temperature | **80** |
| Thermal cut-out fitted | Yes |
| Thermal cut-out reset type | manual |
| Dedicated earthing terminal | Yes |
| Measured earth continuity | 0.08 |
| Insulation resistance | 50 |
| Pressure relief device fitted | Yes |
| Inner container material | Vitreous enamel coated mild steel |
| Anode inspection interval | 24 |
| Protection class | I |
| Supply cord cross-section | 1.0 |

Tick this **evidence**:

- Temperature rise test report
- Hydrostatic pressure test report
- Insulation resistance and electric strength test report
- Earth continuity test report
- Standing loss test report
- Marking durability (rub) test report
- Inner container material certificate
- Thermal insulation chloride-free certificate
- Rating label / marking artwork (all required markings)
- Instruction manual (English + Hindi)
- Technical construction file

Click **Run pre-compliance analysis**.

**Expected result**

| Metric | Value |
|---|---|
| Pre-Compliance Readiness | **81%** |
| Supported | 29 |
| Potential gap | **1** |
| Test required | 4 |
| Document required | 1 |
| Official verification required | 1 |
| Total requirements | 36 |

Open the **Potential gap** filter. The one gap is:

> **D1-R06** — *The maximum thermostat setting shall not permit the mean stored water temperature
> to exceed 75 degC.*
> **Reason:** "Declared 80 degC against the limit that it must not exceed 75.0 degC. The declared
> value does not satisfy the clause limit."
> **Source:** DEMO-STD-001 · Clause 5.1.1

And **D8-R07** (conformity marking licence) is `OFFICIAL VERIFICATION` — the platform explicitly
refuses to decide something only the certifying authority can settle.

> **Point to make:** this is not a model saying "looks risky". A rule read 80, compared it to the
> 75 in Clause 5.1.1, and cited the clause. Change 80 to 72 and re-run — it flips to Supported
> and readiness rises.

### Step 7 — **Compliance Twin** (`/product/:id/compliance`)

| Summary card | Value |
|---|---|
| Applicable standards | 4 |
| Requirements identified | 36 |
| Supported | 29 |
| Potential gaps | 1 |
| Test evidence needed | 4 |
| Unknown | 0 |

Walk the tabs:

- **Overview** — readiness meter, category breakdown, product profile, regulatory position
  (1 mandatory, 3 unable to verify, 1 amendment alert).
- **Requirements** — 36 rows, filterable; click any row for the reason and recommended action.
- **Testing** — 15-item test plan, outstanding items first.
- **Gaps** — the outstanding items with next actions.
- **Amendments** — DEMO-STD-001 Amendment No. 1 on Clause 5.1.1, with a word-level diff showing
  **75 → 70 degC** tagged *tightened*, and a potential-impact note.
- **Graph** — 6 nodes: the product, its 4 standards, and the QCO record attached to DEMO-STD-001.
- **Sources** — 48 distinct clauses backing the dashboard.

> **Point to make on Amendments:** the diff is computed with `difflib` from the stored old and new
> wording. The model was not asked what changed. Note also that the amendment moves the limit to
> 70 degC — which would make the 80 degC declaration worse, not better.

---

## Scenario 2 — Manufacturer, vague description (the AI interview)

**The point:** when the description is too thin, the platform asks instead of guessing.

### Step 1 — `/manufacturer`, click the **Vague description** sample

```
We manufacture heaters.
```

Click **Analyse product**.

**Expected:** the profile page shows category *Water-Heater* with only `power source: electric`
extracted, and an **AI interview** panel appears with four questions:

| Question | Why it matters |
|---|---|
| What type of water heater is it? | Storage and instantaneous heaters are covered by different standards |
| What is the rated storage capacity in litres? | Scope and thickness requirements are capacity dependent |
| What is the rated supply voltage? | Voltage determines whether household appliance safety standards apply |
| Where will the product be used? | Domestic and industrial appliances fall under different scopes |

### Step 2 — Answer

- Type: **Storage water heater**
- Capacity: **15**
- Voltage: **230 V single phase**
- Application: **Domestic / household**

Click **Save 4 answers**.

**Expected:** the interview disappears, the product is renamed **Storage water heater**, and the
attributes now read `capacity_litres: 15`, `voltage_v: 230`, `application: domestic` — note the
free-text answers were normalised into numbers and canonical values.

From here the flow is identical to Scenario 1.

### Alternative — click **Continue with current information**

**Expected:** the interview closes, any answers already typed are kept, and a note appears:
*"Requirements that depend on the undeclared values will be reported as UNKNOWN rather than
assumed."* Running the analysis then shows `UNKNOWN` rows rather than optimistic guesses.

> **Point to make:** try `We make consumer goods.` instead. The platform cannot place it in any
> family, so its first question is *"Which of these best describes the product?"* — it will not
> pick one for you.

---

## Scenario 3 — Toy manufacturer + consumer mode

**The point:** a second product family end to end, then the consumer side.

### Step 3a — Manufacturer

`/manufacturer` → **Toy** sample:

```
We produce plastic rattles and painted wooden blocks for children under 18 months, sold in printed cartons.
```

**Expected profile:** category *Toy*, `age_group_min_months: 18`, with two interview questions
(materials, small parts). Answer:

- Materials: `Plastic (ABS) and painted wood`
- Contains small parts: **Yes**

**Expected standards (3):**

| Standard | Relevance | Regulatory |
|---|---|---|
| DEMO-STD-005 — Safety of Toys Part 1 (mechanical) | HIGH | MANDATORY |
| DEMO-STD-006 — Safety of Toys Part 2 (migration) | HIGH | Unable to verify |
| DEMO-STD-008 — Marking and Labelling | MEDIUM | Unable to verify |

> **Point to make:** Part 2 is pulled in because Part 1 Clause 2.1 names it as the chemical-safety
> companion — the reason on the card quotes that.

**Gap analysis.** Declare `Has cords: No`, `Longest cord length: 150`, and tick:

- Small parts cylinder test report
- Sharp edge and sharp point test report
- Drop test report
- Element migration (heavy metals) test report
- Choking hazard warning artwork
- Rating label / marking artwork (all required markings)
- Technical construction file
- Instruction manual (English + Hindi)

**Expected:** readiness **71%** — 17 supported, 4 test required, 2 document required,
1 official verification, 1 **not applicable**.

> **Point to make:** the *not applicable* row is D5-R05 (cord length limit), which only applies
> below 18 months. The rule read the declared age and switched the requirement off, rather than
> counting it against the manufacturer. Not-applicable rows are excluded from the readiness
> denominator.

**Amendments tab:** DEMO-STD-005 Amendment No. 2 on Clause 6.1, showing two changes —
**18 → 24 months** (*relaxed* threshold) and **220 → 200 mm** (*tightened* limit).

### Step 3b — Consumer mode

Go to `/consumer`. Enter:

```
DEMO-STD-004
```

**Expected:** a result card with

- Title: *Domestic Pressure Cookers — Specification*
- **Mandatory** badge and a **Demo Dataset** badge
- *What is this standard?* — plain-language summary
- *What it covers* — Pressure safety · Material requirements · Mechanical strength ·
  Gasket and sealing · Marking and labelling · Type testing
- *What it applies to* — the literal Clause 1.1 text
- *Is it required by law?* — the QCO record, with effective date and notification number, and an
  explicit note that this is a demonstration record
- Clickable source citations

Now enter a code that is **not** in the corpus:

```
IS 302
```

**Expected:** *"No standard matching 'IS 302' is present in the current corpus. This platform can
only answer for documents that have been ingested — it will not guess what an unknown code
means."* — followed by the list of standards that *are* loaded.

> **Point to make:** IS 302 is a real Indian Standard. A model asked about it would happily
> improvise. This system says it does not have it.

Finally, look up `DEMO-STD-002` and note the regulatory line reads **Unable to verify**, not
"voluntary".

---

## Closing: the Trust page

Route: `/trust`

Shows the dataset's own provenance (8 standards, 8 demo, 0 verified, 4 with a regulatory record,
4 reported as unable to verify), the six enforced controls with the file that implements each,
and the two-stage retrieval architecture with its fusion weights.

Then, if asked how any of this is proven:

```bash
cd backend && pytest -q
```

**Expected: 99 passed.** Re-run against the real database with
`TEST_DATABASE_URL=mysql+pymysql://sih:sihpassword@localhost:3307/sih26107_test pytest` —
also 99 passed. Point at `tests/test_guardrails.py` — the tests where a scripted model
returns `STD-999` and a fabricated `chunk-999` citation, and the system rejects both.

```bash
python scripts/evaluate.py
```

**Expected:** Recall@1 0.90, Recall@3 1.00, MRR 0.95 for standard discovery; Recall@5 1.00 for
clause retrieval; regulatory accuracy 1.00 with **0** cases of absence reported as voluntary;
citation validity 1.00 and unsupported-claim rate 0.00.

---

## If something goes wrong mid-demo

| Symptom | Fix |
|---|---|
| Banner: "Backend unreachable" | `cd backend && uvicorn app.main:app --reload --port 8000` |
| Counts are all zero | `python scripts/setup_demo.py --reset` |
| First search is slow | The embedding model loads once per process; warm it before the demo by loading any page |
| "No applicable standard identified" | The description is out of the demo corpus's four families — use one of the sample buttons |
| Database errors | The backend auto-falls back to SQLite; check `/api/health` → `database.backend` |
