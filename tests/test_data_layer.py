"""
test_data_layer.py
==================
TDD tests for the data loading pipeline.
"""

import pytest
import os
from datetime import datetime, timezone

from src.data_layer import (
    Article,
    load_csv,
    chunk_text,
    _parse_date,
)

# ---------------------------------------------------------------------------
# load_csv
# ---------------------------------------------------------------------------

def test_load_csv_parses_articles(tmp_path):
    csv_file = tmp_path / "test_data.csv"
    csv_content = (
        "link,author,title,content,publish-time,source\n"
        "https://example.com/1,John Doe,Test Title 1,Body text one,2025-06-01T18:00:00+00:00,bbc\n"
        "https://example.com/2,,Test Title 2,,2025-06-02T10:00:00+00:00,bbc\n"  # Empty body
        "https://example.com/3,Jane Doe,Test Title 3,Body text three,,guardian\n"  # Missing date
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    articles = load_csv(str(csv_file))

    # Should only return 2 articles because article 2 has an empty body
    assert len(articles) == 2

    assert articles[0].title == "Test Title 1"
    assert articles[0].body == "Body text one"
    assert articles[0].url == "https://example.com/1"
    assert articles[0].source == "bbc"
    assert articles[0].date_published is not None
    assert articles[0].date_published.year == 2025

    assert articles[1].title == "Test Title 3"
    assert articles[1].body == "Body text three"
    assert articles[1].date_published is None


def test_load_csv_missing_file():
    articles = load_csv("nonexistent_file.csv")
    assert articles == []


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------

def test_chunk_text_splits_long_text():
    """Long text should be split into multiple chunks."""
    text = "football " * 600
    chunks = chunk_text(text, chunk_size=512, chunk_overlap=64)

    assert len(chunks) > 1
    assert isinstance(chunks[0], str)


def test_chunk_text_short_text_stays_single_chunk():
    """Short text should not be split."""
    text = "Messi scored a great goal."
    chunks = chunk_text(text, chunk_size=512, chunk_overlap=64)

    assert len(chunks) == 1
    assert chunks[0] == text


# ---------------------------------------------------------------------------
# _parse_date helper
# ---------------------------------------------------------------------------

def test_parse_date_iso_with_timezone():
    dt = _parse_date("2025-06-01T18:00:00+00:00")
    assert dt is not None
    assert dt.year == 2025
    assert dt.tzinfo is not None


def test_parse_date_z_suffix():
    dt = _parse_date("2025-01-15T10:30:00Z")
    assert dt is not None
    assert dt.month == 1


def test_parse_date_empty_string():
    assert _parse_date("") is None


def test_parse_date_invalid():
    assert _parse_date("not-a-date") is None
