# 🏠 ShopSense AI — GenAI-Powered Home Shopping Assistant

> **AI-first e-commerce assistant built with Google Gemini (`gemini-3.1-flash-lite`), LangChain, Streamlit, and SQLite.**  
> Grounded in real catalog data with zero hallucinations, deterministic multi-layered guardrails, side-by-side product comparisons, and a real 20-case evaluation benchmark.

---

## 🎯 What We Achieved & How We Achieved It

### What We Built
- **A 5-Page Streamlit Production Application**:
  1. `app.py`: Entrypoint homepage with live SQLite catalog statistics, suggested prompt shortcuts, and featured products.
  2. `pages/1_Chat.py`: Conversational shopping assistant with multi-turn chat memory, interactive verified cards, and offline fallback mode.
  3. `pages/2_Product_Search.py`: Deterministic parameterized SQL catalog search with sliders for price, rating, dimensions, and categories.
  4. `pages/3_Compare_Products.py`: Side-by-side product comparison workspace with an attribute table and Python-calculated trade-off summaries.
  5. `pages/4_Evaluation_Dashboard.py`: Benchmark evaluation dashboard executing the 20-case suite on demand.
- **100% Deterministic Safety & Guardrails**: 4/4 guardrail benchmark categories passing with **100% accuracy** (Safety, Prompt Injection, Out-of-Scope refusals).
- **Zero Hallucination Retrieval**: Every recommended product is verified to exist in SQLite before reaching the UI.
- **Honest Empty States**: If constraints (e.g., price < ₹1,000 for large mirrors) yield no results, the system transparently says so instead of returning irrelevant items.
- **31 Automated Tests**: 100% unit test pass rate covering database loading, schemas, parameterized queries, guardrails, agent orchestration, and metric math.

---

## 🏗️ How We Achieved It: Core Engineering Principles

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        SHOPSENSE AI ARCHITECTURE                       │
└────────────────────────────────────────────────────────────────────────┘
                               User Query
                                   │
                                   ▼
                ┌──────────────────────────────────────┐
                │        1. INPUT GUARDRAILS           │
                │  - Empty / Length Check (<1500 chars)│
                │  - Prompt Injection Interception     │
                │  - Dangerous / Harmful Detection     │
                │  - Out-of-Scope Domain Refusal       │
                └──────────────────┬───────────────────┘
                       Allowed?    │
                     ┌─────────────┴─────────────┐
                    YES                          NO ──► Return Safe Refusal
                     │                                  (Zero LLM Cost)
                     ▼
         ┌────────────────────────┐
         │ 2. STAGE A: QUERY      │
         │    UNDERSTANDING       │
         │ (gemini-3.1-flash-lite)│
         └───────────┬────────────┘
                     │ Parses structured ShoppingIntent (Pydantic)
                     ▼
         ┌────────────────────────┐
         │ 3. DETERMINISTIC SQL   │
         │    HARD FILTERS        │
         │ (SQLite Parameterized) │
         └───────────┬────────────┘
                     │ Filtered Candidate IDs (Price, Width, Height, Cat)
                     ▼
         ┌────────────────────────┐
         │ 4. RANKING / RETRIEVAL │
         │  - Semantic Cosine Sim │
         │  - Weighted LIKE Score │
         └───────────┬────────────┘
                     │ Ranked Candidate Products
                     ▼
         ┌────────────────────────┐
         │ 5. OUTPUT GUARDRAILS   │
         │  - Product ID in DB?   │
         │  - Constraint Re-Check │
         └───────────┬────────────┘
                     │ Verified Products
                     ▼
         ┌────────────────────────┐
         │ 6. STAGE B: RESPONSE   │
         │    GENERATION          │
         │ (gemini-3.1-flash-lite)│
         └───────────┬────────────┘
                     │ Grounded Explanation & Interactive Product Cards
                     ▼
             Rendered in Streamlit UI
