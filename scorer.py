import json
from typing import TypedDict

from google import genai

from config import GEMINI_API_KEY
from analyzer import Problem


_client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-2.5-flash"

# Below this score, problems are filtered out as non-opportunities.
# 4.5 means at least one dimension must be 6+ AND the others must be at least 4.
# This catches indie-viable opportunities while removing clear non-businesses.
MIN_OPPORTUNITY_SCORE = 4.5


class ScoredProblem(Problem):
    """A Problem enriched with business opportunity scoring."""
    buyer_test: str
    demand: int
    monetization: int
    buildability: int
    opportunity_score: float
    key_insight: str
    solutions: list[str]
    novelty: str  # "new" | "recurring" | "returning" | "evolving"
    novelty_note: str


def build_scorer_prompt(problems: list[Problem]) -> str:
    """Build a prompt that scores each problem as a SaaS business opportunity."""
    problems_text = "\n\n".join(
        f"{i + 1}. {p['problem_name']} ({p['category']})\n"
        f"   Description: {p['description']}\n"
        f"   Evidence: {', '.join(p.get('evidence', p.get('source_trends', [])))}\n"
        f"   Trending in: {', '.join(p['countries'])}"
        for i, p in enumerate(problems)
    )
    
    prompt = f"""You are a SaaS business analyst evaluating problems as software opportunities for an indie founder or small team. You are skeptical by default. Most problems are not businesses, and you must say so.

# The buyer test (apply BEFORE scoring)

Before scoring any problem, attempt to complete this sentence in ONE concrete sentence:

"____ will pay $____/month for this because ____ — and they currently spend money on ____."

You must name:
1. A specific buyer persona (job title or specific consumer segment, not "users" or "people")
2. A concrete price range they would realistically pay
3. The reason this specific buyer pays
4. An adjacent category where this buyer ALREADY spends money (proves willingness)

If you cannot complete this sentence with a concrete, named buyer who already spends money in adjacent categories, the problem fails the buyer test. Apply scoring penalties below.

# Scoring dimensions (1-10)

**Demand**: How many people are ACTIVELY searching for solutions right now?
- 1-3: Niche, news-driven blip, or topic without active solution-seeking
- 4-6: Real but small market; passive interest dominates
- 7-9: Large active market with consistent solution-seeking
- 10: Massive global active demand, persistent over time

**Monetization**: Will the buyer test pass with a willing, identifiable buyer?
- 1-3: FAILS the buyer test. No nameable buyer, or buyer can't/won't pay (disaster victims, audiences served free by government, audiences with strong free alternatives)
- 4-6: B2C only, low willingness to pay ($5-15/mo), saturated category with strong free competition
- 7-9: B2B with named buyer persona spending in adjacent categories, OR B2C with proven willingness ($20+/mo subscription category)
- 10: High-ticket B2B, mission-critical, $100+/mo with named buyer who urgently needs this

**Buildability**: Can a small indie team realistically ship and operate an MVP?
- 1-3: Requires regulatory approval, gated/expensive data, hardware, or industry partnerships
- 4-6: Requires significant capital, specialized expertise, or 6+ months
- 7-9: Public APIs and standard tools; MVP shippable in 1-3 months by 1-2 people
- 10: Solo dev ships in a weekend with off-the-shelf tools

# Mandatory penalties (apply automatically)

- If the buyer test fails (cannot name specific buyer with adjacent spend): **monetization MUST be 1-3**
- If the problem is in a saturated B2C category (notes apps, todo apps, generic news, weather, generic wellness, generic finance dashboards): **monetization caps at 5**
- If the buyer is "victims of a tragedy/disaster" or "people seeking news": **monetization caps at 3**
- If the problem name or description contains words like "managing", "exploring", "interest in", "navigating", "understanding" without a specific painful action: this is a category, not a problem — **demand caps at 5**

# Solution requirements

Each solution must:
- Name a concrete product type (web app / mobile app / browser extension / API)
- Specify a concrete function in 12 words or fewer
- Be realistically buildable by an indie team
- Have at least one solution that includes the named buyer persona

Reject your own draft solutions if they sound impressive but don't pass these tests. Replace them.

# Problems to score
{problems_text}

# Output format

Return ONLY a JSON array. For each problem:
- "problem_index": integer matching input order
- "buyer_test": ONE sentence following the template above; or "FAILS — no specific buyer identifiable"
- "demand": integer 1-10
- "monetization": integer 1-10
- "buildability": integer 1-10
- "key_insight": ONE sentence (max 25 words) on why this is or isn't a real opportunity. Be skeptical, not promotional.
- "solutions": array of 2-3 strings as specified above

No markdown fences, no commentary outside the JSON.

Example:
[
  {{
    "problem_index": 1,
    "buyer_test": "Personal injury law firms will pay $50-300 per qualified lead because client acquisition costs run $1500+, and they currently spend heavily on Google Ads and lead networks like 4LegalLeads.",
    "demand": 9,
    "monetization": 9,
    "buildability": 7,
    "key_insight": "Proven lead-gen category with established willingness to pay; differentiation must be quality of intake or geographic specialization.",
    "solutions": [
      "Lead-gen web app routing accident victims to vetted local injury lawyers",
      "Mobile evidence-collection app monetized via referral fees to law firms",
      "API for legal CRMs to verify lead intake completeness"
    ]
  }}
]
"""
    return prompt

