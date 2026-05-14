"""
Delivers scored opportunity briefings to the user.

Supports two modes:
- Dev mode (default): print formatted briefing to stdout for fast iteration
- Production mode (--send flag): print AND send to Telegram

Programmatic callers can use deliver(problems, send_telegram=True) directly.
"""
import sys
from typing import TYPE_CHECKING

from telegram_client import send_message, TelegramError

if TYPE_CHECKING:
    from scorer import ScoredProblem


# Maps novelty status to display emoji
NOVELTY_ICONS = {
    "new": "🆕",
    "evolving": "🔄",
    "returning": "📅",
    "recurring": "📈",
}


def format_briefing(problems: list["ScoredProblem"]) -> str:
    """
    Format scored problems into a human-readable briefing message.
    
    This is the single source of truth for message formatting. The same
    formatted string is used for both stdout printing and Telegram delivery.
    """
    if not problems:
        return _format_empty_briefing()
    
    lines = []
    lines.append(f"📊 Daily Opportunity Radar — {_today_str()}")
    lines.append("")
    lines.append(f"{len(problems)} qualifying opportunit{'y' if len(problems) == 1 else 'ies'} today")
    lines.append("─" * 20)
    lines.append("")
    
    for i, p in enumerate(problems, start=1):
        lines.extend(_format_single_problem(i, p))
        lines.append("")  # blank line between problems
    
    return "\n".join(lines)


def _format_single_problem(rank: int, p: "ScoredProblem") -> list[str]:
    """Format a single scored problem into a list of display lines."""
    icon = NOVELTY_ICONS.get(p.get("novelty", "new"), "🆕")
    novelty_label = p.get("novelty", "new").upper()
    
    lines = [
        f"{rank}. {icon} [{novelty_label}] {p['problem_name']}",
        f"   Category: {p['category']}  |  Score: {p['opportunity_score']}",
        f"   Demand: {p['demand']}  •  Monetization: {p['monetization']}  •  Buildability: {p['buildability']}",
        "",
        f"   💡 {p['key_insight']}",
        "",
        f"   🎯 Buyer: {p['buyer_test']}",
        "",
        f"   📝 {p['description']}",
        "",
        f"   🛠 Solutions:",
    ]
    
    for sol in p.get("solutions", []):
        lines.append(f"      • {sol}")
    
    if p.get("novelty_note"):
        lines.append("")
        lines.append(f"   📌 {p['novelty_note']}")
    
    return lines


def _format_empty_briefing() -> str:
    """Format the message shown when no qualifying opportunities exist."""
    lines = [
        f"📊 Daily Opportunity Radar — {_today_str()}",
        "",
        "No qualifying opportunities today.",
        "─" * 20,
        "",
        "Today's trends were mostly news, entertainment, or problems",
        "without indie-viable business angles. This is normal on quiet",
        "days — check back tomorrow.",
    ]
    return "\n".join(lines)


def _today_str() -> str:
    """Return today's date as a readable string (e.g., 'Apr 26, 2026')."""
    from datetime import datetime
    return datetime.now().strftime("%b %d, %Y")


def deliver(
    problems: list["ScoredProblem"],
    send_telegram: bool = False,
) -> None:
    """
    Deliver the briefing to the user.
    
    Always prints to stdout. If send_telegram=True, also sends to Telegram.
    
    Args:
        problems: Scored and novelty-enriched problems from the pipeline.
        send_telegram: If True, also send the briefing via Telegram bot.
    
    Raises:
        TelegramError: If send_telegram=True and the Telegram API call fails.
    """
    message = format_briefing(problems)
    print(message)
    
    if send_telegram:
        print("\n" + "─" * 20)
        print("Sending to Telegram...")
        send_message(message)
        print("✅ Sent successfully.")


# === Dev mode entry point ===

if __name__ == "__main__":
    from cache import load_pipeline_output
    
    # Check for --send flag in command-line args
    send_telegram = "--send" in sys.argv
    
    cached = load_pipeline_output()
    
    if cached is None:
        print("No pipeline cache found.")
        print("Run `python scorer.py` first to generate and cache pipeline output.")
        print("After that, this script will use the cache for fast iteration.")
        sys.exit(1)
    
    print(f"(Loaded {len(cached)} problems from cache — no AI calls were made.)\n")
    print("=" * 60)
    
    try:
        deliver(cached, send_telegram=send_telegram)
    except TelegramError as e:
        print(f"\n❌ Telegram delivery failed: {e}")
        sys.exit(1)
    
    if not send_telegram:
      print()
      print("─" * 40)
      print("To send via Telegram from cached data, run: python deliverer.py --send")
      print("To run the full pipeline + send, run: python main.py")