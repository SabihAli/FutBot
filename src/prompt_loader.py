import os
from typing import Dict, Tuple
import re

_PROMPTS_FILE = os.path.join(os.path.dirname(__file__), "prompts.txt")
_prompts_cache: Dict[str, str] = {}


def load_prompts() -> Dict[str, str]:
    """Loads all prompts from prompts.txt into a dictionary, caching them."""
    global _prompts_cache
    if _prompts_cache:
        return _prompts_cache

    if not os.path.exists(_PROMPTS_FILE):
        raise FileNotFoundError(f"Prompts file not found at {_PROMPTS_FILE}")

    with open(_PROMPTS_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by [PROMPT_NAME] pattern
    blocks = re.split(r'^\[([A-Z_]+)\]\s*$', content, flags=re.MULTILINE)

    # blocks[0] is everything before the first tag (usually empty)
    for i in range(1, len(blocks), 2):
        name = blocks[i]
        prompt_text = blocks[i + 1].strip()
        _prompts_cache[name] = prompt_text

    return _prompts_cache


def get_prompt(name: str) -> str:
    """Helper to get a specific prompt by name.

    For backward compatibility this returns the full prompt string.
    For prompts that have been split into _SYSTEM / _USER parts, calling
    get_prompt('FOO') will raise a KeyError — use get_prompt_parts() instead.
    """
    prompts = load_prompts()
    if name not in prompts:
        raise KeyError(f"Prompt '{name}' not found in prompts.txt")
    return prompts[name]


def get_prompt_parts(name: str) -> Tuple[str, str]:
    """Return (system_prompt, user_template) for a split prompt.

    Looks up '{name}_SYSTEM' and '{name}_USER' from prompts.txt.
    Both halves are returned as raw template strings — the caller is
    responsible for calling .format(**kwargs) on the user template.

    Raises KeyError if either part is missing.
    """
    prompts = load_prompts()
    system_key = f"{name}_SYSTEM"
    user_key = f"{name}_USER"
    if system_key not in prompts:
        raise KeyError(f"System prompt '{system_key}' not found in prompts.txt")
    if user_key not in prompts:
        raise KeyError(f"User prompt '{user_key}' not found in prompts.txt")
    return prompts[system_key], prompts[user_key]
