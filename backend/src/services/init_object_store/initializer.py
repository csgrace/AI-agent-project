"""Object store initialization and management functions."""
from typing import Dict, Any, Optional

from ...core.global_state import get_object_store, set_object_store
from ...core.object_store import ObjectStore


def initialize_object_store(metadata: Optional[Dict[str, Any]] = None) -> None:
    """Initialize the object store.
    
    This function ensures that the global OBJECT_STORE is properly initialized.
    It can be called at application startup to ensure the object store is ready.
    
    Args:
        metadata: Optional metadata to associate with the initialization.
    """
    # The object store is already initialized at module load time
    # This function serves as a placeholder for any future initialization logic
    # and provides a consistent interface with other initialization services
    store = get_object_store()
    if not isinstance(store, ObjectStore):
        # If for some reason the store is not an ObjectStore instance, reinitialize it
        set_object_store(ObjectStore())


def clear_object_store() -> None:
    """Clear all objects from the object store.
    
    This function removes all objects and their metadata from the global OBJECT_STORE.
    It can be called at application shutdown or when a clean state is needed.
    """
    store = get_object_store()
    store.clear()


def reset_object_store() -> None:
    """Reset the object store to a fresh state.
    
    This function replaces the global OBJECT_STORE with a new, empty ObjectStore instance.
    It is useful for testing or when a complete reset of the object store is needed.
    """
    set_object_store(ObjectStore())
