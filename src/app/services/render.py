"""Markdown -> sanitized HTML. Markdown is the canonical internal format; HTML is only
ever produced through this sanitizing gate so a model (or a malicious source) can never
inject active content into the preview."""

from __future__ import annotations

import markdown as md
import nh3

# Conservative allow-list: structural + inline formatting for a literature review.
_ALLOWED_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr", "blockquote", "pre", "code",
    "ul", "ol", "li", "strong", "em", "a", "sup", "sub",
    "table", "thead", "tbody", "tr", "th", "td",
}
# nh3 manages the "rel" attribute itself via link_rel, so it must not be listed here.
_ALLOWED_ATTRS = {"a": {"href", "title"}}


def markdown_to_html(markdown_text: str) -> str:
    raw_html = md.markdown(
        markdown_text or "",
        extensions=["extra", "sane_lists", "smarty"],
        output_format="html",
    )
    # nh3 (ammonia) strips scripts, event handlers, javascript: URLs, etc.
    return nh3.clean(
        raw_html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        link_rel="noopener noreferrer nofollow",
    )
