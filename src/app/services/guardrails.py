"""Scope guardrails: allows all academic synthesis directives while blocking non-scholarly spam."""

from __future__ import annotations

import re

# Block strictly off-topic, non-academic queries
OFF_TOPIC_PATTERNS = [
    r"^\s*(hi|hello|hey|how are you|good morning|good evening)\s*$",
    r"\b(tell me a joke|tell a story|write a poem|write lyrics|sing a song)\b",
    r"\b(recipe for|how to cook|how to bake|make a cake|dinner ideas)\b",
    r"\b(play a game|play chess|trivia|riddle|fortune teller)\b",
    r"\b(crypto price|buy bitcoin|stock advice|how to get rich)\b",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in OFF_TOPIC_PATTERNS]

RESEARCH_REFUSAL_MESSAGE = (
    "## Research Scope Notice\n\n"
    "This system is designed exclusively for scientific literature review and academic synthesis. "
    "Please provide a scientific research topic, comparison request, or academic inquiry."
)


def is_in_research_scope(topic: str, instructions: str = "") -> tuple[bool, str]:
    text = f"{topic.strip()} {instructions.strip()}".lower()

    if not topic.strip():
        return False, "Topic cannot be blank."

    # Allow comparison, synthesis, and review directives
    academic_keywords = [
        "comparison", "table", "review", "synthesize", "survey", "method",
        "dataset", "metric", "paper", "study", "analysis", "malaria", "cancer",
        "model", "algorithm", "architecture", "evaluation", "literature"
    ]
    if any(k in text for k in academic_keywords):
        return True, ""

    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            return False, RESEARCH_REFUSAL_MESSAGE

    return True, ""
