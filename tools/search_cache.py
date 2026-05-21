import json
import os
import threading
from datetime import datetime, timezone

CACHE_FILE = "cache/search_cache.json"
_TTL = 24 * 3600  # seconds
_lock = threading.Lock()


def _load() -> dict:
    if not os.path.isfile(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_cached(query: str) -> str | None:
    """캐시에서 결과 반환. 없거나 24시간 경과 시 None."""
    with _lock:
        entry = _load().get(query)
        if not entry:
            return None
        if datetime.now(timezone.utc).timestamp() - entry["saved_at"] > _TTL:
            return None
        return entry["result"]


def set_cached(query: str, result: str) -> None:
    """쿼리 결과를 캐시에 저장."""
    with _lock:
        cache = _load()
        cache[query] = {
            "result": result,
            "saved_at": datetime.now(timezone.utc).timestamp(),
        }
        _save(cache)
