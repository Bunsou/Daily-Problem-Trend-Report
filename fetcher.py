from typing import Optional, TypedDict

import serpapi
from config import SERPAPI_KEY


# Strategic country list for global problem discovery.
# Each country = 1 API call. Keep at 2 to fit SerpApi free tier.
DEFAULT_COUNTRIES = ["US", "GB"]


class TrendEntry(TypedDict):
    """A single trending search aggregated across countries."""
    query: str
    countries: list[str]


def fetch_trends_for_country(country: str, hours: int = 24) -> list[str]:
    """
    Fetch trending searches from a single country via SerpApi.
    
    Args:
        country: Two-letter country code (e.g., "US", "IN").
        hours: Time window. Must be 4, 24, 48, or 168.
    
    Returns:
        A list of trending query strings. Empty list on failure.
    """
    try:
        client = serpapi.Client(api_key=SERPAPI_KEY)
        
        results = client.search({
            "engine": "google_trends_trending_now",
            "geo": country,
            "hours": hours,
            "hl": "en",
        })
        
        trending = results.get("trending_searches", [])
        return [item["query"] for item in trending if "query" in item]
    
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
    """
    Fetch trending searches from multiple countries and combine them.
    
    Args:
        countries: List of country codes. Defaults to DEFAULT_COUNTRIES.
        hours: Time window for each fetch.
    
    Returns:
        A list of TrendEntry dicts, each with 'query' and 'countries' (where 
        it trended). Deduplicated: if the same trend appears in multiple 
        countries, it's merged into one entry with all countries listed.
    """
    if countries is None:
        countries = DEFAULT_COUNTRIES
    
    # Dictionary to track each unique trend and which countries it came from.
    # Keyed by the normalized (lowercase) query string.
    trend_map: dict[str, TrendEntry] = {}
    
    for country in countries:
        print(f"Fetching trends for {country}...")
        country_trends = fetch_trends_for_country(country, hours=hours)
        
        for query in country_trends:
            # Normalize to avoid duplicates like "Iphone" vs "iPhone"
            key = query.lower().strip()
            
            if key not in trend_map:
                trend_map[key] = {"query": query, "countries": []}
            
            if country not in trend_map[key]["countries"]:
                trend_map[key]["countries"].append(country)
    
    # Convert map back to list, sorted by global signal strength.
    # Trends appearing in multiple countries are stronger signals.
    combined = list(trend_map.values())
    combined.sort(key=lambda x: len(x["countries"]), reverse=True)
    
    return combined


# if __name__ == "__main__":
#     trends = fetch_trends()
#     print(f"\nFetched {len(trends)} unique trends across countries:\n")
#     for i, trend in enumerate(trends, start=1):
#         countries_str = ", ".join(trend["countries"])
#         print(f"{i}. [{countries_str}] {trend['query']}")

# if __name__ == "__main__":
#     trend = fetch_trends_for_country("KH")
#     print(f"\nFetched {len(trend)} unique trends for KH:\n")
#     for i, t in enumerate(trend, start=1):
#         print(f"{i}. {t}")