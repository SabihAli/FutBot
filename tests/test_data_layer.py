"""
test_data_layer.py
==================
TDD tests for the web article scraping pipeline.
All HTTP calls are mocked — no live network requests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from src.data_layer import (
    Article,
    fetch_article_urls,
    scrape_article,
    scrape_all,
    chunk_text,
    _parse_date,
)


# ---------------------------------------------------------------------------
# Helpers — canned HTML responses
# ---------------------------------------------------------------------------

LISTING_HTML = """
<html><body>
  <a href="/sport/football/articles/c123">Match Report</a>
  <a href="/sport/football/articles/c456">Player Profile</a>
  <a href="/about">About BBC</a>
</body></html>
"""

ARTICLE_HTML = """
<html><body>
  <h1>Messi Scores Hat-Trick to Win La Liga</h1>
  <time datetime="2025-06-01T18:00:00+00:00">June 1, 2025</time>
  <article>
    <p>Lionel Messi scored three goals to seal the title.</p>
    <p>The match ended 3-0 against Real Madrid.</p>
  </article>
</body></html>
"""

ARTICLE_HTML_NO_DATE = """
<html><body>
  <h1>Transfer News Roundup</h1>
  <article>
    <p>Several clubs are vying for the striker.</p>
  </article>
</body></html>
"""


def _make_response(html: str, status_code: int = 200):
    """Creates a minimal mock requests.Response object."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.text = html
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        from requests import HTTPError
        mock.raise_for_status.side_effect = HTTPError(f"HTTP {status_code}")
    return mock


# ---------------------------------------------------------------------------
# fetch_article_urls
# ---------------------------------------------------------------------------

def test_fetch_article_urls_returns_absolute_urls(mocker):
    """Should discover article links and resolve relative hrefs to absolute URLs."""
    mocker.patch("src.data_layer._get", return_value=_make_response(LISTING_HTML))

    urls = fetch_article_urls("bbc")

    assert len(urls) == 2
    for url in urls:
        assert url.startswith("https://www.bbc.com/sport/football/articles/")


def test_fetch_article_urls_unknown_source_raises():
    """Should raise a ValueError for an unknown source name."""
    with pytest.raises(ValueError, match="Unknown source"):
        fetch_article_urls("nonexistent_source")


def test_fetch_article_urls_graceful_on_network_error(mocker):
    """Should return an empty list if the listing page fails."""
    mocker.patch("src.data_layer._get", return_value=None)

    urls = fetch_article_urls("bbc")
    assert urls == []


# ---------------------------------------------------------------------------
# scrape_article
# ---------------------------------------------------------------------------

def test_scrape_article_extracts_title_and_body(mocker):
    """Should correctly extract title, body, and date from a valid article page."""
    mocker.patch("src.data_layer._get", return_value=_make_response(ARTICLE_HTML))

    article = scrape_article("https://www.bbc.com/sport/football/articles/c123", source_name="bbc")

    assert article is not None
    assert "Messi" in article.title
    assert "hat-trick" in article.body.lower() or "three goals" in article.body.lower()
    assert article.source == "bbc"
    assert article.url == "https://www.bbc.com/sport/football/articles/c123"


def test_scrape_article_parses_date(mocker):
    """Should parse the ISO-8601 article date into a timezone-aware datetime."""
    mocker.patch("src.data_layer._get", return_value=_make_response(ARTICLE_HTML))

    article = scrape_article("https://www.bbc.com/sport/football/articles/c123", source_name="bbc")

    assert article.date_published is not None
    assert article.date_published.year == 2025
    assert article.date_published.tzinfo is not None


def test_scrape_article_returns_none_on_http_error(mocker):
    """Should return None gracefully when the HTTP request fails."""
    mocker.patch("src.data_layer._get", return_value=None)

    result = scrape_article("https://www.bbc.com/sport/football/articles/c999")
    assert result is None


def test_scrape_article_returns_none_when_no_body(mocker):
    """Should return None if no body text is extracted from the page."""
    empty_html = "<html><body><h1>Empty Article</h1></body></html>"
    mocker.patch("src.data_layer._get", return_value=_make_response(empty_html))

    result = scrape_article("https://www.bbc.com/sport/football/articles/c000", source_name="bbc")
    assert result is None


def test_scrape_article_date_is_none_when_missing(mocker):
    """Should handle articles that have no <time> element gracefully."""
    mocker.patch("src.data_layer._get", return_value=_make_response(ARTICLE_HTML_NO_DATE))

    article = scrape_article("https://www.bbc.com/sport/football/articles/c321", source_name="bbc")

    # Body exists but date is absent — article should still be returned
    assert article is not None
    assert article.date_published is None


# ---------------------------------------------------------------------------
# scrape_all — date filtering
# ---------------------------------------------------------------------------

def test_scrape_all_filters_old_articles(mocker):
    """Articles older than days_back should be excluded."""
    old_date = datetime.now(tz=timezone.utc) - timedelta(days=400)
    recent_date = datetime.now(tz=timezone.utc) - timedelta(days=10)

    old_article = Article(title="Old News", body="Old content.", url="http://example.com/old",
                          source="bbc", date_published=old_date)
    recent_article = Article(title="Recent News", body="Recent content.", url="http://example.com/new",
                             source="bbc", date_published=recent_date)

    mocker.patch("src.data_layer.fetch_article_urls", return_value=["http://example.com/old", "http://example.com/new"])
    mocker.patch("src.data_layer.scrape_article", side_effect=[old_article, recent_article])
    mocker.patch("src.data_layer.time.sleep")  # Don't actually wait

    results = scrape_all(sources=["bbc"], days_back=365)

    assert len(results) == 1
    assert results[0].title == "Recent News"


def test_scrape_all_keeps_articles_with_no_date(mocker):
    """Articles where date_published is None should be kept (safe assumption)."""
    undated_article = Article(title="Undated News", body="Some content.", url="http://example.com/undated",
                              source="bbc", date_published=None)

    mocker.patch("src.data_layer.fetch_article_urls", return_value=["http://example.com/undated"])
    mocker.patch("src.data_layer.scrape_article", return_value=undated_article)
    mocker.patch("src.data_layer.time.sleep")

    results = scrape_all(sources=["bbc"], days_back=365)
    assert len(results) == 1


def test_scrape_all_deduplicates_urls(mocker):
    """The same URL appearing in multiple sources should only be scraped once."""
    article = Article(title="Top Story", body="Content.", url="http://shared.com/article",
                      source="bbc", date_published=None)

    mocker.patch("src.data_layer.fetch_article_urls", return_value=["http://shared.com/article"])
    mock_scrape = mocker.patch("src.data_layer.scrape_article", return_value=article)
    mocker.patch("src.data_layer.time.sleep")

    scrape_all(sources=["bbc", "guardian"], days_back=365)
    # Even though two sources were scraped, the URL should only be visited once
    assert mock_scrape.call_count == 1


# ---------------------------------------------------------------------------
# chunk_text (unchanged)
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
