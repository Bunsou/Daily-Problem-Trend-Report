import json
from typing import TypedDict

from google import genai

from config import GEMINI_API_KEY
from fetcher import TrendEntry


_client = genai.Client(api_key=GEMINI_API_KEY)


class Problem(TypedDict):
    """A real problem identified from trending searches."""
    problem_name: str
    description: str
    evidence: list[str]
    category: str
    source_trends: list[str]  # keep for backward compat — populate from evidence
    countries: list[str]


MODEL_NAME = "gemini-2.5-flash-lite"


def build_prompt(trends: list[TrendEntry]) -> str:
    """
    Build the Stage 2 deep-analysis prompt.
    
    Designed to extract sharp, actionable problems and refuse to
    fabricate problems from topical interest.
    """
    trend_lines = []
    for t in trends:
        line = f"- \"{t['query']}\" (in: {', '.join(t['countries'])})"
        
        if t["categories"]:
            line += f" [{', '.join(t['categories'])}]"
        
        if t["related_queries"]:
            related = ", ".join(t["related_queries"][:3])
            line += f"\n  Related searches: {related}"
        
        trend_lines.append(line)
    
    trends_text = "\n\n".join(trend_lines)
    
    prompt = f"""You are a problem-discovery analyst. Your ONLY job is to identify trends that demonstrate active problem-solving behavior — not topical interest, not curiosity, not news consumption.

# The single rule that governs everything

A trend qualifies as a "problem" ONLY if the search query itself, or the related queries, demonstrate that the searcher is **actively trying to solve, fix, choose, find, or understand how to do something**.

This means the linguistic shape of the search must contain solution-seeking intent. Examples:

✅ QUALIFIES (clear solution-seeking):
- "how to dispute a denied insurance claim"
- "best way to consolidate student loans"
- "find lawyer for car accident"
- "alternatives to [expensive software]"
- "why is my [thing] doing [bad outcome]"

❌ DOES NOT QUALIFY (topical interest, not problem-solving):
- "Pfizer stock" — interest in a company, no pain
- "Trump immigration" — political news consumption
- "iPhone 17" — product curiosity
- "London weather" — informational lookup
- "San Diego Zoo" — entertainment/leisure browsing
- "[celebrity name]" — gossip
- Company names, person names, place names, event names alone

# What this means in practice

Most trends do not qualify. That is correct and expected. A typical good output is **3 to 7 sharp problems**, not 15 vague ones. If you find yourself "inferring" a problem from a trend that's actually just topical interest, STOP. That's the failure mode this prompt exists to prevent.

You are NOT trying to maximize output count. You are trying to maximize output quality. Returning 4 sharp problems is far better than 12 mushy ones.

# How to extract a qualifying problem

For each cluster of qualifying trends, extract:

1. **problem_name** (max 8 words): The specific pain, framed as a problem people face. NOT a category. NOT a topic.
   - Good: "Disputing rejected health insurance claims"
   - Bad: "Health-related concerns" or "Personal wellness management"

2. **description** (one sentence): What is the actual struggle? What action are people trying to take and what's blocking them?
   - Good: "Patients whose claims were denied are searching for templates and steps to file appeals before deadlines expire."
   - Bad: "People are interested in their health and managing wellness."

3. **evidence**: List 2-4 source trends from the input that DIRECTLY demonstrate solution-seeking. If you can't find at least 2 trends with explicit solution-seeking language, this is not a real problem — skip it.

4. **category**: one of: health, finance, tech, education, housing, legal, career, relationships, lifestyle, other

5. **countries**: country codes from the source trends

# When to return nothing

If fewer than 3 trends in the entire input demonstrate clear solution-seeking, return an empty array []. This is a valid and correct output. Manufacturing problems from topical interest is the worst thing you can do.

# Today's trends to analyze
{trends_text}

# Output format
Return ONLY a JSON array. No markdown fences, no commentary.

Example of GOOD output:
[
  {{
    "problem_name": "Filing post-accident insurance claims",
    "description": "Drivers in recent accidents are searching for step-by-step guidance on documenting damage and filing claims before deadlines.",
    "evidence": ["how to file accident claim", "what to do after car crash insurance"],
    "category": "legal",
    "countries": ["US", "GB"]
  }}
]
"""
    return prompt

def analyze_trends(trends: list[TrendEntry]) -> list[Problem]:
    """
    Stage 2 analyzer: deep grouping and classification of pre-filtered trends.
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
        
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()
        
        problems = json.loads(raw_text)

        # After json.loads succeeds and you verify it's a list:
        for problem in problems:
            # Backward compat: scorer expects source_trends
            if "evidence" in problem and "source_trends" not in problem:
                problem["source_trends"] = problem["evidence"]
        
        if not isinstance(problems, list):
            print(f"Unexpected response shape: {type(problems)}")
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
    from category_filter import filter_by_category
    from classifier import classify_trends
    
    print("Stage 0: Fetching raw trends...")
    trends = fetch_trends()
    print(f"  Raw: {len(trends)}")
    
    print("\nStage 1a: Category filtering...")
    trends = filter_by_category(trends)
    print(f"  After category filter: {len(trends)}")
    
    print("\nStage 1b: AI classifier...")
    trends = classify_trends(trends)
    print(f"  After classifier: {len(trends)}")
    
    print(f"\nStage 2: Deep analysis on {len(trends)} candidates...\n")
    problems = analyze_trends(trends)
    
    print(f"Identified {len(problems)} real problems:\n")
    for i, p in enumerate(problems, start=1):
        print(f"{i}. {p['problem_name']} [{p['category']}]")
        print(f"   {p['description']}")
        print(f"   Countries: {', '.join(p['countries'])}")
        print(f"   From trends: {p['source_trends']}\n")