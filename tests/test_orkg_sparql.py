import pytest

from app.services.orkg.sparql import SparqlGuardError, guard_query


def test_select_gets_limit_injected() -> None:
    out = guard_query("SELECT ?s WHERE { ?s ?p ?o }", max_limit=500)
    assert "LIMIT 500" in out


def test_existing_limit_is_clamped() -> None:
    out = guard_query("SELECT ?s WHERE { ?s ?p ?o } LIMIT 100000", max_limit=500)
    assert "LIMIT 500" in out
    assert "100000" not in out


def test_limit_under_cap_preserved() -> None:
    out = guard_query("SELECT ?s WHERE { ?s ?p ?o } LIMIT 10", max_limit=500)
    assert "LIMIT 10" in out


def test_ask_allowed_no_limit() -> None:
    out = guard_query("ASK { ?s ?p ?o }", max_limit=500)
    assert out.strip().lower().startswith("ask")
    assert "limit" not in out.lower()


def test_prefixed_select_allowed() -> None:
    q = "PREFIX ex: <http://example.org/>\nSELECT ?s WHERE { ?s ex:p ?o }"
    out = guard_query(q, max_limit=250)
    assert "LIMIT 250" in out


@pytest.mark.parametrize(
    "query",
    [
        "INSERT DATA { <a> <b> <c> }",
        "DELETE WHERE { ?s ?p ?o }",
        "DROP GRAPH <g>",
        "SELECT ?s WHERE { ?s ?p ?o } ; DROP GRAPH <g>",
        "LOAD <http://evil/data>",
        "",
    ],
)
def test_forbidden_queries_rejected(query: str) -> None:
    with pytest.raises(SparqlGuardError):
        guard_query(query, max_limit=500)
