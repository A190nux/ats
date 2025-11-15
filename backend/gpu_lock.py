"""Simple filesystem-based GPU lock to coordinate exclusive GPU usage across processes.

Usage:
    from backend.gpu_lock import acquire_gpu, release_gpu

Processes should call `acquire_gpu()` before starting GPU-heavy work and `release_gpu()` afterwards.
This uses an atomic directory creation for the lock and is intentionally simple.
"""
import os
import time

LOCK_DIR = os.getenv("ATS_GPU_LOCK_DIR", "/tmp/ats_gpu_lock")


def acquire_gpu(blocking: bool = True, timeout: float = None, poll_interval: float = 0.5) -> bool:
    """Acquire GPU lock by creating a lock directory.

    Returns True if the lock was acquired, False otherwise.
    If blocking is True, waits until lock becomes available or timeout is reached.
    """
    start = time.time()
    while True:
        try:
            os.mkdir(LOCK_DIR)
            # write pid for debugging
            try:
                with open(os.path.join(LOCK_DIR, "pid"), "w") as f:
                    f.write(str(os.getpid()))
            except Exception:
                pass
            return True
        except FileExistsError:
            if not blocking:
                return False
            if timeout is not None and (time.time() - start) >= timeout:
                return False
            time.sleep(poll_interval)
        except Exception:
            return False


def release_gpu() -> None:
    """Release the GPU lock by removing the lock directory."""
    try:
        pid_file = os.path.join(LOCK_DIR, "pid")
        if os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except Exception:
                pass
        os.rmdir(LOCK_DIR)
    except Exception:
        # ignore errors (lock may have been removed externally)
        pass