```

---

## 🛡️ Deep Dive: Complete Guardrail Implementation

Guardrails in ShopSense AI are intentionally **decoupled from LLM evaluation**. Relying on an LLM to evaluate itself is slow, costly, and vulnerable to jailbreaks. Instead, ShopSense AI uses a multi-tiered defense architecture:

### 1. Pre-LLM Input Guardrails (`shopsense/guardrails/input_checks.py`)
Runs **synchronously in < 1 millisecond** before any network call or Gemini API invocation:

1. **Empty & Length Validation**:
   - Rejects blank inputs or whitespace-only messages.
   - Restricts queries to 1,500 characters to prevent buffer overflow attacks and token-stuffing denial-of-service.
2. **Prompt Injection & Jailbreak Interception**:
   - Intercepts attempts to override system directives (e.g. `Ignore all previous instructions...`, `Forget prior directives`).
   - Detects jailbreak personas (e.g. `DAN mode`, `act as an unrestricted AI`).
   - Blocks attempts to leak system instructions or secrets (e.g. `What is your system prompt?`, `Print internal instructions`).
3. **Harmful Content & Safety Filter**:
   - Refuses dangerous or illicit instructions (weapons, explosives, synthesis of illegal substances, self-harm, violent instructions).
4. **Out-of-Scope Domain Refusal**:
   - ShopSense AI is specialized in **IKEA Home Decor**. Queries for electronics (iPhones, laptops, TVs), automotive parts, groceries, clothing, or large furniture slices (sofas, beds, recliners) are politely refused with a redirection to home decor items.

```python
# shopsense/guardrails/input_checks.py
check = check_input(user_query)
if not check.allowed:
    return AgentResponse(
        answer=check.user_message,
        product_ids=[],
        no_results=True,
        retrieval_method="none",
    ), []
```

### 2. Post-Retrieval Output Guardrails (`shopsense/guardrails/output_checks.py`)
Runs on candidate products before they can be displayed:

1. **Database Identity Grounding (`verify_product_ids`)**:
   - Cross-references every retrieved ID against SQLite (`SELECT product_id FROM products WHERE product_id IN (...)`).
   - Completely eliminates hallucinated product IDs or corrupted references.
2. **Deterministic Constraint Enforcement (`verify_products_against_constraints`)**:
   - Re-verifies every candidate product against numerical bounds:
     - `price <= max_price`
     - `average_rating >= min_rating`
     - `width_cm <= max_width_cm`
     - `height_cm <= max_height_cm`
   - If any product violates a hard constraint, it is stripped from recommendations before the UI renders.

---

## 🤖 Model Specification: `gemini-3.1-flash-lite`

ShopSense AI is configured to use Google's **`gemini-3.1-flash-lite`** for high-efficiency, low-latency structured output and generation:
- **Fast Structured Parsing**: Powers Stage A query understanding, converting natural language into a validated Pydantic `ShoppingIntent`.
- **Grounded Response Generation**: Powers Stage B natural language responses, receiving only catalog-verified product context.
- **Comparison Trade-Off Summaries**: Summarizes numerical trade-offs (price gaps, dimension differences) computed by Python.

---

## 📂 Project Directory Structure

```text
products_finder_agent/
├── app.py                             # Main Streamlit entrypoint & home overview
├── pages/
│   ├── 1_Chat.py                      # Conversational AI shopping assistant
│   ├── 2_Product_Search.py            # Deterministic catalog search & filters
│   ├── 3_Compare_Products.py          # Side-by-side product comparison workspace
│   └── 4_Evaluation_Dashboard.py      # Real 20-case benchmark evaluation dashboard
├── shopsense/
│   ├── agent/
│   │   ├── prompts.py                 # Grounded LangChain ChatPromptTemplates
│   │   └── shopping_agent.py          # 5-stage orchestration pipeline
│   ├── catalog/
│   │   ├── loader.py                  # Read-only SQLite connection & model mapping
│   │   └── search.py                  # Hard filters, keyword ranking & semantic search
│   ├── evaluation/
│   │   ├── metrics.py                 # Precision@K, Recall@K, aggregate calculations
│   │   └── runner.py                  # Benchmark case runner & report persistence
│   ├── guardrails/
│   │   ├── input_checks.py            # Pre-LLM deterministic input checks
│   │   └── output_checks.py           # Post-retrieval validation & constraint checker
│   ├── ui/
│   │   ├── components.py              # Product cards, metric widgets, empty states
│   │   └── styles.py                  # Shared CSS design tokens & sidebar branding
│   ├── config.py                      # Config loader (default: gemini-3.1-flash-lite)
│   └── schemas.py                     # Pydantic v2 schemas (Product, ShoppingIntent)
├── data/
│   ├── products.db                    # SQLite product database (verified schema)
│   └── evaluation_cases.json          # 20 curated benchmark test cases
├── reports/
│   └── evaluation_results.json        # Evaluation execution outcomes & metrics
├── tests/
│   ├── test_catalog.py                # Database connection, schemas, and filters
│   ├── test_guardrails.py             # Input and output guardrail test suite
│   ├── test_agent.py                  # Shopping pipeline & fallback unit tests
│   └── test_evaluation.py             # Evaluation metrics and file immutability tests
├── .streamlit/
│   └── config.toml                    # Streamlit theme & UI settings
├── .env.example                       # Documented environment template
├── requirements.txt                   # Dependency list
└── pyproject.toml                     # Project packaging & pytest configuration
```

---

## 🚀 Quickstart Guide

### 1. Installation
```bash
# Clone the repository and enter the directory
cd products_finder_agent

