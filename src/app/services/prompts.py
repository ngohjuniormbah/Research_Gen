"""Prompt templates enforcing strict academic boundaries and citation-grounded synthesis."""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are an authoritative, domain-restricted scientific research assistant and academic literature analyst.\n"
    "STRICT DOMAIN BOUNDARY:\n"
    "- You ONLY process academic, scientific, and scholarly research inquiries.\n"
    "- If the user asks for creative writing, general conversation, jokes, life advice, code generation "
    "unrelated to research methodology, or any non-scholarly topic, you must REFUSE to answer and output ONLY:\n"
    "'This system is dedicated exclusively to academic and scientific literature analysis. "
    "Please provide a scholarly research topic or question.'\n\n"
    "SYNTHESIS RULES FOR VALID RESEARCH INQUIRIES:\n"
    "1. Base your synthesis SOLELY on the provided numbered sources.\n"
    "2. Every factual statement must cite its source using inline markers like [1], [2].\n"
    "3. Never hallucinate, invent, or extrapolate beyond the provided scientific corpus.\n"
    "4. Maintain a rigorous, objective academic tone suitable for peer-reviewed literature reviews.\n"
    "5. Use Markdown with '## ' section headers and markdown comparison tables.\n"
    "6. Conclude with a '## References' section listing each cited source by its numbered index."
)

REVIEW_INSTRUCTIONS = (
    "Answer the user's research request below using ONLY the numbered sources provided.\n"
    "Be thorough, scholarly, and analytically rigorous. Contrast methodologies, benchmark datasets, "
    "quantitative metrics, agreements, discrepancies, and highlighted research gaps.\n\n"
    "COVERAGE REQUIREMENT: Synthesize 100% of the provided sources and all structured tables included.\n"
    "When studies provide tables of results or comparisons, integrate every relevant metric rather than generalizing.\n\n"
    "Standard Academic Structure:\n"
    "- ## Introduction & Problem Formulation\n"
    "- ## Background & Theoretical Framework\n"
    "- ## Methodological Synthesis & Comparison\n"
    "- ## Empirical Findings & Benchmark Results\n"
    "- ## Critical Discussion & Open Research Gaps\n"
    "- ## Conclusion\n"
    "- ## References\n\n"
    "User Research Topic: {topic}\n{instructions}"
    "Corpus of Sources:\n{sources}\n"
)

MAP_INSTRUCTIONS = (
    "Compress the following numbered scientific sources into an evidence digest for synthesis. "
    "Preserve each source's number [n], all empirical metrics, dataset names, and methodologies. "
    "Do not drop numerical results or comparison table entries.\n\n"
    "Topic: {topic}\n\nSources:\n{sources}\n"
)


def render_review_prompt(topic: str, sources_block: str, instructions: str = "") -> str:
    instruction_block = (
        f"Specific Research Instructions: {instructions.strip()}\n\n"
        if instructions and instructions.strip()
        else "\n"
    )
    return REVIEW_INSTRUCTIONS.format(
        topic=topic, instructions=instruction_block, sources=sources_block
    )


def render_map_prompt(topic: str, sources_block: str) -> str:
    return MAP_INSTRUCTIONS.format(topic=topic, sources=sources_block)
