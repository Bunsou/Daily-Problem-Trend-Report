"""
Shared Gemini client.

A single `genai.Client` is instantiated at import time and reused by every
pipeline stage that calls the model — classifier, analyzer, scorer, novelty.
Centralizing this means the API key is read once and any future client-level
config (retries, timeouts, telemetry) lives in one place.
"""
from google import genai
from google.genai import types

from app.core.config import settings


client = genai.Client(
    api_key=settings.gemini_api_key,
    http_options=types.HttpOptions(timeout=120_000),  # 120 s — prevents indefinite hangs on slow batches
)
