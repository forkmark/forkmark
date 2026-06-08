"""Forkmark configuration.

All settings can be controlled via environment variables. Sensible defaults
make Forkmark work out of the box with zero configuration for local use.

UI-saved preferences are written to ~/.forkmark/.env and loaded on startup.
Explicit environment variables always override .env values.
"""
import os
from pathlib import Path

# ── Load ~/.forkmark/.env (low priority — real env vars win) ────────────────
_FM_HOME = Path(os.getenv("FM_HOME", str(Path.home() / ".forkmark")))
_ENV_FILE = _FM_HOME / ".env"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — no dependencies required.

    Only sets vars that are NOT already in the environment, so explicit
    exports always win over .env values.
    """
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(_ENV_FILE)


def save_env_setting(key: str, value: str) -> None:
    """Persist a key=value pair to ~/.forkmark/.env.

    Updates existing keys in place, appends new ones.
    """
    _FM_HOME.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    found = False
    if _ENV_FILE.is_file():
        for line in _ENV_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, _ = stripped.partition("=")
                if k.strip() == key:
                    lines.append(f"{key}={value}")
                    found = True
                    continue
            lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    _ENV_FILE.write_text("\n".join(lines) + "\n")


class Config:
    APP_NAME = "Forkmark"
    VERSION  = "0.1.2"

    # ── Database & Cache ───────────────────────────────────────────────────────
    # PRODUCTION: FM_DATABASE_URL must point to PostgreSQL (via PgBouncer)
    # DEV ONLY:   Leave unset to use SQLite (single-user, no concurrency)
    DB_PATH      = Path(os.getenv("FM_DB_PATH",
                                   str(Path.home() / ".forkmark" / "forkmark.db")))
    DATABASE_URL   = os.getenv("FM_DATABASE_URL", "")  # postgresql://... for production
    REDIS_URL      = os.getenv("FM_REDIS_URL", "")     # optional — enables Redis-backed caching

    # ── Server ─────────────────────────────────────────────────────────────────
    API_KEY_PREFIX = "fm_"
    HOST           = os.getenv("FM_HOST", "127.0.0.1")
    PORT           = int(os.getenv("FM_PORT", "7700"))

    # ── Auth ───────────────────────────────────────────────────────────────────
    # UI read/write endpoints (including data exports) are OPEN when Forkmark is
    # bound to loopback — frictionless local use. When bound to any other
    # interface (e.g. 0.0.0.0 on a server) an X-API-Key is REQUIRED by default, so
    # the preference/DPO corpus isn't exposed to the network unintentionally.
    # Override explicitly either way with FM_REQUIRE_UI_AUTH=true|false.
    _BOUND_LOOPBACK = HOST in ("127.0.0.1", "localhost", "::1")
    REQUIRE_UI_AUTH = os.getenv(
        "FM_REQUIRE_UI_AUTH",
        "false" if _BOUND_LOOPBACK else "true",
    ).lower() == "true"

    # ── Divergence scorer ──────────────────────────────────────────────────────
    # Controls how branch output divergence is measured.
    #
    #   auto      — semantic if sentence-transformers installed, else lexical
    #   lexical   — TF-IDF cosine + SequenceMatcher (zero deps, ~1 ms)
    #   semantic  — sentence-transformers all-MiniLM-L6-v2 (~50 ms, 80 MB model)
    #               pip install sentence-transformers
    #   openai    — OpenAI text-embedding-3-small cosine (requires API key)
    #               set FM_OPENAI_API_KEY or OPENAI_API_KEY
    #   llm_judge — G-Eval LLM-as-judge (2–5 s, ~$0.001/comparison)
    #               set FM_OPENAI_API_KEY + optionally FM_JUDGE_MODEL
    DIVERGENCE_SCORER = os.getenv("FM_DIVERGENCE_SCORER", "auto")

    # sentence-transformers model name (for DIVERGENCE_SCORER=semantic)
    ST_MODEL       = os.getenv("FM_ST_MODEL", "all-MiniLM-L6-v2")

    # OpenAI embeddings model (for DIVERGENCE_SCORER=openai)
    EMBED_MODEL    = os.getenv("FM_EMBED_MODEL", "text-embedding-3-small")

    # LLM judge settings (for DIVERGENCE_SCORER=llm_judge)
    JUDGE_MODEL    = os.getenv("FM_JUDGE_MODEL", "gpt-4o-mini")
    JUDGE_BASE_URL = os.getenv("FM_JUDGE_BASE_URL", "https://api.openai.com/v1")

    # ── CORS ─────────────────────────────────────────────────────────────────────
    CORS_ORIGINS = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:7700", "http://127.0.0.1:7700",
    ] + [o.strip() for o in os.getenv("FM_CORS_ORIGINS", "").split(",") if o.strip()]

    # ── Background scoring ──────────────────────────────────────────────────────
    # Number of background worker threads for divergence scoring + evaluation
    BACKGROUND_WORKERS = int(os.getenv("FM_BACKGROUND_WORKERS", "4"))

    # ── Agent comparison ───────────────────────────────────────────────────────
    # Enable agent trajectory comparison feature (new in v0.1.2)
    # Global env-var kill-switch; per-org / per-workspace gating is handled
    # by core.feature_flags at runtime.
    ENABLE_AGENT_COMPARISON = os.getenv(
        "FM_ENABLE_AGENT_COMPARISON", "false"
    ).lower() in ("true", "1")

    # ── OpenTelemetry ───────────────────────────────────────────────────────────
    # Enable OpenTelemetry tracing with GenAI semantic conventions
    # Requires: pip install opentelemetry-api opentelemetry-sdk
    ENABLE_OTEL = os.getenv("FM_ENABLE_OTEL", "false").lower() == "true"


config = Config()
config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
