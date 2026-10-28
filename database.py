"""Database initialization and access helpers for campus_cache.db."""
import sys
from kgp_mcp.infrastructure.database import (
    init_db,
    insert_classes,
    get_classes,
    DB_PATH,
    ROOT_DIR,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

__all__ = ["init_db", "insert_classes", "get_classes", "DB_PATH", "ROOT_DIR"]

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
    print(f"SUCCESS: campus_cache.db initialized at {DB_PATH}")
