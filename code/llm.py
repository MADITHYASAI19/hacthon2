"""xAI Grok API client (stdlib urllib only) for intent classification."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

XAI_API_URL = "https://api.x.ai/v1/chat/completions"

# Cost estimates per 1,000,000 tokens (USD) - clearly labelled as estimates
# Based on public xAI pricing estimates
MODEL_COST_PER_M_TOKENS = {
    "grok-beta": {"input": 5.00, "output": 15.00},
    "grok-2-1212": {"input": 2.00, "output": 10.00},
    "grok-2-vision-1212": {"input": 2.00, "output": 10.00},
    "grok-2": {"input": 2.00, "output": 10.00},
    "default": {"input": 2.00, "output": 10.00},
}


def load_dotenv(dotenv_path: Optional[Path] = None):
    """Load local .env file if present (stdlib-only lightweight parser)."""
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return
    try:
        content = dotenv_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


# Automatically try loading .env on import
load_dotenv()


def get_cache_path() -> Path:
    cache_dir = Path(__file__).resolve().parent / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "intent_cache.json"


def read_cache() -> Dict[str, Any]:
    cache_file = get_cache_path()
    if not cache_file.exists():
        return {}
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_cache(cache: Dict[str, Any]):
    cache_file = get_cache_path()
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def estimate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate estimated cost based on token counts."""
    pricing = MODEL_COST_PER_M_TOKENS.get(model_name, MODEL_COST_PER_M_TOKENS["default"])
    cost = (prompt_tokens / 1_000_000.0) * pricing["input"] + (
        completion_tokens / 1_000_000.0
    ) * pricing["output"]
    return cost


def query_grok_chat(
    prompt: str,
    system_prompt: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.0,
    max_retries: int = 3,
    timeout_s: float = 30.0,
) -> Dict[str, Any]:
    """Call the xAI chat completions endpoint using urllib."""
    load_dotenv()
    key = api_key or os.environ.get("XAI_API_KEY")
    if not key:
        raise ValueError("XAI_API_KEY environment variable is not set.")

    model = model_name or os.environ.get("GROK_MODEL")
    if not model:
        raise ValueError(
            "GROK_MODEL environment variable is not set. "
            "Please check current supported model names in the xAI documentation (e.g., grok-beta, grok-2-1212)."
        )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "User-Agent": "GhostDataAuditAgent/1.0",
    }

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    data_bytes = json.dumps(body).encode("utf-8")

    last_err = None
    for attempt in range(max_retries):
        req = urllib.request.Request(XAI_API_URL, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                resp_body = resp.read().decode("utf-8")
                return json.loads(resp_body)
        except urllib.error.HTTPError as e:
            status = e.code
            err_body = e.read().decode("utf-8", errors="ignore")
            last_err = RuntimeError(f"xAI API HTTP {status}: {err_body}")
            if status in (429, 500, 502, 503, 504):
                sleep_time = (2 ** attempt) * 1.5
                time.sleep(sleep_time)
                continue
            raise last_err
        except Exception as e:
            last_err = e
            sleep_time = (2 ** attempt) * 1.5
            time.sleep(sleep_time)
            continue

    raise RuntimeError(f"xAI API request failed after {max_retries} retries: {last_err}")


def classify_intent_grok(
    request_text: str,
    system_prompt_path: Optional[Path] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Tuple[Dict[str, str], int, int, float, bool]:
    """Classify intent with Grok with disk caching and robust parsing.

    Returns:
        (parsed_dict, prompt_tokens, completion_tokens, cost, from_cache)
    """
    load_dotenv()
    model = model_name or os.environ.get("GROK_MODEL")
    if not model:
        raise ValueError(
            "GROK_MODEL environment variable is not set. "
            "Please check current supported model names in the xAI documentation."
        )

    if system_prompt_path is None:
        system_prompt_path = Path(__file__).resolve().parent / "prompts" / "intent.md"
    system_prompt = system_prompt_path.read_text(encoding="utf-8")

    # Cache lookup by sha256(request_text + model)
    cache_key = hashlib.sha256(f"{model}::{request_text}".encode("utf-8")).hexdigest()
    cache = read_cache()
    if cache_key in cache:
        cached = cache[cache_key]
        return cached["result"], 0, 0, 0.0, True

    response = query_grok_chat(
        prompt=request_text,
        system_prompt=system_prompt,
        api_key=api_key,
        model_name=model,
    )

    usage = response.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cost = estimate_cost(model, prompt_tokens, completion_tokens)

    content = ""
    choices = response.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")

    # Clean markdown fences if any
    content_clean = content.strip()
    if content_clean.startswith("```"):
        content_clean = re.sub(r"^```(?:json)?\s*", "", content_clean)
        content_clean = re.sub(r"\s*```$", "", content_clean)
        content_clean = content_clean.strip()

    try:
        parsed = json.loads(content_clean)
    except Exception:
        # Fallback regex extraction
        m_intent = re.search(r'"intent"\s*:\s*"(DELETE|NOT_DELETE)"', content_clean, re.IGNORECASE)
        m_reason = re.search(r'"reason"\s*:\s*"([^"]+)"', content_clean)
        parsed = {
            "intent": m_intent.group(1).upper() if m_intent else "DELETE",
            "reason": m_reason.group(1) if m_reason else "Parsed via regex fallback",
        }

    # Store in cache
    cache[cache_key] = {
        "model": model,
        "result": parsed,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost": cost,
    }
    write_cache(cache)

    return parsed, prompt_tokens, completion_tokens, cost, False
