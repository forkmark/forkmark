#!/usr/bin/env python3
"""Start the Forkmark server."""
import os
import uvicorn
from config import config

if __name__ == "__main__":
    dev_mode = os.getenv("FM_ENV", "production").lower() in ("dev", "development")
    print(f"\n  Forkmark {config.VERSION}{'  [dev]' if dev_mode else ''}")
    print(f"  Dashboard → http://{config.HOST}:{config.PORT}\n")
    uvicorn.run(
        "backend.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=dev_mode,
    )
