"""Generate AI-powered cost brief using Claude."""

from __future__ import annotations

import json
from typing import Optional

from .models import TeamReport


def _build_prompt(report: TeamReport) -> str:
    """Serialize a TeamReport into a concise prompt payload."""
    period = "all time"
    if report.period_start and report.period_end:
        period = f"{report.period_start.date()} to {report.period_end.date()}"

    eng_lines = []
    for e in report.engineers[:10]:
        top_proj = sorted(e.project_breakdown.items(), key=lambda x: x[1], reverse=True)[:3]
        proj_str = ", ".join(f"{p}: ${c:.2f}" for p, c in top_proj)
        eng_lines.append(
            f"  - {e.engineer}: ${e.total_cost_usd:.2f} | "
            f"sessions={e.session_count} | cache_eff={e.cache_efficiency:.0%} | "
            f"projects=[{proj_str}]"
        )

    model_lines = [
        f"  - {m}: ${c:.2f} ({c/report.total_cost_usd:.0%})"
        for m, c in sorted(report.model_breakdown.items(), key=lambda x: x[1], reverse=True)
    ]

    return f"""You are an engineering cost analyst for a software team using Claude Code (Anthropic's AI coding assistant).

Here is the team's usage summary for {period}:

TEAM TOTALS
  Total spend: ${report.total_cost_usd:.2f}
  Sessions: {report.total_sessions}
  Turns (API calls): {report.total_turns}
  Engineers: {report.engineer_count}
  Cache efficiency: {report.cache_efficiency_pct:.1f}% (higher = better, reduces costs)

PER-ENGINEER BREAKDOWN (top spenders first)
{chr(10).join(eng_lines)}

MODEL BREAKDOWN
{chr(10).join(model_lines)}

Generate a concise weekly Cost Intelligence Brief for the engineering leader. Structure it exactly as follows:

## Cost Intelligence Brief — {period}

### Executive Summary
[2-3 sentence narrative of the week's spend. Mention total, trend direction (if obvious), biggest driver.]

### Top 3 Cost Drivers
[Rank the three biggest contributors to spend — could be engineers, projects, or models — with specific dollar amounts and percentages.]

### Optimization Recommendations
[Exactly 3 actionable recommendations with estimated savings. Each must include:
- What to change (specific and concrete, not vague)
- Why it will reduce cost (mechanism)
- Estimated savings ($X or X% reduction)

Focus on cache efficiency improvements, model selection optimization, and session hygiene if applicable.]

### Efficiency Score
[Rate the team's current cost efficiency as: Excellent / Good / Needs Improvement / Poor.
Benchmark: cache efficiency >40% = Good, model mix mostly Sonnet/Haiku = Good.
One sentence justification.]

Keep the entire brief under 400 words. Be specific and concrete — numbers, not generalities."""


def generate_brief(report: TeamReport, api_key: Optional[str] = None) -> str:
    """Call Claude to generate a cost brief. Returns the brief as a string."""
    try:
        import anthropic
    except ImportError:
        return (
            "[Cost brief unavailable — install anthropic: pip install anthropic]\n\n"
            + _fallback_brief(report)
        )

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    prompt = _build_prompt(report)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=(
            "You are a concise, data-driven engineering cost analyst. "
            "Follow the output structure exactly. No padding, no hedging."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text


def _fallback_brief(report: TeamReport) -> str:
    """Rule-based brief when Claude API is unavailable."""
    lines = [
        "## Cost Intelligence Brief (offline mode)\n",
        f"**Total spend**: ${report.total_cost_usd:.2f} across {report.total_sessions} sessions",
        f"**Engineers**: {report.engineer_count}",
        f"**Cache efficiency**: {report.cache_efficiency_pct:.1f}%",
        "",
    ]

    if report.engineers:
        top = report.engineers[0]
        pct = top.total_cost_usd / report.total_cost_usd * 100 if report.total_cost_usd > 0 else 0
        lines.append(
            f"**Top spender**: {top.engineer} — ${top.total_cost_usd:.2f} ({pct:.0f}% of team total)"
        )

    if report.cache_efficiency_pct < 20:
        lines.append(
            "\n**Recommendation**: Cache efficiency is low. "
            "Add `--resume` flags to long sessions or break work into fewer, longer sessions."
        )

    if report.model_breakdown:
        expensive = [m for m in report.model_breakdown if "opus" in m.lower()]
        if expensive:
            lines.append(
                "\n**Recommendation**: Opus usage detected. "
                "Switch exploratory/drafting work to Sonnet to reduce costs by ~5x on those tasks."
            )

    return "\n".join(lines)
