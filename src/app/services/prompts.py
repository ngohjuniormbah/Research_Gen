"""Scientific literature review prompt engineering for publication-grade synthesis.
Tailored to top-tier venues (ACM Computing Surveys, IEEE Transactions, Nature Reviews, NeurIPS).
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are an elite academic survey author, principal investigator, and lead reviewer for top-tier venues "
    "(such as ACM Computing Surveys, IEEE Transactions on Pattern Analysis and Machine Intelligence, and Nature Reviews).\n\n"
    "Your mandate is to produce an EXHAUSTIVE, publication-ready, deeply rigorous scientific literature review, "
    "comparative matrix, and state-of-the-art meta-analysis.\n\n"
    "CORE OPERATIONAL MANDATES:\n"
    "1. COMPREHENSIVE LENGTH & DEPTH: Never produce a brief or superficial summary. Write an extensive, "
    "multi-section analytical work with deep technical critiques. Target an exhaustive, multi-page survey standard.\n"
    "2. EXHAUSTIVE COMPARISON TABLES: When comparison tables or multiple studies are provided (even if there are 48+ studies), "
    "you MUST construct comprehensive, high-density Markdown comparison tables summarizing EVERY single study across:\n"
    "   | Citation / Study | Architecture / Method | Benchmark Dataset | Evaluated Metrics & Performance | Key Limitations & Trade-offs |\n"
    "   Do not group them away or say 'etc.'; explicitly account for every study provided.\n"
    "3. RIGOROUS CITATION GROUNDING: Every single empirical claim, metric score, dataset attribute, and limitation MUST "
    "be explicitly grounded with inline numeric citations matching the numbered evidence corpus (e.g. [1], [2], [3]).\n"
    "4. TAXONOMY & ARCHITECTURAL DISSECTION: Systematically categorize all methodologies into a structured taxonomy. "
    "Contrast theoretical formulations, loss functions, compute/memory complexities, and inductive biases.\n"
    "5. CRITICAL RIGOR & DISCREPANCIES: Actively highlight discrepancies across datasets, baseline evaluation flaws, "
    "unreproducible settings, and open scientific bottlenecks.\n"
    "6. STRUCTURE: Organize the output with clear Markdown headings ('## '), sub-headings ('### '), and conclude with "
    "a complete, numbered '## References' section matching every cited source [n]."
)

REVIEW_INSTRUCTIONS = """Conduct an exhaustive, publication-grade academic literature review and comparative meta-analysis for the following request:

### User Inquiry / Research Directive:
{topic}

{instructions}

### Evidence Corpus & Comparison Tables Manifest:
{sources}

### Required Section Layout:
1. ## Executive Summary & Problem Space Formalization
   - Deep contextualization of the research domain, foundational principles, mathematical/clinical motivations, and problem definition with citations [n].
2. ## Methodological Taxonomy & Categorization
   - Systematic classification of all surveyed paradigms, architectures, and approaches. Contrast foundational assumptions and operational mechanics.
3. ## Comprehensive Comparative Analysis & Master Benchmark Table
   - Construct a complete, high-density Markdown table summarizing EVERY study in the evidence corpus:
     | Study / Reference | Method / Paradigm | Dataset / Experimental Setup | Empirical Metrics & Results | Limitations & Bottlenecks |
   - Provide an in-depth accompanying narrative analyzing trends, pareto frontiers, and performance outliers.
4. ## Thematic Deep Dive & Technical Trade-offs
   - Detailed section-by-section analysis examining algorithmic trade-offs (accuracy vs. complexity, generalization bounds, convergence properties, robustness).
5. ## Conflicting Evidence, Methodological Gaps & Limitations
   - Unpack discrepancies across experimental evaluations, unaddressed edge cases, benchmark saturation, and reproducibility gaps.
6. ## Open Research Challenges & Strategic Future Directions
   - Concrete, high-impact research trajectories and unaddressed questions for future academic investigation.
7. ## References
   - Complete, numbered bibliographic list corresponding to every [n] cited in the review.
"""

MAP_INSTRUCTIONS = """Compress the following scientific sources into an evidence digest while strictly preserving all quantitative metrics, benchmark scores, table rows, dataset names, and source citation markers [n].

Topic: {topic}

Sources:
{sources}
"""


def render_review_prompt(topic: str, sources_block: str, instructions: str = "") -> str:
    sources_text = (
        sources_block.strip()
        if sources_block and sources_block.strip()
        else "(No explicit sources attached; synthesize according to established scientific literature and state assumptions clearly.)"
    )
    instruction_block = (
        f"### Specific Methodological Guidance:\n{instructions.strip()}\n"
        if instructions and instructions.strip()
        else ""
    )
    return REVIEW_INSTRUCTIONS.format(
        topic=topic, instructions=instruction_block, sources=sources_text
    )


def render_map_prompt(topic: str, sources_block: str) -> str:
    return MAP_INSTRUCTIONS.format(topic=topic, sources=sources_block)
