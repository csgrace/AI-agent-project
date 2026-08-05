"""In-memory object store for passing large objects across tools by key."""
from __future__ import annotations

import copy
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Type, get_args, get_origin


class ObjectStore:
    """A lightweight key-value object store with copy-on-read semantics."""

    def __init__(self) -> None:
        self._objects: Dict[str, Any] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def put(self, value: Any, metadata: Optional[Dict[str, Any]] = None, key: Optional[str] = None) -> str:
        """Store an object and return its key."""
        item_key = key or self._generate_key()
        self._objects[item_key] = copy.deepcopy(value)
        self._metadata[item_key] = {
            "created_at": datetime.utcnow().isoformat(),
            **(metadata or {}),
        }
        return item_key

    def get(self, key: str, expected_type: Optional[Type[Any]] = None) -> Any:
        """Get a deep-copied object by key with optional type check."""
        if key not in self._objects:
            raise KeyError(f"ObjectStore key not found: {key}")

        value = copy.deepcopy(self._objects[key])
        if expected_type is not None and not isinstance(value, expected_type):
            raise TypeError(
                f"ObjectStore key {key} contains {type(value).__name__}, expected {expected_type.__name__}"
            )
        return value

    def get_typed(self, key: str, expected_annotation: Any) -> Any:
        """Get an item by key and validate it against a type annotation.

        Supported annotations include concrete types (e.g. ``CalendarEvent``),
        ``List[T]``, ``Dict[K, V]``, and ``Optional[T]``/``Union``.
        """
        value = self.get(key)
        self._validate_against_annotation(value, expected_annotation, path=f"ObjectStore key {key}")
        return value

    def clone(self, key: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Clone an existing item into a new key and return the new key."""
        value = self.get(key)
        base_metadata = self.get_metadata(key)
        merged_metadata = {**base_metadata, **(metadata or {}), "cloned_from": key}
        return self.put(value=value, metadata=merged_metadata)

    def get_metadata(self, key: str) -> Dict[str, Any]:
        """Get metadata for an item key."""
        if key not in self._metadata:
            raise KeyError(f"ObjectStore metadata not found: {key}")
        return copy.deepcopy(self._metadata[key])

    def delete(self, key: str) -> bool:
        """Delete an item by key and return whether it existed."""
        existed = key in self._objects
        self._objects.pop(key, None)
        self._metadata.pop(key, None)
        return existed

    def clear(self) -> None:
        """Clear all objects in the store."""
        self._objects.clear()
        self._metadata.clear()

    @staticmethod
    def _generate_key() -> str:
        """Generate a short, collision-resistant key."""
        return f"obj_{uuid.uuid4().hex[:12]}"

    @classmethod
    def _validate_against_annotation(cls, value: Any, annotation: Any, path: str) -> None:
        """Recursively validate a value against a typing annotation."""
        origin = get_origin(annotation)
        args = get_args(annotation)

        if annotation is Any:
            return

        if origin is None:
            if annotation is type(None):
                if value is not None:
                    raise TypeError(f"{path} must be None, got {type(value).__name__}")
                return
            if not isinstance(value, annotation):
                raise TypeError(f"{path} must be {annotation.__name__}, got {type(value).__name__}")
            return

        if origin is list:
            if not isinstance(value, list):
                raise TypeError(f"{path} must be list, got {type(value).__name__}")
            item_annotation = args[0] if args else Any
            for idx, item in enumerate(value):
                cls._validate_against_annotation(item, item_annotation, path=f"{path}[{idx}]")
            return

        if origin is dict:
            if not isinstance(value, dict):
                raise TypeError(f"{path} must be dict, got {type(value).__name__}")
            key_annotation = args[0] if len(args) >= 1 else Any
            val_annotation = args[1] if len(args) >= 2 else Any
            for k, v in value.items():
                cls._validate_against_annotation(k, key_annotation, path=f"{path}.<key>")
                cls._validate_against_annotation(v, val_annotation, path=f"{path}[{k!r}]")
            return

        # Optional[T] and Union types.
        if str(origin).endswith("Union"):
            for option in args:
                try:
                    cls._validate_against_annotation(value, option, path)
                    return
                except TypeError:
                    continue
            option_names = [getattr(opt, "__name__", str(opt)) for opt in args]
            raise TypeError(
                f"{path} must match one of {option_names}, got {type(value).__name__}"
            )

        raise TypeError(f"{path} uses unsupported annotation: {annotation}")