def score_problems(problems: list[Problem]) -> list[ScoredProblem]:
    """
    Score each problem on demand, monetization, and buildability.
    
    Returns problems sorted by opportunity_score (descending).
    """
    if not problems:
        print("No problems to score.")
        return []
    
    raw_text = ""
    
    try:
        prompt = build_scorer_prompt(problems)
        
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
        
        scores = json.loads(raw_text)
        
        if not isinstance(scores, list):
            print(f"Unexpected response shape: {type(scores)}")
            return []
        
        score_map = {
            item["problem_index"]: item 
            for item in scores 
            if "problem_index" in item
        }
        
        scored_problems: list[ScoredProblem] = []
        for i, problem in enumerate(problems):
            problem_index = i + 1
            score_data = score_map.get(problem_index)
            
            if score_data is None:
                print(f"Warning: no score for problem #{problem_index}")
                continue
            
            demand = int(score_data.get("demand", 5))
            monetization = int(score_data.get("monetization", 5))
            buildability = int(score_data.get("buildability", 5))
            
            # Geometric mean penalizes weakness in any dimension.
            # A 9-9-2 problem is a worse opportunity than 6-6-6, and this
            # math reflects that. (9*9*2)^(1/3) = 4.3 vs (6*6*6)^(1/3) = 6.0
            opportunity_score = (demand * monetization * buildability) ** (1/3)
            
            scored_problems.append({
                **problem,
                "buyer_test": score_data.get("buyer_test", ""),
                "demand": demand,
                "monetization": monetization,
                "buildability": buildability,
                "opportunity_score": round(opportunity_score, 1),
                "key_insight": score_data.get("key_insight", ""),
                "solutions": score_data.get("solutions", []),
                "novelty": problem.get("novelty", "new"),
                "novelty_note": problem.get("novelty_note", ""),
            })
        
        # Sort and filter
        scored_problems.sort(key=lambda p: p["opportunity_score"], reverse=True)

        qualifying = [p for p in scored_problems if p["opportunity_score"] >= MIN_OPPORTUNITY_SCORE]
        filtered_count = len(scored_problems) - len(qualifying)

        if filtered_count > 0:
            print(f"Filtered out {filtered_count} non-viable problems (score < {MIN_OPPORTUNITY_SCORE}).")

        return qualifying
    
    except json.JSONDecodeError as e:
        print(f"Failed to parse AI response as JSON: {e}")
        print(f"Raw response was:\n{raw_text}")
        return []
    
    except Exception as e:
        print(f"Error scoring problems: {e}")
        return []


if __name__ == "__main__":
    from fetcher import fetch_trends
    from category_filter import filter_by_category
    from classifier import classify_trends
    from analyzer import analyze_trends
    from novelty import enrich_with_novelty
    from history import save_todays_problems
    
    print("Stage 0: Fetching raw trends...")
    trends = fetch_trends()
    print(f"  Raw: {len(trends)}")
    
    print("\nStage 1a: Category filtering...")
    trends = filter_by_category(trends)
    print(f"  After category filter: {len(trends)}")
    
    print("\nStage 1b: AI classifier...")
    trends = classify_trends(trends)
    print(f"  After classifier: {len(trends)}")
    
    print(f"\nStage 2: Analyzing {len(trends)} candidates...")
    problems = analyze_trends(trends)
    print(f"  Found {len(problems)} problems")
    
    print(f"\nStage 3: Scoring {len(problems)} problems as business opportunities...")
    scored = score_problems(problems)
    
    print(f"\nStage 4: Checking novelty against past 7 days...")
    scored = enrich_with_novelty(scored)
    
    # Save today's results to history for tomorrow's novelty check
    save_todays_problems(scored)

    # Save to pipeline cache (for fast deliverer iteration without re-running AI)
    from cache import save_pipeline_output
    save_pipeline_output(scored)
    
    print()
    
    if not scored:
        print("=" * 60)
        print("No qualifying opportunities today.")
        print("=" * 60)
        print("\nToday's trends were mostly news, entertainment, or problems")
        print("without indie-viable business angles. This is a normal outcome")
        print("on quiet days. Check back tomorrow.\n")
    else:
        # Map novelty to display emoji
        novelty_icons = {
            "new": "🆕",
            "evolving": "🔄",
            "returning": "📅",
            "recurring": "📈",
        }
        
        print(f"Top {len(scored)} qualifying opportunities:\n")
        for i, p in enumerate(scored, start=1):
            icon = novelty_icons.get(p.get("novelty", "new"), "🆕")
            novelty_label = p.get("novelty", "new").upper()
            
            print(f"{i}. {icon} [{novelty_label}] {p['problem_name']} [{p['category']}] — Score: {p['opportunity_score']}")
            print(f"   Demand: {p['demand']}/10 | Monetization: {p['monetization']}/10 | Buildability: {p['buildability']}/10")
            print(f"   📊 {p.get('novelty_note', '')}")
            print(f"   🎯 Buyer test: {p['buyer_test']}")
            print(f"   💡 Insight: {p['key_insight']}")
            print(f"   Description: {p['description']}")
            print(f"   Solutions:")
            for s in p['solutions']:
                print(f"     • {s}")
            print()