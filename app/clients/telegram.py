"""
HTTP wrapper around the Telegram Bot API for one-way message delivery.

This module knows nothing about briefings, problems, or formatting.
It only knows how to send text messages to a configured chat.
"""
import time

import requests

from app.core.config import settings


# Telegram caps individual messages at 4096 characters.
# We use a slightly lower limit to leave room for safety margins.
TELEGRAM_MAX_LENGTH = 4000

# Base URL for the Telegram Bot API
_API_BASE = f"https://api.telegram.org/bot{settings.telegram_bot_token}"


class TelegramError(Exception):
    """Raised when a Telegram API call fails."""
    pass


def send_message(text: str) -> None:
    """
    Send a single message to the configured Telegram chat.
    
    Splits long messages into chunks if they exceed Telegram's length limit.
    Each chunk is sent as a separate message with a small delay between them.
    
    Args:
        text: The message text to send.
    
    Raises:
        TelegramError: On any delivery failure, with details in the message.
    """
    if not text or not text.strip():
        raise TelegramError("Cannot send empty message.")
    
    chunks = _split_message(text)
    
    for i, chunk in enumerate(chunks):
        _send_single_chunk(chunk)
        
        # Brief pause between chunks to avoid rate-limit issues
        # and ensure messages arrive in order on the user's screen.
        if i < len(chunks) - 1:
            time.sleep(0.5)


def _send_single_chunk(text: str) -> None:
    """Send one chunk of text. Internal helper."""
    url = f"{_API_BASE}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        # Disable link previews — they clutter the message visually
        "disable_web_page_preview": True,
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
    except requests.exceptions.Timeout:
        raise TelegramError("Telegram API timed out after 10 seconds.")
    except requests.exceptions.ConnectionError as e:
        raise TelegramError(f"Could not connect to Telegram: {e}")
    
    if response.status_code == 200:
        return  # success
    
    # Parse Telegram's error response for a useful message
    try:
        error_info = response.json()
        description = error_info.get("description", "(no description)")
    except ValueError:
        description = response.text[:200] or "(empty response)"
    
    if response.status_code == 401:
        raise TelegramError(
            f"Telegram rejected the bot token (401 Unauthorized). "
            f"Check TELEGRAM_BOT_TOKEN in your .env. Detail: {description}"
        )
    elif response.status_code == 400:
        raise TelegramError(
            f"Telegram rejected the request (400 Bad Request). "
            f"Likely cause: invalid chat_id or malformed text. Detail: {description}"
        )
    elif response.status_code == 429:
        raise TelegramError(
            f"Telegram rate limit hit (429). Detail: {description}"
        )
    else:
        raise TelegramError(
            f"Telegram returned {response.status_code}: {description}"
        )


def _split_message(text: str) -> list[str]:
    """
    Split a long message into chunks under Telegram's length limit.
    
    Splits on blank lines (problem boundaries) when possible, falling back
    to line boundaries for unusually long single problems. Never splits
    in the middle of a line.
    
    Args:
        text: The full message text.
    
    Returns:
        A list of message chunks, each under TELEGRAM_MAX_LENGTH chars.
    """
    if len(text) <= TELEGRAM_MAX_LENGTH:
        return [text]
    
    chunks: list[str] = []
    
    # First, try splitting on double-newlines (between problems)
    sections = text.split("\n\n")
    current = ""
    
    for section in sections:
        # Compute what 'current' would be after appending this section
        candidate = section if not current else f"{current}\n\n{section}"
        
        if len(candidate) <= TELEGRAM_MAX_LENGTH:
            current = candidate
        else:
            # The section won't fit. Save current chunk first if non-empty.
            if current:
                chunks.append(current)
                current = ""
            
            # Now handle the oversized section itself
            if len(section) <= TELEGRAM_MAX_LENGTH:
                current = section
            else:
                # Edge case: a single section is bigger than limit.
                # Fall back to splitting by single newlines within it.
                chunks.extend(_split_by_lines(section))
    
    if current:
        chunks.append(current)
    
    return chunks


def _split_by_lines(text: str) -> list[str]:
    """
    Last-resort splitter: break text on line boundaries to fit limit.
    
    Used when a single 'section' (problem) is too large for one message.
    """
    chunks: list[str] = []
    current = ""
    
    for line in text.split("\n"):
        candidate = line if not current else f"{current}\n{line}"
        
        if len(candidate) <= TELEGRAM_MAX_LENGTH:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # If a single line exceeds the limit, hard-truncate it.
            # This should be vanishingly rare for our use case.
            if len(line) > TELEGRAM_MAX_LENGTH:
                current = line[:TELEGRAM_MAX_LENGTH - 3] + "..."
            else:
                current = line
    
    if current:
        chunks.append(current)
    
    return chunks


# === Sanity check: test bot connectivity ===

def send_sanity_check() -> None:
    """
    Send a short test message to verify token and chat_id work.
    
    Run this before relying on real briefings to catch config issues early.
    """
    test_message = (
        "🤖 Trend Engine sanity check\n"
        "\n"
        "If you see this, your bot token and chat ID are configured correctly. "
        "You're ready for real briefings."
    )
    send_message(test_message)
    print("Sanity check sent successfully.")


if __name__ == "__main__":
    print("Running Telegram sanity check...")
    try:
        send_sanity_check()
    except TelegramError as e:
        print(f"❌ Sanity check failed: {e}")
        exit(1)