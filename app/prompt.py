"""The concept's prompt, read the way the starter reads it -- the job is the
same on both sides; only what surrounds the agent differs."""

from __future__ import annotations

from pathlib import Path

CONCEPT_DIR = Path(__file__).resolve().parents[1] / "concept"

_FALLBACK_PROMPT = (
    "You are this application's assistant. Answer the user's message directly "
    "and briefly, use the tools you have when the request needs them, and "
    "relay every tool result truthfully."
)


def load_concept_prompt() -> str:
    try:
        text = (CONCEPT_DIR / "prompt.md").read_text(encoding="utf-8").strip()
    except OSError:
        return _FALLBACK_PROMPT
    return text or _FALLBACK_PROMPT


def build_user_text(user_input: str, question: str | None) -> str:
    text = user_input.strip()
    if question and question.strip():
        return f"{text}\n\nQuestion: {question.strip()}"
    return text
