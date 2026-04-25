import json
from typing import TypedDict

from google import genai

from config import GEMINI_API_KEY
from fetcher import TrendEntry


# Create a single Gemini client when this module loads
_client = genai.Client(api_key=GEMINI_API_KEY)


class Problem(TypedDict):
    """A real problem identified from trending searches."""
    problem_name: str
    description: str
    category: str
    source_trends: list[str]
    countries: list[str]


# The model we use. Flash is fast and cheap; perfect for filtering tasks.
MODEL_NAME = "gemini-2.5-flash-lite"


def build_prompt(trends: list[TrendEntry]) -> str:
    """
    Build the prompt that tells Gemini how to filter and classify trends.
    
    Args:
        trends: Raw trending searches from the fetcher.
    
    Returns:
        A complete prompt string ready to send to Gemini.
    """
    # Format trends as a readable list for the AI
    trends_text = "\n".join(
        f"- \"{t['query']}\" (trending in: {', '.join(t['countries'])})"
        for t in trends
    )
    
    prompt = f"""You are a trend analyst specializing in identifying real-world problems people are trying to solve.

I will give you a list of today's trending Google searches from multiple countries. Your job is to identify which trends represent **real problems** that people need help with, and filter out everything else.

## What counts as a real problem
A real problem is something where:
- People are seeking a solution, advice, or way to fix something
- It causes pain, frustration, confusion, or financial cost
- A product, service, or tool could plausibly solve it

## What to EXCLUDE (do not include these)
- Celebrity news, gossip, or entertainment (e.g., "Taylor Swift tour")
- Sports scores, schedules, or team news (e.g., "NFL playoffs")
- Movie/TV/music releases (e.g., "new Marvel movie")
- Political events or election news (e.g., "presidential debate")
- Product launches that aren't problems (e.g., "iPhone 17 release date")
- Memes or viral content
- Weather events unless directly tied to a problem people need to solve

## Today's trending searches
{trends_text}

## Your task
Group related trends together. For each real problem you identify, return a JSON object with these exact fields:
- "problem_name": short descriptive name (max 8 words)
- "description": one sentence explaining the actual problem people face
- "category": one of: "health", "finance", "tech", "education", "housing", "legal", "career", "relationships", "lifestyle", "other"
- "source_trends": list of the original trend strings that pointed to this problem
- "countries": list of country codes where these trends appeared

Return ONLY a valid JSON array. No markdown code fences, no commentary, no explanation. If you find no real problems, return an empty array: []

Example output format:
[
  {{
    "problem_name": "Student loan repayment confusion",
    "description": "Borrowers are unsure how new 2026 forgiveness rules apply to them.",
    "category": "finance",
    "source_trends": ["student loan forgiveness 2026"],
    "countries": ["US", "GB"]
  }}
]
"""
    return prompt


def analyze_trends(trends: list[TrendEntry]) -> list[Problem]:
    """
    Send trends to Gemini for filtering and problem identification.
    
    Args:
        trends: Raw trending searches from the fetcher.
    
    Returns:
        A list of identified Problem dicts. Empty list on failure or no problems.
    """
    if not trends:
        print("No trends to analyze.")
        return []
    
    raw_text = ""
    
    try:
        prompt = build_prompt(trends)
        
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        
        raw_text = (response.text or "").strip()
        
        # Defensive: strip markdown code fences if Gemini adds them despite instructions
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()
        
        problems = json.loads(raw_text)
        
        if not isinstance(problems, list):
            print(f"Unexpected response shape: expected list, got {type(problems)}")
            return []
        
        return problems
    
    except json.JSONDecodeError as e:
        print(f"Failed to parse AI response as JSON: {e}")
        print(f"Raw response was:\n{raw_text}")
        return []
    
    except Exception as e:
        print(f"Error analyzing trends: {e}")
        return []


if __name__ == "__main__":
    from fetcher import fetch_trends
    
    print("Fetching trends...")
    trends = fetch_trends()
    
    print(f"\nAnalyzing {len(trends)} trends with Gemini...\n")
    problems = analyze_trends(trends)
    
    print(f"Identified {len(problems)} real problems:\n")
    for i, p in enumerate(problems, start=1):
        print(f"{i}. {p['problem_name']} [{p['category']}]")
        print(f"   {p['description']}")
        print(f"   Countries: {', '.join(p['countries'])}")
        print(f"   From trends: {p['source_trends']}\n")