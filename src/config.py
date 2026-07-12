import os

HOT_CONTEXT_WINDOW = int(os.environ.get("HOT_CONTEXT_WINDOW", "10"))
SNAPSHOT_MAX_TOKENS = int(os.environ.get("SNAPSHOT_MAX_TOKENS", "300"))
INGEST_ASYNC_IMAGE_THRESHOLD = int(os.environ.get("INGEST_ASYNC_IMAGE_THRESHOLD", "3"))
INGEST_IMAGE_DELAY_MS = int(os.environ.get("INGEST_IMAGE_DELAY_MS", "500"))
CHUNK_TARGET_TOKENS = int(os.environ.get("CHUNK_TARGET_TOKENS", "400"))
CHUNK_OVERLAP_SENTENCES = int(os.environ.get("CHUNK_OVERLAP_SENTENCES", "2"))
TABLE_CHUNK_ROWS = int(os.environ.get("TABLE_CHUNK_ROWS", "10"))
INGEST_OCR_ENABLED = os.environ.get("INGEST_OCR_ENABLED", "true").lower() in {"1", "true", "yes"}
INGEST_OCR_MIN_CONFIDENCE = int(os.environ.get("INGEST_OCR_MIN_CONFIDENCE", "60"))
