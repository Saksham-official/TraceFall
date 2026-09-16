import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.cli import main

if __name__ == "__main__":
    # Preserve the old helper name, but use the same interactive flow as production.
    # No password belongs in this repository.
    sys.argv[1:] = ["create-admin", *sys.argv[1:]]
    raise SystemExit(main())
