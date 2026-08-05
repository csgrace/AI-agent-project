"""Tests for object store initialization service."""
import pytest

from src.core.global_state import get_object_store
from src.services.init_object_store import initialize_object_store, clear_object_store, reset_object_store
from src.core.object_store import ObjectStore


def test_initialize_object_store():
    """Test that initialize_object_store ensures the store is properly initialized."""
    # Call the initialize function
    initialize_object_store()
    
    # Verify the store is an ObjectStore instance
    store = get_object_store()
    assert isinstance(store, ObjectStore)


def test_clear_object_store():
    """Test that clear_object_store removes all objects from the store."""
    # First, add an object to the store
    store = get_object_store()
    test_key = store.put("test_value")
    
    # Verify the object was added
    assert test_key in store._objects
    
    # Clear the store
    clear_object_store()
    
    # Verify the object was removed
    assert test_key not in store._objects
    assert len(store._objects) == 0
    assert len(store._metadata) == 0


def test_reset_object_store():
    """Test that reset_object_store replaces the store with a new instance."""
    # Get the original store instance
    original_store = get_object_store()
    
    # Add an object to the original store
    original_store.put("test_value")
    
    # Reset the store
    reset_object_store()
    
    # Get the new store instance
    new_store = get_object_store()
    
    # Verify the store is a new instance
    assert new_store is not original_store
    assert isinstance(new_store, ObjectStore)
    
    # Verify the new store is empty
    assert len(new_store._objects) == 0
    assert len(new_store._metadata) == 0
