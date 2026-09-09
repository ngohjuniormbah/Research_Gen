"""Scope guardrails: ensures requests are strictly academic and research-oriented.
Rejects casual conversation, entertainment, recipes, coding tasks, and off-topic requests.
"""

from __future__ import annotations

import re

# Patterns indicating casual conversation, entertainment, or non-research tasks
OFF_TOPIC_PATTERNS = [
    r"^\s*(hi|hello|hey|greetings|how are you|good morning|good evening)\b",
    r"\b(tell me a joke|tell a story|write a poem|write lyrics|sing a song)\b",
    r"\b(recipe for|how to cook|how to bake|make a cake|dinner ideas)\b",
    r"\b(play a game|play chess|trivia|riddle|fortune teller)\b",
    r"\b(horoscope|astrology|zodiac)\b",
    r"\b(who is your favorite|what is your name|are you conscious|are you human)\b",
    r"\b(write a python script to download|code a snake game|build me a website)\b",
    r"\b(crypto price|buy bitcoin|stock advice|how to get rich)\b",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in OFF_TOPIC_PATTERNS]

RESEARCH_REFUSAL_MESSAGE = (
    "## Research Scope Restriction\n\n"
    "This platform is exclusively dedicated to **academic and scientific research analysis**.\n\n"
    "It cannot assist with general conversation, creative writing, entertainment, or non-research tasks.\n\n"
    "**Please provide a scientific research question, literature review topic, or academic query** "
    "(e.g., *'Comparative analysis of transformer architectures for genomic sequence modeling'*), "
    "along with your scholarly sources (PDFs, DOIs, CSV, or ORKG records)."
)


def is_in_research_scope(topic: str, instructions: str = "") -> tuple[bool, str]:
    """Verify that the query pertains to scholarly literature or scientific inquiry.
    Returns (is_valid, rejection_reason_or_empty).
    """
    text = f"{topic.strip()} {instructions.strip()}".lower()

    if not topic.strip():
        return False, "Topic cannot be blank."

    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            return False, RESEARCH_REFUSAL_MESSAGE

    return True, ""
