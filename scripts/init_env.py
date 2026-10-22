"""Create .env from .env.example with freshly generated secrets.

Usage: python scripts/init_env.py [--force]
"""

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    target = ROOT / ".env"
    if target.exists() and "--force" not in sys.argv:
        sys.exit(".env already exists (use --force to overwrite)")

    db_password = secrets.token_urlsafe(24)
    lines = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("JWT_SECRET="):
            line = f"JWT_SECRET={secrets.token_urlsafe(48)}"
        elif line.startswith("POSTGRES_PASSWORD="):
            line = f"POSTGRES_PASSWORD={db_password}"
        line = line.replace("<POSTGRES_PASSWORD>", db_password)
        lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Created {target} with random JWT_SECRET and POSTGRES_PASSWORD.")


if __name__ == "__main__":
    main()
