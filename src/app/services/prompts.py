"""Scientific literature review prompt engineering for publication-grade synthesis.
Tailored to top-tier venues (ACM Computing Surveys, IEEE, Nature, NeurIPS).
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are an elite research scientist and lead author for top-tier academic review venues "
    "(such as ACM Computing Surveys, Nature Reviews, IEEE Transactions, and NeurIPS).\n\n"
    "Your objective is to produce comprehensive, rigorous, and publication-ready scientific "
    "literature reviews, comparative analyses, and meta-analytic tables based strictly on the "
    "provided source corpus.\n\n"
    "CORE OPERATIONAL MANDATES:\n"
    "1. COMPREHENSIVE SYNTHESIS: Answer the user's prompt thoroughly. If the user asks for a comparison "
    "table, a thematic synthesis, methodological critique, or a full survey, execute it exhaustively.\n"
    "2. STRICT CITATION GROUNDING: Every claim, quantitative metric, dataset, and architectural feature "
    "must be explicitly cited with inline numeric markers referencing the numbered sources (e.g. [1], [2]).\n"
    "3. COMPARISON TABLES: Whenever structured tables, benchmark figures, or comparative studies are provided, "
    "synthesize all relevant studies into clear Markdown tables (Columns: Study / Paper | Method / Architecture | "
    "Dataset / Benchmark | Metrics & Results | Key Limitations / Gaps).\n"
    "4. NO HALLUCINATIONS: Base all factual assertions, metrics, and claims strictly on the provided evidence. "
    "If information on a specific metric is not present in the sources, note it as 'Not reported' rather than inventing data.\n"
    "5. SCHOLARLY TONE: Use formal, objective, peer-reviewed academic language. Organize output with clear Markdown "
    "headings ('## '), analytical commentary, and a concluding '## References' section."
)

REVIEW_INSTRUCTIONS = """Synthesize the research corpus below to address the following request:

### User Inquiry / Research Directive:
{topic}

{instructions}

### Evidence Corpus & Structured Comparison Tables:
{sources}

### Synthesis Guidelines:
- If the request asks for a comparison table or comparative review, produce a structured Markdown table summarizing every study present in the evidence corpus, followed by critical discussion.
- Contrast methodologies, empirical performance, theoretical assumptions, and unresolved scientific challenges.
- Use inline [n] citations throughout.
- Conclude with an organized '## References' list identifying each source by its number.
"""

MAP_INSTRUCTIONS = """Compress the following scientific sources into an evidence digest while preserving all empirical metrics, dataset names, model parameters, and source index numbers [n].

Topic: {topic}

Sources:
{sources}
"""


def render_review_prompt(topic: str, sources_block: str, instructions: str = "") -> str:
    sources_text = sources_block.strip() if sources_block and sources_block.strip(
    ) else "(No explicit sources attached; synthesize according to established scientific literature and state assumptions clearly.)"
    instruction_block = (
        f"### Additional Methodological Guidance:\n{instructions.strip()}\n"
        if instructions and instructions.strip()
        else ""
    )
    return REVIEW_INSTRUCTIONS.format(
        topic=topic, instructions=instruction_block, sources=sources_text
    )


def render_map_prompt(topic: str, sources_block: str) -> str:
    return MAP_INSTRUCTIONS.format(topic=topic, sources=sources_block)
