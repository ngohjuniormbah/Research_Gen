"""Citation formatting. The review stores its sources as CSL-JSON (so more styles can be
added later) plus a rendered APA bibliography (one style is enough for now)."""

from __future__ import annotations

from typing import Any


def _split_name(name: str) -> tuple[str, str]:
    """Best-effort split into (family, given). Handles "Family, Given" and "Given Family"."""
    name = name.strip()
    if not name:
        return "", ""
    if "," in name:
        family, _, given = name.partition(",")
        return family.strip(), given.strip()
    parts = name.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def _initials(given: str) -> str:
    return " ".join(f"{p[0]}." for p in given.replace(".", " ").split() if p)


def source_to_csl(source: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for name in source.get("authors", []) or []:
        family, given = _split_name(str(name))
        entry: dict[str, str] = {"family": family}
        if given:
            entry["given"] = given
        authors.append(entry)

    item: dict[str, Any] = {
        "id": f"source-{source.get('index', 0)}",
        "type": "article-journal",
        "title": source.get("title", "") or "",
    }
    if authors:
        item["author"] = authors
    if source.get("year"):
        item["issued"] = {"date-parts": [[int(source["year"])]]}
    if source.get("venue"):
        item["container-title"] = source["venue"]
    if source.get("doi"):
        item["DOI"] = source["doi"]
    return item


def to_csl_json(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [source_to_csl(s) for s in sources]


def _apa_authors(authors: list[str]) -> str:
    formatted = []
    for name in authors:
        family, given = _split_name(str(name))
        initials = _initials(given)
        formatted.append(f"{family}, {initials}".strip().rstrip(",") if initials else family)
    if not formatted:
        return ""
    if len(formatted) == 1:
        return formatted[0]
    return ", ".join(formatted[:-1]) + ", & " + formatted[-1]


def format_apa(source: dict[str, Any]) -> str:
    """Render a single source as an APA-style reference string."""
    authors = _apa_authors(source.get("authors", []) or [])
    year = source.get("year")
    title = (source.get("title") or "").strip()
    venue = (source.get("venue") or "").strip()
    doi = (source.get("doi") or "").strip()

    parts = []
    if authors:
        parts.append(f"{authors}")
    parts.append(f"({year})." if year else "(n.d.).")
    if title:
        parts.append(f"{title}.")
    if venue:
        parts.append(f"*{venue}*.")
    if doi:
        parts.append(f"https://doi.org/{doi}")
    return " ".join(parts).strip()


def build_apa_bibliography(sources: list[dict[str, Any]]) -> list[str]:
    return [format_apa(s) for s in sources]
