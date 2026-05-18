from typing import Optional, TypedDict

import serpapi

from app.core.config import settings
from app.services.cache import save_cache, load_cache


# Strategic country list for global problem discovery.
DEFAULT_COUNTRIES = ["US", "GB"]


class TrendEntry(TypedDict):
    """A single trending search aggregated across countries."""
    query: str
    countries: list[str]
    categories: list[str]
    search_volume: str
    related_queries: list[str]


def fetch_trends_for_country(country: str, hours: int = 24) -> list[dict]:
    """
    Fetch trending searches from a single country via SerpApi.
    
    Args:
        country: Two-letter country code (e.g., "US", "GB").
        hours: Time window. Must be 4, 24, 48, or 168.
    
    Returns:
        A list of raw trend dicts from SerpApi. Empty list on failure.
    """
    try:
        client = serpapi.Client(api_key=settings.serpapi_key)
        
        results = client.search({
            "engine": "google_trends_trending_now",
            "geo": country,
            "hours": hours,
            "hl": "en",
        })
        
        return results.get("trending_searches", [])
    
    except serpapi.HTTPError as e:
        print(f"SerpApi error for {country}: {e.status_code} — {e}")
        return []
    
    except Exception as e:
        print(f"Error fetching trends for {country}: {e}")
        return []


def fetch_trends(
    countries: Optional[list[str]] = None,
    hours: int = 24,
) -> list[TrendEntry]:
    cached = load_cache("raw_trends")
    if cached is not None:
        print("Using cached trends from earlier today.")
        return cached

    """
    Fetch trending searches from multiple countries and combine them.
    
    Args:
        countries: List of country codes. Defaults to DEFAULT_COUNTRIES.
        hours: Time window for each fetch.
    
    Returns:
        A list of TrendEntry dicts with rich metadata. Deduplicated and
        sorted by global signal strength (countries appeared in).
    """
    if countries is None:
        countries = DEFAULT_COUNTRIES
    
    trend_map: dict[str, TrendEntry] = {}
    
    for country in countries:
        print(f"Fetching trends for {country}...")
        raw_trends = fetch_trends_for_country(country, hours=hours)
        
        for raw in raw_trends:
            query = raw.get("query")
            if not query:
                continue
            
            key = query.lower().strip()
            
            # Extract category names from the categories field
            raw_categories = raw.get("categories", [])
            category_names = [
                c.get("name", "") for c in raw_categories 
                if isinstance(c, dict) and c.get("name")
            ]
            
            if key not in trend_map:
                trend_map[key] = {
                    "query": query,
                    "countries": [],
                    "categories": category_names,
                    "search_volume": raw.get("search_volume", ""),
                    "related_queries": raw.get("trend_breakdown", [])[:5],
                }
            
            if country not in trend_map[key]["countries"]:
                trend_map[key]["countries"].append(country)
            
            # If a later country has different categories, merge them
            for cat in category_names:
                if cat not in trend_map[key]["categories"]:
                    trend_map[key]["categories"].append(cat)
    
    combined = list(trend_map.values())
    combined.sort(key=lambda x: len(x["countries"]), reverse=True)
    
    save_cache("raw_trends", combined)
    return combined


if __name__ == "__main__":
    trends = fetch_trends()
    print(f"\nFetched {len(trends)} unique trends across countries:\n")
    for i, trend in enumerate(trends[:10], start=1):  # show first 10
        countries_str = ", ".join(trend["countries"])
        cats_str = ", ".join(trend["categories"]) or "uncategorized"
        print(f"{i}. [{countries_str}] {trend['query']}")
        print(f"   Categories: {cats_str}")
        print(f"   Volume: {trend['search_volume']}")
        print()
    
    print(f"... and {len(trends) - 10} more trends" if len(trends) > 10 else "")