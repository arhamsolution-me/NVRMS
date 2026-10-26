"""Local runner for NVRSMS Hub Backend without Docker.

Runs with:
- SQLite database (auto-created at nvrsms.db)
- In-memory FakeRedis (auto-fallback when Redis is not running)
- Auto-seeded Super Admin account (admin@nvrsms.local / AdminPass2026!#)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure paths
root_dir = Path(__file__).parent.resolve()
hub_dir = root_dir / "hub-backend"
agent_dir = root_dir / "agent"

sys.path.insert(0, str(hub_dir))
sys.path.insert(0, str(agent_dir))

# Environment overrides for zero-Docker standalone execution
db_path = root_dir / "nvrsms.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
os.environ.setdefault("SECRET_KEY", "nvrsms_ultra_secure_jwt_secret_key_32_chars_2026!#")
os.environ.setdefault("SUPER_ADMIN_EMAIL", "admin@nvrsms.local")
os.environ.setdefault("SUPER_ADMIN_PASSWORD", "AdminPass2026!#")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")  # Triggers FakeRedis fallback
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173")

if __name__ == "__main__":
    import uvicorn

    print("==================================================")
    print("  NVRSMS Hub Backend — Standalone (No Docker)")
    print("==================================================")
    print(f" Database: SQLite ({db_path})")
    print(" Cache:    In-Memory FakeRedis")
    print(" URL:      http://127.0.0.1:8000")
    print(" Docs:     http://127.0.0.1:8000/api/docs")
    print(" Admin:    admin@nvrsms.local / AdminPass2026!#")
    print("==================================================")

    uvicorn.run("hub_backend.main:app", host="127.0.0.1", port=8000, reload=False)
