<div align="center">

# jobpilot

**Turn a messy job posting into a tracked application, in one command.**

[![CI](https://github.com/MuhammadAbuBakar69/jobpilot/actions/workflows/ci.yml/badge.svg)](https://github.com/MuhammadAbuBakar69/jobpilot/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-3DA639)

</div>

Most job hunts die in a spreadsheet nobody updates. `jobpilot` takes the raw text
of a posting (an email, a WhatsApp forward, a scraped page) and turns it into a
structured record: company, role, salary band, deadline, stack, contact. It runs
entirely offline by default, and uses an LLM only when you ask it to.

```console
$ jobpilot add posting.txt
added #1: Senior Frontend Engineer @ Northwind Labs
  deadline: 2026-12-15
  skills:   figma, next.js, node.js, react, tailwind, typescript

$ jobpilot stats
total applications : 12
  applied      7
  interview    2
  rejected     2
  offer        1
response rate      : 41.7%
most requested     : react (9), typescript (7), node.js (5), figma (4), docker (2)
next deadline      : 2026-12-15 - Senior Frontend Engineer @ Northwind Labs
```

## Why it exists

Parsing a posting is the tedious part of applying, and the record you need later
(what did they pay? when did I apply? did they answer?) is exactly what gets lost.
This keeps one SQLite file you own, plus a REST API for anything else you want to
point at it.

## Design

```
     raw text
        |
        v
  +-------------+   no key / API error    +-------------+
  |  extract.py | ----------------------> | heuristic   |
  |  parse_*()  |                         | regex pass  |
  +-------------+ <---------------------- +-------------+
        |                  always works
        v
  +-------------+        +----------------+
  |   db.py     | <----> | applications   |  sqlite, deduped by url/company+role
  +-------------+        +----------------+
        |
        +--> cli.py  (argparse, no extra deps)
        +--> api.py  (FastAPI: /applications, /stats)
```

Two decisions worth calling out:

- **The LLM is optional and never trusted blindly.** `parse_with_llm` validates the
  JSON, keeps only integers for salary, and merges against the heuristic result, so
  a hallucinated field falls back to what the regexes actually found.
- **Deduplication is by fingerprint.** Re-importing the same posting is a no-op
  instead of a duplicate row.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

jobpilot add posting.txt        # or: pbpaste | jobpilot add
jobpilot list
jobpilot move 1 interview
jobpilot stats

jobpilot serve --port 8000      # http://127.0.0.1:8000/docs
```

### With an LLM extractor

Off by default. Set a key and pass `--llm`:

```bash
cp .env.example .env
export FASTROUTER_API_KEY=...        # or OPENAI_API_KEY
jobpilot add posting.txt --llm
```

Any OpenAI-compatible endpoint works. `resolve_llm_config()` picks the target from
the environment:

| Variable | Effect |
| :--- | :--- |
| `FASTROUTER_API_KEY` | key + `https://api.fastrouter.ai/api/v1`, model defaults to `openai/gpt-4o-mini` |
| `OPENAI_API_KEY` | key + `https://api.openai.com/v1`, model defaults to `gpt-4o-mini` |
| `OPENAI_BASE_URL` | overrides the base URL (Azure, Groq, Ollama, a local gateway) |
| `JOBPILOT_MODEL` | overrides the model id |

FastRouter namespaces its model ids (`openai/gpt-4o-mini`,
`anthropic/claude-haiku-5.5`), which is why the default flips when that key is
present. A token shaped like a GitHub token (`ghp_...`) is refused outright rather
than sent to a model provider. If the call fails or the model returns something
unusable, the heuristic parser handles the posting instead. No keys are committed
to this repo.

## API

| Method | Path | Body |
| :--- | :--- | :--- |
| `GET` | `/health` | - |
| `GET` | `/applications?status=&limit=` | - |
| `POST` | `/applications` | `{"text": "...", "use_llm": false}` |
| `PATCH` | `/applications/{id}` | `{"status": "interview"}` |
| `GET` | `/stats` | - |

Statuses: `applied`, `screening`, `interview`, `offer`, `rejected`, `ghosted`.

## Tests

```bash
pytest        # 24 tests, no network, no keys
ruff check .
```

CI runs both on Python 3.10, 3.11 and 3.12 for every push and pull request.

## Roadmap

- [ ] Email ingest (IMAP) so application confirmations file themselves
- [ ] Follow-up reminders for applications with no reply after N days
- [ ] CSV export for spreadsheet people

## License

MIT
