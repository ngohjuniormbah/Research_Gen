import time

import pytest

from app.core.crypto import TokenCipher
from app.core.signing import SignatureError, TokenSigner
from app.services.citations import build_apa_bibliography, format_apa, to_csl_json
from app.services.export import ExportError, FakeRenderer, content_type_for
from app.services.orkg.tokens import OidcToken, TokenStore
from app.services.render import markdown_to_html

# --- render / sanitization --------------------------------------------------- #


def test_markdown_renders_headings_and_lists() -> None:
    html = markdown_to_html("# Title\n\n- one\n- two\n")
    assert "<h1>" in html
    assert "<li>one</li>" in html


def test_markdown_strips_scripts_and_handlers() -> None:
    dangerous = "Hello <script>alert('x')</script> [link](javascript:alert(1))"
    html = markdown_to_html(dangerous)
    assert "<script>" not in html
    assert "javascript:" not in html
    assert "alert" not in html or "<script>" not in html


def test_markdown_adds_noopener_to_links() -> None:
    html = markdown_to_html("[ok](https://example.org)")
    assert "https://example.org" in html
    assert "noopener" in html


# --- citations --------------------------------------------------------------- #

_SOURCE = {
    "index": 1,
    "title": "Attention Is All You Need",
    "authors": ["Vaswani, Ashish", "Noam Shazeer"],
    "year": 2017,
    "venue": "NeurIPS",
    "doi": "10.5555/abc",
}


def test_apa_formatting() -> None:
    text = format_apa(_SOURCE)
    assert "Vaswani, A." in text
    assert "(2017)" in text
    assert "Attention Is All You Need" in text
    assert "https://doi.org/10.5555/abc" in text


def test_csl_json_shape() -> None:
    csl = to_csl_json([_SOURCE])
    item = csl[0]
    assert item["type"] == "article-journal"
    assert item["DOI"] == "10.5555/abc"
    assert item["issued"]["date-parts"] == [[2017]]
    assert item["author"][0]["family"] == "Vaswani"


def test_apa_bibliography_handles_missing_fields() -> None:
    bib = build_apa_bibliography([{"index": 1, "title": "Untitled"}])
    assert bib[0].startswith("(n.d.)") or "Untitled" in bib[0]


# --- signing ----------------------------------------------------------------- #


def test_signer_roundtrip() -> None:
    signer = TokenSigner("secret")
    token = signer.sign({"sk": "key123", "ct": "application/pdf"}, ttl_s=60)
    payload = signer.verify(token)
    assert payload["sk"] == "key123"


def test_signer_rejects_tampering() -> None:
    signer = TokenSigner("secret")
    token = signer.sign({"sk": "key"}, ttl_s=60)
    with pytest.raises(SignatureError):
        signer.verify(token[:-2] + ("aa" if not token.endswith("aa") else "bb"))


def test_signer_rejects_expired() -> None:
    signer = TokenSigner("secret")
    token = signer.sign({"sk": "key", "exp": int(time.time()) - 5}, ttl_s=-5)
    with pytest.raises(SignatureError):
        signer.verify(token)


def test_signer_wrong_secret() -> None:
    token = TokenSigner("secret-a").sign({"sk": "k"}, ttl_s=60)
    with pytest.raises(SignatureError):
        TokenSigner("secret-b").verify(token)


# --- crypto / token encryption ---------------------------------------------- #


def test_cipher_roundtrip_with_key() -> None:
    from cryptography.fernet import Fernet

    cipher = TokenCipher(Fernet.generate_key().decode())
    assert cipher.active
    enc = cipher.encrypt("s3cr3t")
    assert enc != "s3cr3t"
    assert cipher.decrypt(enc) == "s3cr3t"


def test_cipher_passthrough_without_key() -> None:
    cipher = TokenCipher("")
    assert not cipher.active
    enc = cipher.encrypt("hello")
    assert enc != "hello"  # marked, not raw
    assert cipher.decrypt(enc) == "hello"


def test_cipher_accepts_arbitrary_secret() -> None:
    # A non-Fernet secret (as a platform 'generate secret' would produce) still works.
    cipher = TokenCipher("any-old-platform-generated-secret-value")
    assert cipher.active
    assert cipher.decrypt(cipher.encrypt("tok")) == "tok"


def test_database_url_scheme_is_normalized() -> None:
    from app.config import Settings

    s = Settings(database_url="postgres://u:p@host:5432/db")
    assert s.database_url.startswith("postgresql+asyncpg://")
    s2 = Settings(database_url="postgresql://u:p@host/db")
    assert s2.database_url.startswith("postgresql+asyncpg://")
    # Already-async and sqlite URLs are left untouched.
    assert Settings(database_url="sqlite+aiosqlite://").database_url == "sqlite+aiosqlite://"


def test_openai_provider_auto_registered_from_key() -> None:
    from app.config import Settings
    from app.services.llm.registry import ProviderRegistry

    s = Settings(openai_api_key="sk-test-123", openai_model="gpt-4o")
    assert "openai" in s.llm_providers
    provider = ProviderRegistry(s).get("openai")
    assert provider.model == "gpt-4o"
    assert provider.key == "openai"


def test_no_openai_provider_without_key() -> None:
    from app.config import Settings

    assert "openai" not in Settings().llm_providers


def test_token_store_encrypts_at_rest() -> None:
    from cryptography.fernet import Fernet

    cipher = TokenCipher(Fernet.generate_key().decode())
    store = TokenStore(cipher)
    store.set("user-1", OidcToken(access_token="AT", refresh_token="RT", expires_at=0))
    stored = store._tokens["user-1"]
    assert "AT" not in stored.access_token_enc
    assert "RT" not in stored.refresh_token_enc
    got = store.get("user-1")
    assert got is not None and got.access_token == "AT" and got.refresh_token == "RT"


# --- export renderer --------------------------------------------------------- #


def test_fake_renderer_formats() -> None:
    r = FakeRenderer()
    assert r.render("# hi", "md").decode() == "# hi"
    assert r.render("# hi", "pdf", title="T").startswith(b"%PDF")
    assert b"FAKE-DOCX" in r.render("# hi", "docx", title="T")


def test_content_type_lookup() -> None:
    assert content_type_for("pdf") == "application/pdf"
    with pytest.raises(ExportError):
        content_type_for("txt")