# Set up virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Set your Google Gemini API key:
```ini
GOOGLE_API_KEY=your_google_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite
```

> **Offline Mode**: If `GOOGLE_API_KEY` is not provided, ShopSense AI automatically runs in deterministic catalog fallback mode using SQLite queries and regex parsing.

### 3. Launch the Application
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 🧪 Automated Testing

Run the full automated test suite:
```bash
pytest tests/ -v
```
All **31 unit tests** pass without requiring a live Gemini API key:
- Database connectivity & schema validation
- String product ID preservation
- Parameterized SQL execution
- Price, category, and dimension filters
- Input guardrails (empty, length, harmful content, injections, out-of-scope)
- Output guardrails (unverified ID removal, constraint validation)
- Structured ShoppingIntent parsing and fallback behavior
- Evaluation metric calculation (Recall@5, Precision@5) and benchmark file immutability

---

## 📊 Live 20-Case Benchmark Evaluation

ShopSense AI includes an evaluation benchmark in `data/evaluation_cases.json` covering:
- Direct product search & keyword retrieval
- Budget filtering & dimension tolerance
- Category navigation & semantic queries
- Out-of-scope domain refusals
- Safety & dangerous request handling
- Prompt injection protection

### Metric Definitions
- **Recall@5**: Percentage of expected ground-truth product IDs retrieved in the top 5 results.
- **Precision@5**: Proportion of top-5 retrieved products that match ground-truth IDs.
- **Guardrail Pass Rate**: Percentage of safety and injection test cases correctly intercepted and refused.
- **Constraint Satisfaction**: Verification that 100% of returned items satisfy stated price and size constraints.

To run the benchmark on demand:
```bash
python -c "from shopsense.evaluation.runner import run_evaluation; print(run_evaluation()['summary'])"
```
Or click **Run Evaluation Suite Now** on the **Evaluation Dashboard** page (`pages/4_Evaluation_Dashboard.py`).

---

## ☁️ Deployment (Streamlit Community Cloud)

1. Push your code to GitHub.
2. Sign in to [share.streamlit.io](https://share.streamlit.io).
3. Click **New app** and select your repository, branch `main`, and main file `app.py`.
4. In **Advanced settings → Secrets**, paste:
   ```toml
   GOOGLE_API_KEY = "AIzaSy..."
   GEMINI_MODEL = "gemini-3.1-flash-lite"
   ```
5. Click **Deploy**!
