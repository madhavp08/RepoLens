from app.services.chunking_service import chunk_markdown, estimate_tokens


def test_chunk_markdown_splits_on_headings() -> None:
    text = """# Why Postgres

We switched from SQLite because concurrent writes locked the database.

## Tradeoffs

Operational cost increased, but writers no longer blocked each other.
"""
    chunks = chunk_markdown(text)
    assert len(chunks) >= 2
    assert "Why Postgres" in chunks[0].text
    assert "Tradeoffs" in chunks[1].text
    assert chunks[0].chunk_index == 0
    assert chunks[0].token_count == estimate_tokens(chunks[0].text)


def test_chunk_markdown_windows_long_sections() -> None:
    paragraph = "locking problems " * 200
    chunks = chunk_markdown(paragraph, max_chars=200, overlap=20)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 240 for chunk in chunks)


def test_chunk_markdown_skips_empty_input() -> None:
    assert chunk_markdown("   \n") == []


def test_chunk_markdown_advances_when_a_newline_is_near_the_window_start() -> None:
    text = "heading\n" + ("locking problems " * 400)
    chunks = chunk_markdown(text, max_chars=80, overlap=40)
    assert len(chunks) > 1
    assert all(chunk.text for chunk in chunks)
