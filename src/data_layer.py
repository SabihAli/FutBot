"""
data_layer.py
=============
Data loading pipeline for football news articles.

Flow:
    load_csv()     — loads articles from a given CSV file
    chunk_text()   — splits article body into token-bounded chunks
"""

import logging
import csv
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Optional

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
# Core data loading functions
# ---------------------------------------------------------------------------

def load_csv(csv_path: str) -> List[Article]:
    """
    Loads articles from a CSV file.
    CSV columns expected: link,author,title,content,publish-time,source
    """
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
# Text chunking
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
