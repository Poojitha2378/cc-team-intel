"""FastAPI server — accepts JSONL uploads, serves aggregated reports."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse

from .aggregator import build_team_report
from .brief import generate_brief
from .models import TeamReport
from .storage import get_upload_dir, iter_records_from_upload_dir

app = FastAPI(
    title="cc-team-intel",
    description="Team-level Claude Code cost intelligence for engineering leaders.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = get_upload_dir()


# ---------------------------------------------------------------------------
# Upload endpoint (used by the `ccti submit` CLI command)
# ---------------------------------------------------------------------------


@app.post("/upload/{engineer}", summary="Upload a JSONL session file")
async def upload_jsonl(
    engineer: str,
    file: UploadFile = File(...),
):
    """
    Upload a Claude Code JSONL session file for a named engineer.

    The file is stored under CCTI_DATA_DIR/uploads/<engineer>/<filename>.
    """
    if not file.filename or not file.filename.endswith(".jsonl"):
        raise HTTPException(status_code=400, detail="Only .jsonl files accepted")

    dest_dir = UPLOAD_DIR / engineer
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.filename

    contents = await file.read()
    dest.write_bytes(contents)

    return {"status": "ok", "stored": str(dest)}


# ---------------------------------------------------------------------------
# Report endpoints
# ---------------------------------------------------------------------------


@app.get("/report", response_model=TeamReport, summary="Full team cost report (JSON)")
def get_report(
    since: Optional[str] = None,
    until: Optional[str] = None,
    brief: bool = False,
):
    """
    Return the aggregated team cost report.

    - **since**: ISO date filter start (e.g. 2025-05-01)
    - **until**: ISO date filter end (e.g. 2025-05-31)
    - **brief**: if true, generate and attach the AI cost brief (requires ANTHROPIC_API_KEY)
    """
    records = list(iter_records_from_upload_dir(UPLOAD_DIR))
    if not records:
        raise HTTPException(status_code=404, detail="No data uploaded yet. Use `ccti submit` first.")

    period_start = datetime.fromisoformat(since).replace(tzinfo=timezone.utc) if since else None
    period_end = datetime.fromisoformat(until).replace(tzinfo=timezone.utc) if until else None

    report = build_team_report(records, period_start=period_start, period_end=period_end)

    if brief:
        report.cost_brief = generate_brief(report)

    return report


@app.get("/report/html", response_class=HTMLResponse, summary="Human-readable HTML report")
def get_html_report(since: Optional[str] = None, until: Optional[str] = None, brief: bool = False):
    """Render a simple HTML cost report for sharing in email or Slack."""
    try:
        report = get_report(since=since, until=until, brief=brief)
    except HTTPException as e:
        return HTMLResponse(content=f"<p>{e.detail}</p>", status_code=e.status_code)

    period = "all time"
    if report.period_start and report.period_end:
        period = f"{report.period_start.date()} – {report.period_end.date()}"

    eng_rows = "".join(
        f"<tr><td>{e.engineer}</td><td>${e.total_cost_usd:.2f}</td>"
        f"<td>{e.session_count}</td><td>{e.cache_efficiency:.0%}</td></tr>"
        for e in report.engineers
    )

    brief_html = ""
    if report.cost_brief:
        import re
        brief_html = f"<section><h2>AI Cost Brief</h2><pre>{report.cost_brief}</pre></section>"

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>cc-team-intel — {period}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #1a1a2e; }}
    h1 {{ color: #e94560; }}
    h2 {{ color: #16213e; border-bottom: 2px solid #e94560; padding-bottom: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 32px; }}
    th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #ddd; }}
    th {{ background: #16213e; color: #fff; }}
    .stat {{ display: inline-block; background: #f8f9fa; border-radius: 8px; padding: 12px 20px; margin: 8px; text-align: center; }}
    .stat-num {{ font-size: 2em; font-weight: bold; color: #e94560; }}
    pre {{ background: #f8f9fa; padding: 16px; border-radius: 8px; white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>cc-team-intel</h1>
  <p>Cost report for <strong>{period}</strong> · Generated {report.generated_at.strftime("%Y-%m-%d %H:%M UTC")}</p>

  <div>
    <div class="stat"><div class="stat-num">${report.total_cost_usd:.2f}</div>Total spend</div>
    <div class="stat"><div class="stat-num">{report.engineer_count}</div>Engineers</div>
    <div class="stat"><div class="stat-num">{report.total_sessions}</div>Sessions</div>
    <div class="stat"><div class="stat-num">{report.cache_efficiency_pct:.0f}%</div>Cache efficiency</div>
  </div>

  <h2>Per-Engineer Breakdown</h2>
  <table>
    <thead><tr><th>Engineer</th><th>Spend</th><th>Sessions</th><th>Cache eff.</th></tr></thead>
    <tbody>{eng_rows}</tbody>
  </table>

  {brief_html}

  <p style="color:#999;font-size:0.85em">Generated by <a href="https://github.com/Poojitha2378/cc-team-intel">cc-team-intel</a></p>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/brief", summary="AI-generated cost brief (markdown)")
def get_brief():
    """Return just the AI cost brief as plain markdown text."""
    records = list(iter_records_from_upload_dir(UPLOAD_DIR))
    if not records:
        raise HTTPException(status_code=404, detail="No data uploaded yet.")
    report = build_team_report(records)
    return {"brief": generate_brief(report)}


@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}
