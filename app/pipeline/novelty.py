"""
Novelty detection for scored problems.

Uses an AI call to compare today's problems against recent history,
tagging each problem with its novelty status.
"""
import json
from typing import TYPE_CHECKING

from google import genai

from config import GEMINI_API_KEY
from history import load_recent_history

if TYPE_CHECKING:
    from scorer import ScoredProblem


_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash-lite"


def _build_novelty_prompt(
    todays_problems: list["ScoredProblem"],
    history: list[dict],
) -> str:
    """Build the prompt that asks the AI to tag novelty for each problem."""
    todays_text = "\n".join(
        f"{i + 1}. {p['problem_name']} — {p['description']}"
        for i, p in enumerate(todays_problems)
    )
    
    if history:
        history_text = "\n".join(
            f"- [{h['days_ago']} day(s) ago] {h['problem_name']} — {h['description']}"
            for h in history
        )
    else:
        history_text = "(no recent history available)"
    
    return f"""You are a novelty classifier. Compare today's problems against recent history and decide if each is genuinely new, recurring, or evolving.

# Recent history (past 7 days)
{history_text}

# Today's problems
{todays_text}

# Classification rules

For each of today's problems, choose ONE status:

- **"new"**: This problem (or a substantially similar one) does NOT appear in recent history. Genuinely first appearance in the window.

- **"recurring"**: A substantially similar problem appeared 2+ times in recent history. This is an evergreen pattern, likely to keep appearing.

- **"returning"**: A similar problem appeared once in recent history but not consistently. It's coming back after a gap.

- **"evolving"**: A similar problem appeared in recent history, but today's framing reveals a meaningfully different angle (different buyer, different mechanism, different urgency). Specify what changed.

Substantial similarity means the same underlying pain point, even if worded differently. "Filing accident insurance claims" and "Getting compensation after car crash" are similar. "Filing accident claims" and "Filing tax returns" are not.

# Output format

Return ONLY a JSON array, one object per today's problem in input order:

[
  {{
    "problem_index": 1,
    "novelty": "new" | "recurring" | "returning" | "evolving",
    "novelty_note": "ONE sentence explaining the classification. For 'evolving', specify what changed."
  }}
]

No markdown fences. No commentary outside the JSON."""


def enrich_with_novelty(
    problems: list["ScoredProblem"],
) -> list["ScoredProblem"]:
    """
    Tag each problem with novelty status by comparing against recent history.
    
    Returns the same list with `novelty` and `novelty_note` fields added.
    On any failure, returns the problems with default values so the
    pipeline degrades gracefully.
    """
    if not problems:
        return problems
    
    history = load_recent_history()
    
    # If there's no history yet (first run), everything is "new" by definition
    if not history:
        for p in problems:
            p["novelty"] = "new"
            p["novelty_note"] = "First run — no history available yet."
        return problems
    
    raw_text = ""
    
    try:
        prompt = _build_novelty_prompt(problems, history)
        
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        
        raw_text = (response.text or "").strip()
        
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()
        
        verdicts = json.loads(raw_text)
        
        if not isinstance(verdicts, list):
            print(f"Unexpected novelty response shape: {type(verdicts)}")
            return _apply_default_novelty(problems)
        
        # Build lookup from problem_index to verdict
        verdict_map: dict[int, dict] = {}
        for v in verdicts:
            if isinstance(v, dict) and "problem_index" in v:
                verdict_map[v["problem_index"]] = v
        
        # Apply verdicts (or defaults for missing entries)
        for i, problem in enumerate(problems):
            verdict = verdict_map.get(i + 1)
            if verdict:
                problem["novelty"] = verdict.get("novelty", "new")
                problem["novelty_note"] = verdict.get("novelty_note", "")
            else:
                problem["novelty"] = "new"
                problem["novelty_note"] = "(no novelty classification returned)"
        
        return problems
    
    except json.JSONDecodeError as e:
        print(f"Novelty JSON parse failed: {e}")
        print(f"Raw response was:\n{raw_text[:500]}")
        return _apply_default_novelty(problems)
    
    except Exception as e:
        print(f"Novelty enrichment error: {e}")
        return _apply_default_novelty(problems)


def _apply_default_novelty(
    problems: list["ScoredProblem"],
) -> list["ScoredProblem"]:
    """Fallback: mark everything as 'new' so the pipeline still works."""
    for p in problems:
        p["novelty"] = "new"
        p["novelty_note"] = "(novelty detection unavailable)"
    return problems