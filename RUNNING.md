# Running SchemeLogic

Two frontends exist side by side. Neither depends on the other.

## Next.js + FastAPI (new, primary for tomorrow's demo)

Two commands, two terminals, from the repo root:

```bash
# Terminal 1 -- backend (port 8000)
PYTHONPATH=. python -m uvicorn api.main:app --reload --port 8000
```

```bash
# Terminal 2 -- frontend (port 3000)
cd frontend && npm run dev
```

Open http://localhost:3000. The frontend reads the backend URL from `frontend/.env.local`
(`NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`) -- change that if you run the API on a
different port.

First message/selection after a fresh backend restart is slow (~1-2 min): it cold-builds the
~2073-scheme embedding index once, in-process, then it's cached for the rest of that server's
life (same one-time cost the Streamlit app always had).

## Streamlit (fallback, still fully working, untouched)

```bash
PYTHONPATH=. streamlit run schemelogic/conversational/app.py
```

Open the URL Streamlit prints (defaults to http://localhost:8501).

## Tests

```bash
python -m pytest -q
```

Runs everything, including `tests/test_api.py` (the new FastAPI layer) alongside every existing
test — all pass unmodified; the migration added a new layer, it didn't touch the old one.
