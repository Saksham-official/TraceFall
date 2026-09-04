"""Queue worker.

Phase 1 has no queue: this is the process placeholder that proves the container
topology works. It writes a heartbeat file that its healthcheck reads.
Phase 2 replaces the loop body with the Redis queue consumer.
"""

import sys
import time
from pathlib import Path

HEARTBEAT = Path("/tmp/tracefall-worker-heartbeat")  # noqa: S108
INTERVAL_SECONDS = 5
STALE_AFTER_SECONDS = 30


def beat() -> None:
    HEARTBEAT.write_text(str(time.time()))


def is_alive() -> bool:
    try:
        return time.time() - float(HEARTBEAT.read_text()) < STALE_AFTER_SECONDS
    except (OSError, ValueError):
        return False


def run() -> None:
    print("worker ready", flush=True)
    while True:
        beat()
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if is_alive() else 1)
    run()
