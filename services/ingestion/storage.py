import os


def _client():
    from minio import Minio

    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "futbot")
    secret_key = os.getenv("MINIO_SECRET_KEY", "futbotminio")
    secure = os.getenv("MINIO_SECURE", "false").lower() in {"1", "true", "yes"}
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def fetch_object_bytes(storage_key: str) -> bytes:
    bucket = os.getenv("MINIO_BUCKET", "futbot-projects")
    client = _client()
    response = client.get_object(bucket, storage_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
