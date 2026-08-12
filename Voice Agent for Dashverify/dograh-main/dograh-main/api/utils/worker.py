"""Utilities for worker process identification."""

import multiprocessing
import os

from loguru import logger


def get_worker_id() -> int:
    """Get the current worker ID from environment or process name.

    Returns:
        Worker ID (0-based index), or 0 if not in a worker process.
    """
    # Check for custom ASGI_WORKER_ID (for future compatibility)
    worker_id = os.getenv("ASGI_WORKER_ID")
    if worker_id:
        return int(worker_id)

    # Debug log the process name to understand worker identification
    process_name = multiprocessing.current_process().name

    # Try to extract worker number from process name
    # Uvicorn with --workers creates processes like "SpawnProcess-1", "SpawnProcess-2", etc.
    # TODO FIXME: If a worker process crashes and uvicorn creates a new process,
    # it assigns ID which may be beyond NUM_FASTAPI_WORKERS. Example: if we have
    # 2 fastapi workers configured, and one of them dies, we can get a process name with
    # SpawnProcess-3 which is bad
    if "SpawnProcess" in process_name:
        try:
            # Extract the number after "SpawnProcess-"
            worker_num = int(process_name.split("-")[-1])
            # Convert to 0-based index
            return worker_num - 1
        except (ValueError, IndexError):
            logger.warning(
                f"Could not extract worker ID from process name: {process_name}"
            )

    # Gunicorn creates workers with names like "Worker-1", "Worker-2", etc.
    if "Worker" in process_name:
        try:
            # Extract the number after "Worker-"
            worker_num = int(process_name.split("-")[-1])
            # Convert to 0-based index
            return worker_num - 1
        except (ValueError, IndexError):
            logger.warning(
                f"Could not extract worker ID from process name: {process_name}"
            )

    # Not in a worker process (main process or single-process mode)
    return 0


def is_worker_process() -> bool:
    """Check if we're running in a worker process (not the main process).

    Returns:
        True if in a worker process, False if in main process or single-process mode.
    """
    process_name = multiprocessing.current_process().name
    return "SpawnProcess" in process_name or "Worker" in process_name
