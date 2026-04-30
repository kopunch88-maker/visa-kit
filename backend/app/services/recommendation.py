"""
Recommendation service — match applicant to company+position using LLM.

Strategy: send applicant CV summary + descriptions of all active Positions
to Claude (via Anthropic API), ask for top-3 matches with scores and reasoning.

Result is structured JSON which the admin UI displays as recommendation cards.
Manager makes the final call.

Cost: ~$0.01-0.02 per recommendation (Claude Haiku is enough for this).
Latency: 3-5 seconds.
"""

import json
import os
from typing import List, Sequence

from anthropic import AsyncAnthropic

from app.models import Applicant, Position


# Initialized lazily to avoid import-time failure if no API key
_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _client = AsyncAnthropic(api_key=api_key)
    return _client


SYSTEM_PROMPT = """You are an HR matching assistant for a visa-services company.

Given:
- A candidate profile (CV-style: education, work history, languages)
- A list of available positions, each with title, duties, and a description of
  the ideal candidate

Return the TOP 3 best-matching positions, ranked. For each:
- position_id (the integer ID provided)
- score (0-100 confidence that this is a good match)
- reasoning (2-3 sentences in Russian, explaining the match for a Russian-speaking manager)

Match on:
- Specialty alignment (geodesy expert → geodesy position)
- Years of experience meeting position requirements
- Education relevance
- Language skills if relevant

Return ONLY a JSON object, no markdown, no preamble. Schema:
{
  "matches": [
    {"position_id": int, "score": int, "reasoning": str},
    ...
  ]
}
"""


def _summarize_applicant(applicant: Applicant) -> str:
    """Compact applicant profile for LLM input."""
    edu = "; ".join(
        f"{e.get('degree', '')} {e.get('specialty', '')} ({e.get('institution', '')}, "
        f"{e.get('graduation_year', '?')})"
        for e in applicant.education
    ) or "no education on file"

    work = []
    for w in applicant.work_history:
        duties = "; ".join(w.get("duties", []))
        work.append(
            f"{w.get('period_start', '?')} - {w.get('period_end', '?')}: "
            f"{w.get('position', '?')} at {w.get('company', '?')}. {duties}"
        )
    work_str = "\n".join(work) or "no work history on file"

    langs = ", ".join(applicant.languages) or "not specified"

    return (
        f"Name: {applicant.first_name_native} {applicant.last_name_native}\n"
        f"Nationality: {applicant.nationality}\n"
        f"Education: {edu}\n"
        f"Work history:\n{work_str}\n"
        f"Languages: {langs}"
    )


def _summarize_positions(positions: Sequence[Position]) -> str:
    """Compact list of positions for LLM input."""
    lines = []
    for p in positions:
        duties = "; ".join(p.duties[:5])  # cap to avoid bloated prompt
        lines.append(
            f"- ID {p.id}: \"{p.title_ru}\". "
            f"Tags: {', '.join(p.tags)}. "
            f"Profile: {p.profile_description}. "
            f"Sample duties: {duties}"
        )
    return "\n".join(lines)


async def recommend_position(
    applicant: Applicant,
    positions: Sequence[Position],
) -> dict:
    """
    Run LLM to get top-3 position matches for this applicant.

    Returns:
        {
            "matches": [
                {"position_id": 5, "score": 94, "reasoning": "..."},
                {"position_id": 7, "score": 62, "reasoning": "..."},
                ...
            ],
            "top_match": { ... first item, with extra fields ... },
            "model": "claude-haiku-4-5",
            "applicant_summary": "...",  # for audit
        }
    """
    client = _get_client()

    applicant_summary = _summarize_applicant(applicant)
    positions_summary = _summarize_positions(positions)

    user_message = (
        f"=== CANDIDATE ===\n{applicant_summary}\n\n"
        f"=== AVAILABLE POSITIONS ===\n{positions_summary}\n\n"
        "Return the top 3 matches as JSON."
    )

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = response.content[0].text.strip()
    # Strip ```json fences if Claude added them despite the instruction
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    parsed = json.loads(raw_text)
    matches: List[dict] = parsed.get("matches", [])

    # Enrich with position metadata for UI convenience
    pos_by_id = {p.id: p for p in positions}
    for m in matches:
        p = pos_by_id.get(m["position_id"])
        if p:
            m["position_title"] = p.title_ru
            m["company_short_name"] = p.company.short_name if p.company else None
            m["salary_rub"] = float(p.salary_rub_default)

    return {
        "matches": matches,
        "top_match": matches[0] if matches else None,
        "model": "claude-haiku-4-5-20251001",
        "applicant_summary": applicant_summary,
    }
