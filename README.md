# cc-team-intel 

**Team-level Claude Code cost intelligence for engineering leaders.**

> Every other tool tracks *your* Claude Code spend. This one tracks *your team's* — and tells you what to do about it.

[![CI](https://github.com/Poojitha2378/cc-team-intel/actions/workflows/ci.yml/badge.svg)](https://github.com/Poojitha2378/cc-team-intel/actions)
[![PyPI](https://img.shields.io/pypi/v/cc-team-intel)](https://pypi.org/project/cc-team-intel/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

---

## Why this exists

Tools like [ccusage](https://github.com/ryoppippi/ccusage) and [ccost](https://github.com/cc-friend/ccost) are excellent for individual developers. But engineering managers have no visibility into aggregate spend across their team. And nobody has built the AI-powered recommendation layer: *"Your team's cache efficiency is 12% — here are 3 specific changes that would cut your bill by 40%."*

`cc-team-intel` fills both gaps:

- **Team aggregation** — roll up JSONL files from multiple engineers into one report
- **AI cost brief** — Claude analyzes the data and generates actionable optimization recommendations
- **Zero new infrastructure** — reads the same `~/.claude/projects/*.jsonl` files Claude Code already writes

---

## What it looks like

```
┌─────────────────────────────────────────────────────────────────────┐
│ cc-team-intel  |  2025-05-01 – 2025-05-31                          │
│ Total spend: $847.32  Engineers: 8  Sessions: 312  Cache eff: 18%  │
└─────────────────────────────────────────────────────────────────────┘

Per-Engineer Breakdown
┌──────────────┬──────────┬──────────┬───────┬────────────┬──────────────────────┐
│ Engineer     │ Spend    │ Sessions │ Turns │ Cache eff. │ Top model            │
├──────────────┼──────────┼──────────┼───────┼────────────┼──────────────────────┤
│ alice        │ $234.17  │ 87       │ 1,204 │ 31%        │ claude-sonnet-4-6    │
│ bob          │ $198.44  │ 62       │ 891   │ 8%         │ claude-opus-4-7      │
│ carol        │ $156.92  │ 73       │ 1,012 │ 42%        │ claude-sonnet-4-6    │
│ ...          │ ...      │ ...      │ ...   │ ...        │ ...                  │
└──────────────┴──────────┴──────────┴───────┴────────────┴──────────────────────┘

╔══════════════════════════════════════════════════════╗
║  AI Cost Brief                                       ║
╠══════════════════════════════════════════════════════╣
║  ## Cost Intelligence Brief — May 2025              ║
║                                                      ║
║  ### Executive Summary                              ║
║  Team spent $847 this month, up 23% from April.    ║
║  Bob's Opus usage accounts for 38% of total spend  ║
║  despite representing only 23% of sessions.        ║
║                                                      ║
║  ### Optimization Recommendations                   ║
║  1. Switch Bob's exploratory sessions to Sonnet    ║
║     (~$75/month savings, 5x model cost difference) ║
║  2. Enable prompt caching for the auth-service     ║
║     project (cache hit rate 2% vs team avg 18%)    ║
║  3. Break alice's 6h marathon sessions into        ║
║     smaller chunks to improve cache reuse          ║
╚══════════════════════════════════════════════════════╝
```

---

## Installation

```bash
pip install cc-team-intel
```

With the HTTP server (for team deployments):

```bash
pip install "cc-team-intel[server]"
```

With S3 backend:

```bash
pip install "cc-team-intel[server,s3]"
```

---

## Quick start

### Single developer (no server needed)

Analyze your own `~/.claude` usage instantly:

```bash
ccti self
ccti self --since 2025-05-01 --until 2025-05-31
ccti self --brief   # adds AI cost brief (needs ANTHROPIC_API_KEY)
```

### Team setup

**Step 1 — Start the server** (on a shared machine or internal server):

```bash
ccti serve
# or with Docker:
docker-compose up -d
```

**Step 2 — Each engineer submits their data** (run from their own machine):

```bash
ccti submit --server http://your-server:8000
```

**Step 3 — View the team report**:

```bash
ccti report --brief
```

Or open the HTML report in a browser:

```
http://your-server:8000/report/html?brief=true
```

---

## CLI reference

| Command | Description |
|---|---|
| `ccti self` | Analyze your own `~/.claude` usage |
| `ccti self --brief` | Add AI cost brief to your report |
| `ccti submit` | Upload your JSONL files to the team server |
| `ccti submit --local` | Write to local shared directory instead |
| `ccti report` | View team report from uploaded data |
| `ccti report --since YYYY-MM-DD` | Filter by date range |
| `ccti report --brief` | Include AI cost brief |
| `ccti report --json-out` | Output raw JSON (for piping/dashboards) |
| `ccti serve` | Start the HTTP server |

---

## Deployment options

### Option A — Shared filesystem

If your team has a shared filesystem (NFS, Samba, shared Docker volume):

```bash
# Each engineer runs this locally
ccti submit --local --data-dir /shared/cc-team-intel/uploads

# Manager runs this on the shared machine
ccti report --data-dir /shared/cc-team-intel/uploads --brief
```

### Option B — HTTP server (Docker)

```bash
# On your server
ANTHROPIC_API_KEY=sk-ant-... docker-compose up -d

# Each engineer runs locally
ccti submit --server http://your-server:8000

# View report
open http://your-server:8000/report/html?brief=true
```

### Option C — S3 bucket

Upload JSONL files to S3 with the layout `s3://bucket/prefix/<engineer>/<session>.jsonl`.

```python
from cc_team_intel.storage import try_s3_iter
from cc_team_intel.aggregator import build_team_report

records = list(try_s3_iter("my-bucket", prefix="claude-logs/"))
report = build_team_report(records)
print(report.total_cost_usd)
```

---

## HTTP API

When running `ccti serve`, the following endpoints are available:

| Endpoint | Method | Description |
|---|---|---|
| `POST /upload/{engineer}` | POST | Upload a JSONL file for an engineer |
| `GET /report` | GET | Full team report (JSON) |
| `GET /report/html` | GET | Human-readable HTML report |
| `GET /brief` | GET | AI cost brief only (markdown) |
| `GET /health` | GET | Health check |

Query params for `/report` and `/report/html`:
- `since=YYYY-MM-DD` — filter start date
- `until=YYYY-MM-DD` — filter end date
- `brief=true` — generate AI cost brief (requires `ANTHROPIC_API_KEY`)

Interactive API docs: `http://your-server:8000/docs`

---

## How it works

Claude Code writes a JSONL file per session to `~/.claude/projects/<project-hash>/*.jsonl`. Each line is a conversation turn. `cc-team-intel`:

1. **Parses** every `assistant`-type record, extracting token counts (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`) and the model name.
2. **Computes cost** using Anthropic's published per-token pricing for each model.
3. **Aggregates** by session → engineer → project → team.
4. **Generates** an AI cost brief by feeding the aggregated data to Claude and asking for specific, actionable optimization recommendations with estimated savings.

### Pricing table

| Model | Input | Output | Cache read | Cache write |
|---|---|---|---|---|
| claude-opus-4-7 | $15/MTok | $75/MTok | $1.50/MTok | $18.75/MTok |
| claude-sonnet-4-6 | $3/MTok | $15/MTok | $0.30/MTok | $3.75/MTok |
| claude-haiku-4-5 | $0.80/MTok | $4/MTok | $0.08/MTok | $1/MTok |

---

## Library usage

```python
from cc_team_intel.parser import iter_records_from_claude_home
from cc_team_intel.aggregator import build_team_report
from cc_team_intel.brief import generate_brief

# Analyze your own data
records = list(iter_records_from_claude_home(engineer="alice"))
report = build_team_report(records)

print(f"Total spend: ${report.total_cost_usd:.2f}")
print(f"Cache efficiency: {report.cache_efficiency_pct:.1f}%")

# Generate AI brief (needs ANTHROPIC_API_KEY in environment)
brief = generate_brief(report)
print(brief)
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `CCTI_DATA_DIR` | `~/.cc-team-intel` | Local data storage directory |
| `ANTHROPIC_API_KEY` | — | Required for AI cost brief generation |
| `AWS_ACCESS_KEY_ID` | — | S3 backend (optional) |
| `AWS_SECRET_ACCESS_KEY` | — | S3 backend (optional) |

---

## Development

```bash
git clone https://github.com/Poojitha2378/cc-team-intel
cd cc-team-intel
pip install -e ".[dev,server]"
pytest
ruff check .
```

---

## Roadmap

- [ ] Slack/email weekly digest
- [ ] Per-project budget alerts
- [ ] GitHub Actions integration (post cost summary on PRs)
- [ ] Grafana dashboard JSON export
- [ ] Cost anomaly detection

---

## Related tools

- [ccusage](https://github.com/ryoppippi/ccusage) — the community standard single-developer tracker (supports 14+ tools)
- [ccost](https://github.com/cc-friend/ccost) — Rust CLI + desktop app with nested session view
- [claude-token-analyzer](https://github.com/li195111/claude-token-analyzer) — anomaly detection plugin

`cc-team-intel` is intentionally additive, not competitive. Use `ccusage` for your individual view, `cc-team-intel` for your team's.

---

## License

MIT — see [LICENSE](LICENSE).
