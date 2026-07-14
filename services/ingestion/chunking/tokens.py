import tiktoken

_ENCODER = tiktoken.encoding_for_model("gpt-3.5-turbo")


def count_tokens(text: str) -> int:
    return len(_ENCODER.encode(text))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    tokens = _ENCODER.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _ENCODER.decode(tokens[:max_tokens])
