import os

HOT_CONTEXT_WINDOW = int(os.environ.get("HOT_CONTEXT_WINDOW", "10"))
SNAPSHOT_MAX_TOKENS = int(os.environ.get("SNAPSHOT_MAX_TOKENS", "300"))
