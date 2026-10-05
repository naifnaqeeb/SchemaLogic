# SchemeLogic

SchemeLogic turns Indian welfare-scheme documents into executable eligibility rules and checks
citizens against them. An LLM **only extracts** the rules. A deterministic symbolic evaluator
**decides** every verdict and records a full trace of the rules it applied. The LLM never decides
whether anyone is eligible.

It is a B.Tech final-year research project (VIT, BITE497J). The research questions are in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) §1 (C1–C5), and the measured results are in
[RESULTS.md](RESULTS.md).

## What it does

- **Extraction**: a scheme document goes in and a `Scheme` comes out. That is a typed rule tree:
  inclusion AND/OR, exclusions with family quantifiers, exceptions to exclusions, temporal validity
  with `supersedes`, and a category tag on each predicate. The extractor
  ([schemelogic/extraction/extractor.py](schemelogic/extraction/extractor.py)) uses `openai/gpt-oss-120b`
  through Groq with structured output, in two calls: rules, then metadata.
- **Judge, repair and gate**: an LLM judge reports implied facts the draft missed, and temporal
  supersessions ([judge_repair.py](schemelogic/extraction/judge_repair.py)). A calibration gate
  ([calibration_gate.py](schemelogic/deferral/calibration_gate.py)) applies a finding only when
  its quote is verbatim in the source and its confidence clears the threshold. Otherwise it defers
  the finding to a person.
- **Evaluator**: [symbolic_engine.py](schemelogic/evaluator/symbolic_engine.py) gives eligible /
  ineligible / undetermined, with a trace. A missing fact gives "undetermined", never a guess.
- **Chat app**: a citizen describes their situation, and the app finds schemes and asks only the
  questions the rules need. It explains the verdict from the trace. Schemes come in three tiers:
  - **Verified**: 7 schemes with hand-audited gold rules.
  - **AI-Checked**: rules extracted live, labelled as such.
  - **Description only**: about 2,066 schemes scraped from myScheme.

  The app works in English, Hindi, Urdu (right to left), Marathi and Tamil. It is English
  internally and translates at the edges. The non-English strings are machine translations, not yet
  reviewed ([docs/i18n/](docs/i18n/)).

## How to run

Requirements: Python 3.11+, Node.js (developed on 22), and a `GROQ_API_KEY` in `.env`. `OPENROUTER_API_KEY` is
optional and only used as the chat's fallback provider. `.env` is gitignored, so never commit it.

```bash
pip install -e ".[dev]"                                       # dependencies from pyproject.toml
PYTHONPATH=. python -m uvicorn api.main:app --port 8000      # backend
cd frontend && npm install && npm run dev                     # frontend, http://localhost:3000
python -m pytest -q                                           # tests (no network)
```

[RUNNING.md](RUNNING.md) has the details, including the Streamlit fallback UI. The first request
after a backend start builds the discovery index, which takes 1–2 minutes.

Experiments run against the gold frozen at git tag `gold-v2`. They are paced under Groq's
free-tier limits (8k tokens/min, about 200k tokens per rolling 24 hours) and resume where they
stopped:

```bash
PYTHONPATH=. python scripts/run_queue.py day2              # or day3, day4; several in order
PYTHONPATH=. python scripts/run_batch_report.py            # offline: docs/results/BATCH_REPORT.md
```

Every result file records the gold tag, provider, model, config, date and measured token usage.
The token ledger is `data/experiments/token_ledger.jsonl`.

## Layout

| Path | What |
|---|---|
| `schemelogic/schema/` | `Scheme` model; field ontology (canonical citizen-fact fields and their questions) |
| `schemelogic/extraction/` | extractor; judge and repair |
| `schemelogic/deferral/` | calibration gate |
| `schemelogic/evaluator/` | symbolic engine (the only thing that decides a verdict) |
| `schemelogic/evaluation/` | structural F1, outcome equivalence, scalar checks, Baselines 1 and 2 |
| `schemelogic/experiments/` | harness (frozen gold, ledger, pacing); injected-error corpus |
| `schemelogic/conversational/` | chat engine, router, question selector, session, messages catalogue (i18n) |
| `schemelogic/retrieval/`, `discovery/` | temporal retrieval for the judge; scheme search |
| `api/`, `frontend/` | FastAPI backend; Next.js frontend |
| `data/gold/`, `data/profiles/` | 7 gold schemes and their test profiles |
| `data/experiments/` | every experiment result; `docs/results/` has the generated reports |
| `scripts/` | runners and analyses (all experiments are reproducible from here) |

## Honest status

- **Small benchmark.** There are 7 gold schemes. Every gold scheme was audited against primary
  sources ([docs/GOLD_AUDIT_2026-10-03.md](docs/GOLD_AUDIT_2026-10-03.md)). The same team built the
  gold, the extractor's field ontology and the test profiles. Results on this benchmark are
  therefore optimistic: the ontology was shaped by the same schemes.
- **Experiments are small samples.** They ran on Groq's free tier: k=3 self-consistency, about 30
  injected errors for the gate, and k=1 per pre-amendment text in the temporal study. Each report
  says so beside its numbers.
- **Several earlier claims were withdrawn** after the gold audit, and RESULTS.md lists them.
  Before 2026-10-03, any number in a commit message or note may be stale.
- **The judge's findings come in only two kinds**: a missing implied fact, or a temporal
  supersession. It cannot flag a rule that is present but wrong, so that kind of error depends on
  other signals, such as agreement across samples.
- **Translations are unreviewed** machine translations, with English as the fallback.
- Open issues: [KNOWN_ISSUES.md](KNOWN_ISSUES.md). The current push and its log:
  [docs/PLAN_FINAL_PUSH.md](docs/PLAN_FINAL_PUSH.md).
