import json

from google import genai

from config import GEMINI_API_KEY
from fetcher import TrendEntry


_client = genai.Client(api_key=GEMINI_API_KEY)

# Use the cheapest, fastest model for classification — accuracy matters less
# than speed at this stage. The deep analyzer in Stage 2 catches mistakes.
CLASSIFIER_MODEL = "gemini-2.5-flash-lite"

# Cap to avoid sending massive prompts to the classifier in one go
MAX_TRENDS_PER_CLASSIFY_CALL = 100


def build_classifier_prompt(trends: list[TrendEntry]) -> str:
    """
    Build a yes/no classification prompt for triaging trends.
    
    Args:
        trends: Trends to classify.
    
    Returns:
        A complete prompt string.
    """
    # Format each trend with its rich metadata so the AI has context
    trend_lines = []
    for i, t in enumerate(trends):
        line = f"{i + 1}. \"{t['query']}\""
        
        # Add categories if present
        if t["categories"]:
            line += f" [{', '.join(t['categories'])}]"
        
        trend_lines.append(line)
    
    trends_text = "\n".join(trend_lines)
    
    prompt = f"""You are a fast classifier. For each trending search below, decide if it represents a **real-world problem** that people might be looking to solve.

A "real problem" is something where:
- People are seeking a solution, advice, or way to fix something
- It causes pain, frustration, confusion, or financial cost
- A product, service, or tool could plausibly help

NOT a problem (return "no"):
- Celebrity news, gossip, athlete updates
- Sports results, scores, schedules
- Movie/show/album releases
- Political horse-race news (debates, polls, election results)
- Pure curiosity ("what is X", "who is Y") with no pain implied
- Memes, viral content
- Weather events unless tied to a clear problem

When in doubt, return "yes" — the next stage will do deeper analysis.

## Trends to classify
{trends_text}

## Output format
Return ONLY a JSON array of objects, one per trend, in the same order:
[
  {{"index": 1, "is_problem": true}},
  {{"index": 2, "is_problem": false}},
  ...
]

No markdown code fences, no commentary. Just the JSON array.
"""
    return prompt


def classify_trends(trends: list[TrendEntry]) -> list[TrendEntry]:
    """
    Use a fast AI call to keep only trends that look like real problems.
    
    Args:
        trends: Trends from the category filter.
    
    Returns:
        Filtered list of trends. Empty list on failure.
    """
    if not trends:
        print("No trends to classify.")
        return []
    
    # Process in batches if input is large
    if len(trends) > MAX_TRENDS_PER_CLASSIFY_CALL:
        print(f"Classifying {len(trends)} trends in batches of {MAX_TRENDS_PER_CLASSIFY_CALL}...")
        kept: list[TrendEntry] = []
        for i in range(0, len(trends), MAX_TRENDS_PER_CLASSIFY_CALL):
            batch = trends[i:i + MAX_TRENDS_PER_CLASSIFY_CALL]
            kept.extend(_classify_batch(batch))
        return kept
    
    return _classify_batch(trends)


def _classify_batch(trends: list[TrendEntry]) -> list[TrendEntry]:
    """Classify a single batch of trends. Internal helper."""
    raw_text = ""
    
    try:
        prompt = build_classifier_prompt(trends)
        
        response = _client.models.generate_content(
            model=CLASSIFIER_MODEL,
            contents=prompt,
        )
        
        raw_text = (response.text or "").strip()
        
        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()
        
        verdicts = json.loads(raw_text)
        
        if not isinstance(verdicts, list):
            print(f"Unexpected classifier response shape: {type(verdicts)}")
            return trends  # fallback: pass everything through to next stage
        
        # Build a lookup from index -> verdict
        verdict_map: dict[int, bool] = {}
        for v in verdicts:
            if isinstance(v, dict) and "index" in v and "is_problem" in v:
                verdict_map[v["index"]] = bool(v["is_problem"])
        
        # Keep trends where the AI said "yes" (or didn't return a verdict — safe default)
        kept = []
        for i, trend in enumerate(trends):
            verdict = verdict_map.get(i + 1, True)  # default to keep if missing
            if verdict:
                kept.append(trend)
        
        print(f"Classifier kept {len(kept)} of {len(trends)} trends in this batch.")
        return kept
    
    except json.JSONDecodeError as e:
        print(f"Classifier JSON parse failed: {e}")
        print(f"Raw response was:\n{raw_text[:500]}")
        # Safe fallback: return all trends so we don't lose data
        return trends
    
    except Exception as e:
        print(f"Classifier error: {e}")
        return trends  # safe fallback


if __name__ == "__main__":
    from fetcher import fetch_trends
    from category_filter import filter_by_category
    
    print("Fetching trends...")
    trends = fetch_trends()
    print(f"Raw: {len(trends)}")
    
    trends = filter_by_category(trends)
    print(f"After category filter: {len(trends)}")
    
    trends = classify_trends(trends)
    print(f"After classifier: {len(trends)}")
    
    print("\nSample of trends classified as problems:")
    for trend in trends[:10]:
        print(f"- {trend['query']}")