"""Global registry of running script executions for kill support.

Maintains a thread-safe dictionary mapping execution_id -> subprocess.Popen
so that the kill API endpoint can terminate a running script by ID.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional

import subprocess

# Global registry: execution_id -> Popen process
_RUNNING_PROCESSES: Dict[str, subprocess.Popen] = {}
_lock = threading.Lock()


def register_execution(execution_id: str, process: subprocess.Popen) -> None:
    """Register a running process under the given execution_id.

    Args:
        execution_id: Unique identifier (uuid4 hex short form).
        process: The subprocess.Popen instance to track.
    """
    with _lock:
        _RUNNING_PROCESSES[execution_id] = process


def kill_execution(execution_id: str) -> bool:
    """Kill a running script execution by ID.

    Calls process.kill() on the tracked process and removes it from
    the registry.  If the process was already dead or unknown, returns
    False.

    Args:
        execution_id: The execution ID to kill.

    Returns:
        True if a process was found and killed, False otherwise.
    """
    with _lock:
        process = _RUNNING_PROCESSES.pop(execution_id, None)
    if process is None:
        return False
    try:
        process.kill()
        # Consume remaining stdout/stderr so the reader threads can exit
        process.stdout.close()
        process.stderr.close()
    except Exception:
        pass
    return True


def unregister_execution(execution_id: str) -> Optional[subprocess.Popen]:
    """Remove a completed/failed execution from the registry.

    Should be called in the finally block after script execution ends
    (success, timeout, or kill).

    Args:
        execution_id: The execution ID to remove.

    Returns:
        The Popen instance if it was registered, or None.
    """
    with _lock:
        return _RUNNING_PROCESSES.pop(execution_id, None)
