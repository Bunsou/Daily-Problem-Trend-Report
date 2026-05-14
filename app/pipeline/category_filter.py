from app.pipeline.fetcher import TrendEntry


# Categories that almost never represent real problems.
# Lowercase for case-insensitive matching.
NOISE_CATEGORIES = {
    "sports",
    "entertainment",
    "gaming",
    "celebrity",
    "music",
    "movies",
    "tv",
    "television",
    "fashion",
    "memes",
    "viral",
}


def filter_by_category(trends: list[TrendEntry]) -> list[TrendEntry]:
    """
    Drop trends whose primary category is pure noise (sports, entertainment, etc.).
    
    A trend is dropped only if ALL its categories are in the noise list.
    If a trend has even one non-noise category, we keep it for the AI to judge.
    
    Args:
        trends: Raw trends from the fetcher.
    
    Returns:
        Filtered trends.
    """
    kept: list[TrendEntry] = []
    
    for trend in trends:
        # Trends with no categories are kept — we can't judge without info
        if not trend["categories"]:
            kept.append(trend)
            continue
        
        # Check if EVERY category is noise
        categories_lower = {c.lower() for c in trend["categories"]}
        all_noise = categories_lower.issubset(NOISE_CATEGORIES)
        
        if not all_noise:
            kept.append(trend)
    
    return kept


if __name__ == "__main__":
    from app.pipeline.fetcher import fetch_trends
    
    print("Fetching trends...")
    raw = fetch_trends()
    print(f"Raw trends: {len(raw)}")
    
    filtered = filter_by_category(raw)
    print(f"After category filter: {len(filtered)}")
    print(f"Removed: {len(raw) - len(filtered)} noise trends\n")
    
    print("Sample of kept trends:")
    for trend in filtered[:5]:
        cats = ", ".join(trend["categories"]) or "uncategorized"
        print(f"- {trend['query']} ({cats})")