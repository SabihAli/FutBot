import os
from typing import Dict

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
    import re
    blocks = re.split(r'^\[([A-Z_]+)\]\s*$', content, flags=re.MULTILINE)
    
    # blocks[0] is everything before the first tag (usually empty)
    for i in range(1, len(blocks), 2):
        name = blocks[i]
        prompt_text = blocks[i+1].strip()
        _prompts_cache[name] = prompt_text
        
    return _prompts_cache

def get_prompt(name: str) -> str:
    """Helper to get a specific prompt by name."""
    prompts = load_prompts()
    if name not in prompts:
        raise KeyError(f"Prompt '{name}' not found in prompts.txt")
    return prompts[name]
