"""
data_layer.py
=============
Web scraping pipeline for football news articles.

Flow:
    scrape_all()
        └─> fetch_article_urls()   — discovers article URLs from listing pages
        └─> scrape_article()       — extracts title + body + metadata from a URL
        └─> (date filter)          — drops articles older than `days_back` days
    chunk_text()                   — splits article body into token-bounded chunks
"""

import time
import logging
import csv
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Article data structure
# ---------------------------------------------------------------------------

@dataclass
class Article:
    title: str
    body: str
    url: str
    source: str
    date_published: Optional[datetime] = field(default=None)


# ---------------------------------------------------------------------------
# Source configurations
# ---------------------------------------------------------------------------

# Each entry defines how to discover article links and parse article content
# for a given football news site.
SOURCE_CONFIGS = {
    "bbc": {
        "listing_urls": [
            "https://www.bbc.com/sport/football",
        ],
        "article_link_selector": "a[href*='/sport/football/articles/']",
        "base_url": "https://www.bbc.com",
        "title_selector": "h1",
        "body_selector": "article p",
        "date_selector": "time",
        "date_attr": "datetime",
    },
    "guardian": {
        "listing_urls": [
            "https://www.theguardian.com/football",
        ],
        "article_link_selector": "a[href*='theguardian.com/football/']",
        "base_url": "",
        "title_selector": "h1",
        "body_selector": "div.article-body-commercial-selector p, div[data-gu-name='body'] p",
        "date_selector": "time",
        "date_attr": "datetime",
    },
    "skysports": {
        "listing_urls": [
            "https://www.skysports.com/football/news",
        ],
        "article_link_selector": "a[href*='skysports.com/football/news/']",
        "base_url": "https://www.skysports.com",
        "title_selector": "h1",
        "body_selector": "div.sdc-article-body p",
        "date_selector": "time",
        "date_attr": "datetime",
    },
}

# Polite scraping headers — identifies us without impersonating a browser fully
REQUEST_HEADERS = {
    "User-Agent": (
        "FootballRAGBot/1.0 (research project; respectful scraper; "
        "contact: admin@example.com)"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}

REQUEST_TIMEOUT = 10   # seconds
RATE_LIMIT_DELAY = 1.5  # seconds between requests


# ---------------------------------------------------------------------------
# Core scraping functions
# ---------------------------------------------------------------------------

def fetch_article_urls(source_name: str, max_pages: int = 1) -> List[str]:
    """
    Scrapes listing page(s) for a given source and returns discovered article URLs.

    Args:
        source_name: Key in SOURCE_CONFIGS (e.g. "bbc", "guardian").
        max_pages:   Number of listing pages to scrape (for pagination).

    Returns:
        De-duplicated list of absolute article URLs.
    """
    config = SOURCE_CONFIGS.get(source_name)
    if not config:
        raise ValueError(f"Unknown source: '{source_name}'. Valid: {list(SOURCE_CONFIGS.keys())}")

    urls: set[str] = set()

    for listing_url in config["listing_urls"][:max_pages]:
        try:
            resp = _get(listing_url)
            if resp is None:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            links = soup.select(config["article_link_selector"])
            for link in links:
                href = link.get("href", "")
                if href.startswith("http"):
                    urls.add(href)
                elif href.startswith("/"):
                    urls.add(config["base_url"] + href)
        except Exception as exc:
            logger.warning("Failed to fetch listing page %s: %s", listing_url, exc)

    return list(urls)


def scrape_article(url: str, source_name: str = "bbc") -> Optional[Article]:
    """
    Visits a single article URL and extracts its title, body, source, and date.

    Args:
        url:         The full URL of the article.
        source_name: Key in SOURCE_CONFIGS used to select CSS selectors.

    Returns:
        An Article dataclass, or None if the page could not be scraped.
    """
    config = SOURCE_CONFIGS.get(source_name, SOURCE_CONFIGS["bbc"])

    resp = _get(url)
    if resp is None:
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # --- Title ---
    title_tag = soup.select_one(config["title_selector"])
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"

    # --- Body ---
    paragraphs = soup.select(config["body_selector"])
    body = " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    if not body:
        logger.debug("No body text found for %s", url)
        return None

    # --- Date ---
    date_published: Optional[datetime] = None
    date_tag = soup.select_one(config["date_selector"])
    if date_tag:
        raw_date = date_tag.get(config.get("date_attr", "datetime"), "")
        date_published = _parse_date(raw_date)

    return Article(
        title=title,
        body=body,
        url=url,
        source=source_name,
        date_published=date_published,
    )


def scrape_all(
    sources: Optional[List[str]] = None,
    days_back: int = 365,
    max_pages_per_source: int = 1,
) -> List[Article]:
    """
    Top-level orchestrator. Scrapes all configured sources, filters by date,
    and returns a deduplicated list of recent articles.

    Args:
        sources:               List of source keys to scrape. Defaults to all.
        days_back:             Maximum age (in days) of articles to retain.
        max_pages_per_source:  Listing pages to crawl per source.

    Returns:
        List of Article objects published within the last `days_back` days.
    """
    if sources is None:
        sources = list(SOURCE_CONFIGS.keys())

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)
    articles: List[Article] = []
    seen_urls: set[str] = set()

    for source_name in sources:
        logger.info("Scraping source: %s", source_name)
        urls = fetch_article_urls(source_name, max_pages=max_pages_per_source)

        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            article = scrape_article(url, source_name=source_name)
            time.sleep(RATE_LIMIT_DELAY)

            if article is None:
                continue

            # Date filter — keep articles with unknown dates to be safe
            if article.date_published and article.date_published < cutoff:
                logger.debug("Skipping old article (%s): %s", article.date_published, url)
                continue

            articles.append(article)

    return articles

def load_csv(csv_path: str, days_back: int = 365) -> List[Article]:
    """
    Loads articles from a CSV file.
    CSV columns expected: link,author,title,content,publish-time,source
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)
    articles: List[Article] = []

    if not os.path.exists(csv_path):
        logger.warning(f"CSV file not found: {csv_path}")
        return articles

    # The CSV can be large; but we read it fully to memory as Article objects
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # parse date
            pub_time_str = row.get("publish-time", "")
            date_published = None
            if pub_time_str and pub_time_str.lower() != "publish time not found":
                date_published = _parse_date(pub_time_str)

            # filter by date
            if date_published and date_published < cutoff:
                continue

            # We assume 'content' holds the body
            body = row.get("content", "").strip()
            if not body:
                continue

            article = Article(
                title=row.get("title", ""),
                body=body,
                url=row.get("link", ""),
                source=row.get("source", ""),
                date_published=date_published
            )
            articles.append(article)

    logger.info(f"Loaded {len(articles)} articles from CSV.")
    return articles

# ---------------------------------------------------------------------------
# Text chunking (unchanged — works for any natural language text)
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = 512, chunk_overlap: int = 64) -> List[str]:
    """
    Splits text into token-bounded chunks ready for vector embedding.

    Args:
        text:          Full article body or any natural language string.
        chunk_size:    Maximum number of tokens per chunk.
        chunk_overlap: Number of tokens shared between adjacent chunks.

    Returns:
        List of text strings.
    """
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        model_name="gpt-3.5-turbo",
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return splitter.split_text(text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url: str) -> Optional[requests.Response]:
    """Executes a GET request with standard headers. Returns None on error."""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp
    except requests.RequestException as exc:
        logger.warning("HTTP error fetching %s: %s", url, exc)
        return None


def _parse_date(raw: str) -> Optional[datetime]:
    """Parses an ISO-8601 datetime string into a timezone-aware datetime."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None
