"""Tools for reading ObjectStore items by key."""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import tool

from ...core.global_state import get_object_store


def _to_jsonable(value: Any, max_items: int, max_string_length: int) -> Any:
    """Convert values into JSON-serializable payloads with safe truncation."""
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        if len(value) <= max_string_length:
            return value
        return value[:max_string_length] + "..."

    if isinstance(value, list):
        items = value[:max_items]
        converted = [_to_jsonable(item, max_items, max_string_length) for item in items]
        if len(value) > max_items:
            converted.append(
                {
                    "_truncated": True,
                    "remaining_items": len(value) - max_items,
                }
            )
        return converted

    if isinstance(value, dict):
        keys = list(value.keys())[:max_items]
        converted = {
            str(k): _to_jsonable(value[k], max_items, max_string_length) for k in keys
        }
        if len(value) > max_items:
            converted["_truncated"] = True
            converted["_remaining_keys"] = len(value) - max_items
        return converted

    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _to_jsonable(value.model_dump(), max_items, max_string_length)

    if hasattr(value, "__dict__"):
        return _to_jsonable(vars(value), max_items, max_string_length)

    return repr(value)


@tool
def read_object_store_item(
    object_store_key: str,
    max_items: int = 20,
    max_string_length: int = 2000,
) -> str:
    """Read and print one ObjectStore item by key.

    Useful when another tool returned an object_store_key and the agent needs
    to inspect actual content.

    Args:
        object_store_key: Key returned by ObjectStore-producing tools.
        max_items: Maximum number of list items or dict keys to include.
        max_string_length: Maximum length of each string field before truncation.

    Returns:
        JSON string with object metadata and content preview.

    Raises:
        ValueError: If key does not exist in ObjectStore.
    """
    store = get_object_store()
    try:
        value = store.get(object_store_key)
        metadata = store.get_metadata(object_store_key)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc

    payload = {
        "ok": True,
        "action": "read_object_store_item",
        "object_store_key": object_store_key,
        "value_type": type(value).__name__,
        "metadata": metadata,
        "value": _to_jsonable(value, max_items=max_items, max_string_length=max_string_length),
    }
    return json.dumps(payload, ensure_ascii=False)
