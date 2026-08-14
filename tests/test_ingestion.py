import io
import json

import pandas as pd
import pytest

from app.schemas.source_record import SourceRecord
from app.services.ingestion import normalize_records, parse_bytes
from app.services.ingestion.parsers import ParseError, detect_kind

CSV = (
    "title,abstract,authors,year,journal,doi\n"
    "Deep Learning,A survey of DL.,\"Smith, John; Doe, Jane\",2019,Nature,10.1/ABC\n"
    "Transformers,Attention models.,Vaswani et al.,2017,NeurIPS,\n"
)


def test_detect_kind() -> None:
    assert detect_kind("a.csv") == "csv"
    assert detect_kind("a.xlsx") == "xlsx"
    assert detect_kind("a.pdf") == "pdf"
    assert detect_kind("a.json") == "json"
    with pytest.raises(ParseError):
        detect_kind("a.txt")


def test_parse_csv() -> None:
    records = parse_bytes(CSV.encode(), "papers.csv")
    assert len(records) == 2
    first = records[0]
    assert first.title == "Deep Learning"
    assert first.authors == ["Smith, John", "Doe, Jane"]
    assert first.year == 2019
    assert first.venue == "Nature"
    assert first.doi == "10.1/ABC"


def test_parse_xlsx() -> None:
    df = pd.read_csv(io.StringIO(CSV))
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    records = parse_bytes(buf.getvalue(), "papers.xlsx")
    assert len(records) == 2
    assert records[1].title == "Transformers"
    assert records[1].year == 2017


def test_parse_json_list_and_wrapped() -> None:
    payload = [{"title": "A", "year": 2020, "authors": ["X"]}]
    recs = parse_bytes(json.dumps(payload).encode(), "d.json")
    assert recs[0].title == "A" and recs[0].year == 2020

    wrapped = {"records": [{"title": "B", "doi": "10.9/z"}]}
    recs2 = parse_bytes(json.dumps(wrapped).encode(), "d.json")
    assert recs2[0].title == "B" and recs2[0].doi == "10.9/z"


def test_parse_pdf() -> None:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "A Neat Paper Title\nAbstract: This is the abstract text.")
    data = doc.tobytes()
    doc.close()
    records = parse_bytes(data, "paper.pdf")
    assert len(records) == 1
    assert records[0].full_text
    assert "abstract" in records[0].abstract.lower() or records[0].abstract == "" or \
        "abstract text" in records[0].full_text.lower()


def test_parse_jsonld_graph_keeps_only_works() -> None:
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@id": "paper1",
                "@type": "ScholarlyArticle",
                "name": "Deep Learning",
                "description": "A survey of DL.",
                "datePublished": "2019",
                "author": [{"@type": "Person", "name": "Jane Smith"}],
                "doi": "10.1/abc",
            },
            {"@id": "person1", "@type": "Person", "name": "Jane Smith"},
            {"@id": "venue1", "@type": "Periodical", "name": "Nature"},
        ],
    }
    recs = parse_bytes(json.dumps(payload).encode(), "annotations.jsonld")
    assert len(recs) == 1  # article only; person/venue nodes are skipped
    assert recs[0].title == "Deep Learning"
    assert recs[0].year == 2019
    assert recs[0].doi == "10.1/abc"
    assert recs[0].authors == ["Jane Smith"]


def test_parse_jsonld_full_iri_keys() -> None:
    payload = [
        {
            "@id": "p",
            "@type": "http://purl.org/spar/fabio/ResearchPaper",
            "http://purl.org/dc/terms/title": "Graph Neural Networks",
            "http://purl.org/dc/terms/abstract": "GNN overview.",
        }
    ]
    recs = parse_bytes(json.dumps(payload).encode(), "kg.jsonld")
    assert len(recs) == 1
    assert recs[0].title == "Graph Neural Networks"
    assert "GNN overview" in recs[0].abstract


def test_normalize_dedupes_by_doi() -> None:
    records = [
        SourceRecord(title="Deep Learning", doi="10.1/ABC", year=2019),
        SourceRecord(title="Deep  Learning ", doi="https://doi.org/10.1/abc", abstract="more"),
    ]
    out = normalize_records(records)
    assert len(out) == 1
    # Complementary fields merged: abstract from the duplicate filled in.
    assert out[0].abstract == "more"
    assert out[0].doi == "10.1/abc"


def test_normalize_drops_empty_and_cleans_whitespace() -> None:
    records = [
        SourceRecord(title="  Spaced   Title  ", authors=["  A  ", "A"]),
        SourceRecord(title="", abstract="", full_text=None),
    ]
    out = normalize_records(records)
    assert len(out) == 1
    assert out[0].title == "Spaced Title"
    assert out[0].authors == ["A"]  # de-duplicated author


def test_unsupported_type_raises() -> None:
    with pytest.raises(ParseError):
        parse_bytes(b"hello", "notes.txt")
