"""Forkmark database layer — SQLite default, PostgreSQL via DATABASE_URL,
DuckDB via FM_TRACE_BACKEND=duckdb.

PostgreSQL support requires psycopg2-binary:
    pip install psycopg2-binary

DuckDB support requires duckdb:
    pip install duckdb

Set FM_DATABASE_URL=postgresql://user:pass@host:5432/dbname to enable PostgreSQL.
Set FM_TRACE_BACKEND=duckdb to enable DuckDB columnar storage.
"""

from __future__ import annotations
import base64, hashlib, json, logging, os, re, sqlite3, threading, time, uuid

_log = logging.getLogger("forkmark.store")
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

# ── Argon2id hasher singleton ─────────────────────────────────────────────────
# Instantiated once at import time so verify_api_key and create_api_key never
# pay module-import overhead inside hot request paths.
try:
    from argon2 import PasswordHasher as _PH
    from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
    _ph = _PH()
except ImportError:
    _ph = None  # type: ignore
    VerifyMismatchError = VerificationError = InvalidHashError = Exception  # type: ignore

# ── API key verify cache ───────────────────────────────────────────────────────
# Maps raw_key → (expire_timestamp, ApiKey | None).
# Bounded LRU (max 2048 entries) so long-running servers with key rotation
# don't leak memory indefinitely.
_VERIFY_CACHE_MAX = 2048
_verify_cache: OrderedDict = OrderedDict()
_verify_lock  = threading.Lock()
_VERIFY_TTL   = 60.0  # seconds


def _cache_put(key: str, value: tuple) -> None:
    """Insert/update cache entry, evicting LRU entries over the size cap."""
    with _verify_lock:
        if key in _verify_cache:
            _verify_cache.move_to_end(key)
        _verify_cache[key] = value
        while len(_verify_cache) > _VERIFY_CACHE_MAX:
            _verify_cache.popitem(last=False)  # pop oldest

from .models import (
    Workflow, WorkflowRun, Branch, StepOutput,
    Comparison, Decision, ApiKey,
    TestSet, TestCase, EvalRun,
    RunStatus, DecisionChoice, ConfidenceLevel, EvalRunStatus, ScoringStatus,
)


# ── Sensitive settings encryption ────────────────────────────────────────────
# Encrypts values like openai_api_key at rest using Fernet if `cryptography`
# is available and FM_SECRET_KEY is set.  Falls back to plaintext with a
# one-time warning.
_SENSITIVE_KEYS = frozenset({"openai_api_key", "provider_api_key"})
_ENC_PREFIX = "enc::"  # marker for encrypted values in the DB

try:
    from cryptography.fernet import Fernet as _Fernet

    def _derive_fernet_key(secret: str) -> bytes:
        """Derive a 32-byte URL-safe-base64 key from a user-provided secret."""
        raw = hashlib.sha256(secret.encode()).digest()
        return base64.urlsafe_b64encode(raw)

    _fm_secret = os.getenv("FM_SECRET_KEY", "")
    if _fm_secret:
        _fernet = _Fernet(_derive_fernet_key(_fm_secret))
    else:
        _fernet = None
except ImportError:
    _fernet = None


def _encrypt_setting(value: str) -> str:
    """Encrypt a sensitive setting value if Fernet is available."""
    if _fernet is None:
        return value
    return _ENC_PREFIX + _fernet.encrypt(value.encode()).decode()


def _decrypt_setting(value: str) -> str:
    """Decrypt a sensitive setting value if it has the enc:: prefix."""
    if not value.startswith(_ENC_PREFIX):
        return value  # plaintext (legacy or no encryption)
    if _fernet is None:
        return value  # can't decrypt — return raw (will look garbled)
    try:
        return _fernet.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
    except Exception:
        return value  # decryption failed — return as-is


# ── SQLite adapter ────────────────────────────────────────────────────────────

class _SQLiteConn:
    """SQLite connection manager with separate read/write paths.

    Write path: single persistent connection behind a threading.Lock
    (SQLite allows only one writer at a time).

    Read path: thread-local connections so concurrent readers don't block
    each other (WAL mode supports this natively).
    """
    def __init__(self, path: str):
        self._path = path
        self._write_lock = threading.Lock()
        self._write_conn: Optional[sqlite3.Connection] = None
        self._local = threading.local()

    def _get_write_conn(self) -> sqlite3.Connection:
        if self._write_conn is None:
            self._write_conn = sqlite3.connect(self._path, check_same_thread=False)
            self._write_conn.row_factory = sqlite3.Row
            self._write_conn.execute("PRAGMA journal_mode=WAL")
            self._write_conn.execute("PRAGMA foreign_keys=ON")
        return self._write_conn

    def _get_read_conn(self) -> sqlite3.Connection:
        """Thread-local read connection — no lock needed, WAL allows concurrent readers."""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA query_only=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def connect(self):
        with self._write_lock:
            conn = self._get_write_conn()
            try:
                yield _SQLiteWrapper(conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @contextmanager
    def read_connect(self):
        """Read-only connection — no lock, concurrent readers allowed."""
        conn = self._get_read_conn()
        yield _SQLiteWrapper(conn)


class _SQLiteWrapper:
    def __init__(self, conn):
        self._c = conn

    def execute(self, sql, params=()):
        return self._c.execute(sql, params)

    def executemany(self, sql, params_seq):
        return self._c.executemany(sql, params_seq)

    def executescript(self, sql):
        self._c.executescript(sql)

    def fetchall(self, sql, params=()):
        return self._c.execute(sql, params).fetchall()

    def fetchone(self, sql, params=()):
        return self._c.execute(sql, params).fetchone()


# ── DuckDB adapter ────────────────────────────────────────────────────────────

class _DuckDBResult:
    """Wraps a DuckDB cursor to return dict-like rows (matching sqlite3.Row API)."""
    def __init__(self, cursor):
        self._cursor = cursor
        self._cols = [d[0] for d in cursor.description] if cursor.description else []

    def _to_dict(self, row):
        if row is None:
            return None
        return dict(zip(self._cols, row))

    def fetchall(self):
        if not self._cols:
            return []
        return [self._to_dict(r) for r in self._cursor.fetchall()]

    def fetchone(self):
        if not self._cols:
            return None
        return self._to_dict(self._cursor.fetchone())

    def __iter__(self):
        if not self._cols:
            return
        while True:
            row = self._cursor.fetchone()
            if row is None:
                break
            yield self._to_dict(row)

    @property
    def rowcount(self):
        return getattr(self._cursor, 'rowcount', -1)


class _DuckDBWrapper:
    """Wraps a DuckDB connection with the same interface as _SQLiteWrapper."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        return _DuckDBResult(cursor)

    def executemany(self, sql, params_seq):
        cursor = self._conn.cursor()
        cursor.executemany(sql, list(params_seq))
        return _DuckDBResult(cursor)

    def executescript(self, sql):
        # DuckDB does not support CASCADE / SET NULL / SET DEFAULT on FK constraints
        _fk_action_re = re.compile(
            r'\bON\s+(DELETE|UPDATE)\s+(CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION)',
            re.IGNORECASE,
        )
        for raw_stmt in sql.split(";"):
            stmt = raw_stmt.strip()
            if not stmt or stmt.upper().startswith("PRAGMA"):
                continue
            stmt = _fk_action_re.sub("", stmt)
            try:
                self._conn.execute(stmt)
            except Exception as e:
                msg = str(e).lower()
                if "already exists" not in msg and "duplicate" not in msg:
                    raise

    def fetchall(self, sql, params=()):
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        if not cursor.description:
            return []
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def fetchone(self, sql, params=()):
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        if not cursor.description:
            return None
        cols = [d[0] for d in cursor.description]
        row = cursor.fetchone()
        return dict(zip(cols, row)) if row else None


class _DuckDBConn:
    """DuckDB connection manager — columnar OLAP with embedded simplicity."""
    def __init__(self, path: str):
        self._path = path
        self._write_lock = threading.Lock()
        self._conn = None

    def _get_conn(self):
        if self._conn is None:
            try:
                import duckdb
            except ImportError:
                raise ImportError(
                    "duckdb is required when FM_TRACE_BACKEND=duckdb.\n"
                    "Install it: pip install duckdb"
                )
            self._conn = duckdb.connect(self._path)
        return self._conn

    @contextmanager
    def connect(self):
        with self._write_lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN TRANSACTION")
                yield _DuckDBWrapper(conn)
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    @contextmanager
    def read_connect(self):
        with self._write_lock:
            conn = self._get_conn()
            yield _DuckDBWrapper(conn)


# ── PostgreSQL adapter ────────────────────────────────────────────────────────

class _PostgreSQLConn:
    """psycopg2-backed adapter with the same interface as _SQLiteConn."""

    def __init__(self, url: str):
        self._url = url
        self._pool = None

    def _get_pool(self):
        if self._pool is None:
            try:
                import psycopg2.pool
            except ImportError:
                raise ImportError(
                    "psycopg2-binary is required for PostgreSQL support.\n"
                    "Install it: pip install psycopg2-binary"
                )
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                2,
                max(20, int(os.getenv("FM_BACKGROUND_WORKERS", "10")) + 10),
                self._url,
            )
        return self._pool

    @contextmanager
    def connect(self):
        import psycopg2.extras
        pool = self._get_pool()
        conn = pool.getconn()
        try:
            yield _PGWrapper(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool.putconn(conn)

    @contextmanager
    def read_connect(self):
        """PG uses connection pool — reads go through the same pool."""
        with self.connect() as c:
            yield c


class _PGWrapper:
    """Wraps a psycopg2 connection with the same interface as _SQLiteWrapper.

    Handles two key differences from SQLite:
      - Parameter placeholders: ? → %s
      - executescript: split on ; and execute each statement individually
    """

    def __init__(self, conn):
        self._conn = conn

    @staticmethod
    def _pg(sql: str) -> str:
        """Convert SQLite ? placeholders to psycopg2 %s.

        Simple character substitution — safe because Forkmark SQL never
        contains literal '?' characters inside string values.
        """
        return sql.replace("?", "%s")

    def _cursor(self):
        import psycopg2.extras
        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def execute(self, sql, params=()):
        cur = self._cursor()
        cur.execute(self._pg(sql), params)
        return cur

    def executemany(self, sql, params_seq):
        cur = self._cursor()
        cur.executemany(self._pg(sql), params_seq)
        return cur

    def executescript(self, sql: str):
        """Execute multiple DDL statements atomically.

        Skips PRAGMA (SQLite-only), tolerates 'already exists' errors.
        All statements run in a single transaction — either all succeed or
        all roll back (prevents half-applied migrations).
        """
        cur = self._conn.cursor()
        for raw_stmt in sql.split(";"):
            stmt = raw_stmt.strip()
            if not stmt:
                continue
            if stmt.upper().startswith("PRAGMA"):
                continue
            try:
                cur.execute(stmt)
            except Exception as e:
                msg = str(e).lower()
                if "already exists" not in msg and "duplicate" not in msg:
                    self._conn.rollback()
                    raise
                # Tolerate "already exists" — keep going in the same txn
        self._conn.commit()

    def fetchall(self, sql, params=()):
        cur = self.execute(sql, params)
        rows = cur.fetchall()
        return rows if rows else []

    def fetchone(self, sql, params=()):
        cur = self.execute(sql, params)
        return cur.fetchone()


# ── Row helper ────────────────────────────────────────────────────────────────

def _row(r) -> dict:
    """Normalise sqlite3.Row / psycopg2 RealDictRow / plain dict → dict."""
    if r is None:
        return {}
    return dict(r)


# ── Cost estimation ───────────────────────────────────────────────────────────

# Prices in USD per 1M tokens — updated periodically.
# Override or extend via FM_COST_TABLE_JSON env var (JSON dict).
_DEFAULT_PRICES: Dict[str, Dict[str, float]] = {
    # OpenAI
    "gpt-4o":            {"input": 2.50, "output": 10.00},
    "gpt-4o-mini":       {"input": 0.15, "output": 0.60},
    "gpt-4-turbo":       {"input": 10.00, "output": 30.00},
    "gpt-4":             {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo":     {"input": 0.50, "output": 1.50},
    "o1":                {"input": 15.00, "output": 60.00},
    "o1-mini":           {"input": 3.00, "output": 12.00},
    "o3-mini":           {"input": 1.10, "output": 4.40},
    # Anthropic
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku":  {"input": 0.80, "output": 4.00},
    "claude-3-opus":     {"input": 15.00, "output": 75.00},
    "claude-3-sonnet":   {"input": 3.00, "output": 15.00},
    "claude-3-haiku":    {"input": 0.25, "output": 1.25},
    # Google
    "gemini-1.5-pro":    {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash":  {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash":  {"input": 0.10, "output": 0.40},
    # Meta (self-hosted prices are $0 but we estimate typical API provider rates)
    "llama-3.1-70b":     {"input": 0.59, "output": 0.79},
    "llama-3.1-8b":      {"input": 0.10, "output": 0.10},
}

_price_cache: Optional[Dict[str, Dict[str, float]]] = None
_price_cache_env: Optional[str] = None   # tracks FM_COST_TABLE_JSON value


def update_pricing_table(new_prices: Dict[str, Dict[str, float]]):
    """Update in-memory price table from an external source (e.g. LiteLLM).
    Expects prices in USD per 1M tokens.
    """
    global _price_cache
    _DEFAULT_PRICES.update(new_prices)
    _price_cache = None  # invalidate cache


def _get_price_table() -> Dict[str, Dict[str, float]]:
    """Return the model price table, optionally extended via env var.

    Cached — only rebuilt when update_pricing_table() is called or
    FM_COST_TABLE_JSON env var changes.
    """
    global _price_cache, _price_cache_env
    current_env = os.getenv("FM_COST_TABLE_JSON")
    if _price_cache is not None and _price_cache_env == current_env:
        return _price_cache
    prices = dict(_DEFAULT_PRICES)
    if current_env:
        try:
            prices.update(json.loads(current_env))
        except (json.JSONDecodeError, TypeError):
            pass
    _price_cache = prices
    _price_cache_env = current_env
    return prices

# Compiled once at module level — avoids re.compile() on every _estimate_cost call.
_VERSION_SUFFIX_RE = re.compile(
    r'(-\d{4}(-\d{2}(-\d{2})?)?|-preview|-latest|-turbo|-instruct'
    r'|-vision|-mini|-nano|-pro|-ultra|-flash|-exp|-beta|:\d+)$'
)


def _estimate_cost(model_id: str, tokens_input: int, tokens_output: int) -> Optional[float]:
    """Estimate USD cost for a step from token counts and model pricing.

    Returns None if the model is not in the price table.
    Uses prefix matching so 'gpt-4o-2024-08-06' matches 'gpt-4o'.
    """
    prices = _get_price_table()

    # Try exact match first, then prefix match (longest prefix wins)
    price = prices.get(model_id)
    if not price:
        # Prefix match — only accept known version/date-style suffixes to avoid
        # false matches on fine-tuned IDs (e.g. "gpt-4o-mini-ft-acme" must NOT
        # match "gpt-4o-mini").  Accepted suffixes: date stamps, -preview,
        # -latest, -turbo, -instruct, -vision, -mini, -nano, -pro, -ultra,
        # -flash, -exp, -beta, and snapshot tags like ":20240801".
        candidates = [
            (k, v) for k, v in prices.items()
            if model_id.startswith(k) and _VERSION_SUFFIX_RE.match(model_id[len(k):])
        ]
        if candidates:
            # Pick longest matching prefix for specificity
            candidates.sort(key=lambda x: len(x[0]), reverse=True)
            price = candidates[0][1]

    if not price:
        return None

    cost = (tokens_input * price["input"] + tokens_output * price["output"]) / 1_000_000
    return round(cost, 8)  # sub-cent precision


# ── Database ──────────────────────────────────────────────────────────────────


def _add_column(c, table: str, col: str, typedef: str):
    """Helper: add a column, silently ignoring 'already exists' errors.

    DuckDB does not support constraints (NOT NULL) on ALTER TABLE ADD COLUMN,
    so we strip NOT NULL when the wrapper is DuckDB-based.
    """
    td = typedef
    if isinstance(c, _DuckDBWrapper):
        td = re.sub(r'\bNOT\s+NULL\b', '', td, flags=re.IGNORECASE).strip()
    try:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {td}")
    except Exception as e:
        msg = str(e).lower()
        if "duplicate column" not in msg and "already exists" not in msg:
            raise


def _migration_v1(c):
    """v1: Add eval_run support columns."""
    _add_column(c, "workflows",     "eval_run_count",        "INTEGER DEFAULT 0")
    _add_column(c, "workflow_runs", "eval_run_id",            "TEXT")
    _add_column(c, "workflow_runs", "test_case_label",        "TEXT DEFAULT ''")
    _add_column(c, "comparisons",   "eval_run_id",            "TEXT")
    _add_column(c, "comparisons",   "test_case_label",        "TEXT DEFAULT ''")
    _add_column(c, "comparisons",   "divergence_score",       "REAL")
    _add_column(c, "comparisons",   "step_divergence_scores", "TEXT DEFAULT '{}'")
    _add_column(c, "decisions",     "eval_run_id",            "TEXT")
    _add_column(c, "decisions",     "updated_at",             "TEXT")


def _migration_v2(c):
    """v2: Add async scoring, eval results, test set versioning, OTel tracing."""
    _add_column(c, "comparisons",   "eval_results",    "TEXT DEFAULT '{}'")
    _add_column(c, "comparisons",   "scoring_status",  "TEXT DEFAULT 'completed'")
    _add_column(c, "test_sets",     "version",         "INTEGER DEFAULT 1")
    _add_column(c, "test_sets",     "is_frozen",       "INTEGER DEFAULT 0")
    _add_column(c, "step_outputs",  "trace_id",        "TEXT")
    _add_column(c, "step_outputs",  "span_id",         "TEXT")


def _migration_v3(c):
    """v3: Add expected_output to test_cases and cost_usd to step_outputs."""
    _add_column(c, "test_cases",    "expected_output",  "TEXT")
    _add_column(c, "step_outputs",  "cost_usd",         "REAL")


def _migration_v4(c):
    """v4 — Flywheel 1: enrich test_cases with domain/industry/use-case metadata.

    New columns on test_cases:
      domain         – high-level domain (e.g. 'customer_support', 'legal', 'healthcare')
      industry       – vertical (e.g. 'ecommerce', 'finserv', 'healthcare')
      use_case_type  – 'safety' | 'edge_case' | 'regression' | 'happy_path' | 'adversarial'
      failure_mode   – what failure the test is designed to catch (free text)
      test_goal      – what quality signal this case measures (free text)

    Also creates the test_case_performance table for cases where
    the DDL ran before this migration was added (existing DBs).
    """
    _add_column(c, "test_cases", "domain",        "TEXT NOT NULL DEFAULT ''")
    _add_column(c, "test_cases", "industry",      "TEXT NOT NULL DEFAULT ''")
    _add_column(c, "test_cases", "use_case_type", "TEXT NOT NULL DEFAULT ''")
    _add_column(c, "test_cases", "failure_mode",  "TEXT NOT NULL DEFAULT ''")
    _add_column(c, "test_cases", "test_goal",     "TEXT NOT NULL DEFAULT ''")
    # Create flywheel tables if not yet present (idempotent via IF NOT EXISTS)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS test_case_performance (
            id               TEXT PRIMARY KEY,
            test_case_label  TEXT NOT NULL,
            workflow_id      TEXT NOT NULL,
            eval_run_id      TEXT NOT NULL,
            comparison_id    TEXT,
            divergence_score REAL,
            decision_choice  TEXT,
            reviewer_confidence TEXT,
            recorded_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tc_perf_label
            ON test_case_performance(test_case_label, workflow_id);
        CREATE INDEX IF NOT EXISTS idx_tc_perf_eval_run
            ON test_case_performance(eval_run_id);
    """)


def _migration_v5(c):
    """v5 — Flywheel 2: enrich decisions with provenance + category; add
    reviewer_profiles and data_consent tables.

    New columns on decisions:
      provenance_hash – SHA-256(workflow_id:label:input_snippet) for
                        cross-customer correlation without exposing raw text
      data_category   – auto-classified category tag (safety, legal, billing, …)
    """
    _add_column(c, "decisions", "provenance_hash", "TEXT NOT NULL DEFAULT ''")
    _add_column(c, "decisions", "data_category",   "TEXT NOT NULL DEFAULT ''")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS reviewer_profiles (
            reviewer_id      TEXT PRIMARY KEY,
            display_name     TEXT NOT NULL DEFAULT '',
            role             TEXT NOT NULL DEFAULT 'reviewer',
            expertise_level  TEXT NOT NULL DEFAULT 'intermediate',
            domain_expertise TEXT NOT NULL DEFAULT '[]',
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS data_consent (
            id           TEXT PRIMARY KEY,
            scope        TEXT NOT NULL DEFAULT 'global',
            workflow_id  TEXT,
            consent_type TEXT NOT NULL,
            granted_by   TEXT NOT NULL,
            granted_at   TEXT NOT NULL,
            expires_at   TEXT,
            is_active    INTEGER NOT NULL DEFAULT 1,
            notes        TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_consent_scope
            ON data_consent(scope, workflow_id, consent_type, is_active);
    """)


def _migration_v6(c):
    """v6 — Collaboration: comments, review assignments, review status tracking.

    New tables:
      comments           – threaded comments on comparisons/decisions
      review_assignments – assign comparisons to reviewers with status tracking
    New columns:
      comparisons.review_status   – pending/assigned/reviewed/skipped
      comparisons.assigned_to     – reviewer ID for queue management
    """
    _add_column(c, "comparisons", "review_status", "TEXT NOT NULL DEFAULT 'pending'")
    _add_column(c, "comparisons", "assigned_to", "TEXT NOT NULL DEFAULT ''")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS comments (
            id              TEXT PRIMARY KEY,
            comparison_id   TEXT NOT NULL,
            author_id       TEXT NOT NULL,
            author_name     TEXT NOT NULL DEFAULT '',
            body            TEXT NOT NULL,
            parent_id       TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            is_resolved     INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_comments_comparison
            ON comments(comparison_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_comments_parent
            ON comments(parent_id);

        CREATE TABLE IF NOT EXISTS review_assignments (
            id              TEXT PRIMARY KEY,
            eval_run_id     TEXT NOT NULL,
            comparison_id   TEXT NOT NULL,
            reviewer_id     TEXT NOT NULL,
            assigned_by     TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'pending',
            assigned_at     TEXT NOT NULL,
            completed_at    TEXT,
            notes           TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_assignments_reviewer
            ON review_assignments(reviewer_id, status);
        CREATE INDEX IF NOT EXISTS idx_assignments_eval_run
            ON review_assignments(eval_run_id, status);
        CREATE INDEX IF NOT EXISTS idx_assignments_comparison
            ON review_assignments(comparison_id);
    """)


# ── Migration strategy ─────────────────────────────────────────────────────
#
# Forkmark uses TWO complementary migration systems:
#
#   1. store.py inline DDL (below) — workspace-level tables (workflows, runs,
#      branches, step_outputs, comparisons, decisions, test_sets, eval_runs).
#      Runs on BOTH SQLite (dev) and PostgreSQL (prod).  Applied automatically
#      on Database.__init__ via _migrate().
#
#   2. Alembic migrations (migrations/versions/) — multi-tenant control plane
#      tables (organizations, workspaces, users, workspace_memberships,
#      api_keys_v2, audit_log).  PostgreSQL ONLY.  Run via `alembic upgrade head`.
#
# These are NOT duplicates: (1) handles data that lives *inside* each workspace
# schema, while (2) handles data in the shared public schema.
#
# Future workspace-level schema changes should be added as new entries in
# _MIGRATIONS below.  Control-plane changes go in migrations/versions/.
# ───────────────────────────────────────────────────────────────────────────

def _migration_v7(c):
    """v7 — Provider registry: dedicated table for LLM providers with encrypted keys.

    Also adds provider_id columns to branches and eval_runs so each branch
    can independently track which provider was used.
    """
    c.executescript("""
        CREATE TABLE IF NOT EXISTS llm_providers (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            provider_type   TEXT NOT NULL DEFAULT 'openai',
            base_url        TEXT NOT NULL DEFAULT '',
            api_key_encrypted TEXT NOT NULL DEFAULT '',
            is_default      INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_providers_default
            ON llm_providers(is_default);
    """)
    _add_column(c, "branches", "provider_id", "TEXT")


# Ordered list of (version, description, function)
def _migration_v8(c):
    """v8 — Agent comparison: trace_events tree + trajectory_outcomes.

    No inbound FKs from core tables — fully additive, safe to roll back
    by dropping these two tables.
    """
    c.executescript("""
        CREATE TABLE IF NOT EXISTS trace_events (
            id TEXT PRIMARY KEY,
            branch_id TEXT NOT NULL REFERENCES branches(id),
            run_id TEXT NOT NULL REFERENCES workflow_runs(id),
            parent_event_id TEXT REFERENCES trace_events(id),
            event_type TEXT NOT NULL DEFAULT 'tool_call',
            event_index INTEGER NOT NULL DEFAULT 0,
            name TEXT NOT NULL DEFAULT '',
            input_data TEXT DEFAULT '{}',
            output_data TEXT DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'completed',
            latency_ms INTEGER DEFAULT 0,
            tokens_input INTEGER DEFAULT 0,
            tokens_output INTEGER DEFAULT 0,
            cost_usd REAL,
            metadata TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_trace_events_branch
            ON trace_events(branch_id);
        CREATE INDEX IF NOT EXISTS idx_trace_events_run
            ON trace_events(run_id);
        CREATE INDEX IF NOT EXISTS idx_trace_events_parent
            ON trace_events(parent_event_id);

        CREATE TABLE IF NOT EXISTS trajectory_outcomes (
            id TEXT PRIMARY KEY,
            comparison_id TEXT NOT NULL REFERENCES comparisons(id),
            run_id TEXT NOT NULL REFERENCES workflow_runs(id),
            workflow_id TEXT NOT NULL,
            tool_sequence_score REAL DEFAULT 0.0,
            outcome_equivalence_score REAL DEFAULT 0.0,
            efficiency_score REAL DEFAULT 0.0,
            trajectory_score REAL DEFAULT 0.0,
            tool_sequence_detail TEXT DEFAULT '{}',
            outcome_detail TEXT DEFAULT '{}',
            efficiency_detail TEXT DEFAULT '{}',
            branch_a_tool_count INTEGER DEFAULT 0,
            branch_b_tool_count INTEGER DEFAULT 0,
            branch_a_depth INTEGER DEFAULT 0,
            branch_b_depth INTEGER DEFAULT 0,
            branch_a_total_latency_ms INTEGER DEFAULT 0,
            branch_b_total_latency_ms INTEGER DEFAULT 0,
            branch_a_total_cost_usd REAL DEFAULT 0.0,
            branch_b_total_cost_usd REAL DEFAULT 0.0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_trajectory_outcomes_comparison
            ON trajectory_outcomes(comparison_id);
        CREATE INDEX IF NOT EXISTS idx_trajectory_outcomes_workflow
            ON trajectory_outcomes(workflow_id);
    """)
    # Add run_type column to workflow_runs for distinguishing agent runs
    _add_column(c, "workflow_runs", "run_type", "TEXT DEFAULT 'standard'")


_MIGRATIONS = [
    (1, "eval_run support columns",                          _migration_v1),
    (2, "async scoring, eval results, OTel, versioning",     _migration_v2),
    (3, "expected_output on test_cases, cost_usd on step_outputs", _migration_v3),
    (4, "flywheel-1: test_case domain metadata + performance corpus", _migration_v4),
    (5, "flywheel-2: decision provenance + reviewer_profiles + data_consent", _migration_v5),
    (6, "collaboration: comments + review assignments + review status", _migration_v6),
    (7, "provider registry: llm_providers table + branch provider_id", _migration_v7),
    (8, "agent comparison: trace_events + trajectory_outcomes", _migration_v8),
]

class Database:
    def __init__(self, db_path: str, database_url: str = "", trace_backend: str = ""):
        if database_url:
            self._adapter = _PostgreSQLConn(database_url)
        elif trace_backend.lower() == "duckdb":
            self._adapter = _DuckDBConn(str(db_path))
        else:
            self._adapter = _SQLiteConn(str(db_path))
        self._init()
        self._migrate()

    @contextmanager
    def _conn(self):
        with self._adapter.connect() as c:
            yield c

    @contextmanager
    def _read_conn(self):
        """Read-only connection — allows concurrent readers on SQLite WAL."""
        with self._adapter.read_connect() as c:
            yield c

    def _init(self):
        with self._conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                run_count INTEGER DEFAULT 0,
                decision_count INTEGER DEFAULT 0,
                eval_run_count INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS test_sets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                workflow_id TEXT,
                created_at TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                is_frozen INTEGER DEFAULT 0,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS test_cases (
                id TEXT PRIMARY KEY,
                test_set_id TEXT NOT NULL,
                label TEXT NOT NULL,
                input_data TEXT DEFAULT '{}',
                expected_output TEXT,
                tags TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY (test_set_id) REFERENCES test_sets(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS eval_runs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                test_set_id TEXT,
                branch_a_config TEXT DEFAULT '{}',
                branch_b_config TEXT DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                total_cases INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS workflow_runs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                created_at TEXT NOT NULL,
                completed_at TEXT,
                input_data TEXT DEFAULT '{}',
                metadata TEXT DEFAULT '{}',
                sdk_key_prefix TEXT DEFAULT '',
                eval_run_id TEXT,
                test_case_label TEXT DEFAULT '',
                FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
                FOREIGN KEY (eval_run_id) REFERENCES eval_runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS branches (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                name TEXT NOT NULL,
                model_id TEXT NOT NULL,
                temperature REAL DEFAULT 0.7,
                system_prompt TEXT,
                extra_config TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                is_baseline INTEGER DEFAULT 0,
                FOREIGN KEY (run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS step_outputs (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                branch_id TEXT NOT NULL,
                step_name TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                input_messages TEXT DEFAULT '[]',
                output_text TEXT NOT NULL,
                model_id TEXT NOT NULL,
                temperature REAL DEFAULT 0.7,
                tokens_input INTEGER DEFAULT 0,
                tokens_output INTEGER DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                error TEXT,
                trace_id TEXT,
                span_id TEXT,
                cost_usd REAL,
                FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS comparisons (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                branch_a_id TEXT NOT NULL,
                branch_b_id TEXT NOT NULL,
                step_names TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                decided INTEGER DEFAULT 0,
                decision_id TEXT,
                eval_run_id TEXT,
                test_case_label TEXT DEFAULT '',
                divergence_score REAL,
                step_divergence_scores TEXT DEFAULT '{}',
                eval_results TEXT DEFAULT '{}',
                scoring_status TEXT DEFAULT 'completed',
                FOREIGN KEY (run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE,
                FOREIGN KEY (eval_run_id) REFERENCES eval_runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                comparison_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                reviewer_id TEXT NOT NULL,
                choice TEXT NOT NULL,
                confidence TEXT NOT NULL,
                rationale_for_choice TEXT NOT NULL,
                rationale_for_rejection TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT,
                branch_winner_id TEXT,
                branch_loser_id TEXT,
                divergence_score REAL DEFAULT 0.0,
                divergence_summary TEXT,
                eval_run_id TEXT,
                FOREIGN KEY (comparison_id) REFERENCES comparisons(id) ON DELETE CASCADE,
                FOREIGN KEY (eval_run_id) REFERENCES eval_runs(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                key_prefix TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                is_active INTEGER DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_runs_workflow ON workflow_runs(workflow_id);
            CREATE INDEX IF NOT EXISTS idx_runs_eval_run ON workflow_runs(eval_run_id);
            CREATE INDEX IF NOT EXISTS idx_branches_run ON branches(run_id);
            CREATE INDEX IF NOT EXISTS idx_steps_branch ON step_outputs(branch_id);
            CREATE INDEX IF NOT EXISTS idx_steps_run ON step_outputs(run_id);
            CREATE INDEX IF NOT EXISTS idx_comparisons_run ON comparisons(run_id);
            CREATE INDEX IF NOT EXISTS idx_comparisons_eval_run ON comparisons(eval_run_id);
            CREATE INDEX IF NOT EXISTS idx_decisions_workflow ON decisions(workflow_id);
            CREATE INDEX IF NOT EXISTS idx_decisions_eval_run ON decisions(eval_run_id);
            CREATE INDEX IF NOT EXISTS idx_decisions_comparison ON decisions(comparison_id);
            CREATE INDEX IF NOT EXISTS idx_test_cases_set ON test_cases(test_set_id);
            CREATE INDEX IF NOT EXISTS idx_eval_runs_workflow ON eval_runs(workflow_id);
            CREATE INDEX IF NOT EXISTS idx_comparisons_workflow ON comparisons(workflow_id);

            -- Composite index for eval run stats query (eval_run_id + divergence ordering)
            CREATE INDEX IF NOT EXISTS idx_comparisons_eval_div
                ON comparisons(eval_run_id, divergence_score DESC);

            -- Index for list_decisions ORDER BY created_at DESC
            CREATE INDEX IF NOT EXISTS idx_decisions_created
                ON decisions(created_at DESC);

            -- Index for API key lookup by prefix (needed for argon2 verification)
            CREATE INDEX IF NOT EXISTS idx_api_keys_prefix
                ON api_keys(key_prefix);

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            -- ── Provider registry ────────────────────────────────────────
            -- Stores LLM provider configurations with encrypted API keys.
            -- Each branch can optionally reference a provider_id for
            -- per-branch credential resolution.
            CREATE TABLE IF NOT EXISTS llm_providers (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                provider_type   TEXT NOT NULL DEFAULT 'openai',
                base_url        TEXT NOT NULL DEFAULT '',
                api_key_encrypted TEXT NOT NULL DEFAULT '',
                is_default      INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_providers_default
                ON llm_providers(is_default);

            -- ── Flywheel 1: test-case performance corpus ──────────────────────
            -- One row per (test_case_label, eval_run_id).
            -- Populated automatically when comparisons are created and decisions recorded.
            -- Powers automated test-case generation: tracks which inputs surface
            -- divergence, which models win, and reviewer confidence over time.
            CREATE TABLE IF NOT EXISTS test_case_performance (
                id               TEXT PRIMARY KEY,
                test_case_label  TEXT NOT NULL,
                workflow_id      TEXT NOT NULL,
                eval_run_id      TEXT NOT NULL,
                comparison_id    TEXT,
                divergence_score REAL,
                decision_choice  TEXT,           -- a_wins | b_wins | tie | skip
                reviewer_confidence TEXT,        -- low | medium | high
                recorded_at      TEXT NOT NULL,
                FOREIGN KEY (workflow_id)   REFERENCES workflows(id) ON DELETE CASCADE,
                FOREIGN KEY (eval_run_id)   REFERENCES eval_runs(id) ON DELETE CASCADE
            );

            -- ── Flywheel 2a: reviewer identity & expertise ────────────────────
            -- Enriches preference exports with reviewer quality metadata.
            -- AI companies pay more for data with auditable reviewer provenance.
            CREATE TABLE IF NOT EXISTS reviewer_profiles (
                reviewer_id      TEXT PRIMARY KEY,
                display_name     TEXT NOT NULL DEFAULT '',
                role             TEXT NOT NULL DEFAULT 'reviewer',
                expertise_level  TEXT NOT NULL DEFAULT 'intermediate',
                domain_expertise TEXT NOT NULL DEFAULT '[]',  -- JSON array of domain strings
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL
            );

            -- ── Flywheel 2b: data-sharing consent ────────────────────────────
            -- Each customer must explicitly opt in before their preference data
            -- is included in anonymized B2B exports.
            CREATE TABLE IF NOT EXISTS data_consent (
                id           TEXT PRIMARY KEY,
                scope        TEXT NOT NULL DEFAULT 'global', -- global | workflow
                workflow_id  TEXT,                           -- NULL when scope='global'
                consent_type TEXT NOT NULL,                  -- training_data | anonymized_export | aggregated_stats
                granted_by   TEXT NOT NULL,
                granted_at   TEXT NOT NULL,
                expires_at   TEXT,                          -- NULL = no expiry
                is_active    INTEGER NOT NULL DEFAULT 1,
                notes        TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_tc_perf_label
                ON test_case_performance(test_case_label, workflow_id);
            CREATE INDEX IF NOT EXISTS idx_tc_perf_eval_run
                ON test_case_performance(eval_run_id);
            CREATE INDEX IF NOT EXISTS idx_consent_scope
                ON data_consent(scope, workflow_id, consent_type, is_active);
            """)

    def _migrate(self):
        """Run versioned schema migrations.

        Uses a `schema_version` table to track which migrations have been applied.
        Each migration function is numbered and runs exactly once in order.
        New migrations should be appended to the _MIGRATIONS list.
        """
        # Ensure schema_version table exists
        with self._conn() as c:
            try:
                c.execute("""CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )""")
            except Exception:
                pass  # Table might already exist in some form

        # Get current version
        with self._conn() as c:
            row = c.fetchone("SELECT COALESCE(MAX(version), 0) AS v FROM schema_version")
            current_version = _row(row).get("v", 0)

        # Run pending migrations
        for version, description, fn in _MIGRATIONS:
            if version <= current_version:
                continue
            try:
                with self._conn() as c:
                    fn(c)
                    c.execute(
                        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                        (version, datetime.now(timezone.utc).isoformat()),
                    )
                import logging
                logging.getLogger("forkmark.migrations").info(
                    f"Applied migration v{version}: {description}"
                )
            except Exception as e:
                msg = str(e).lower()
                # Tolerate "already exists" / "duplicate column" from re-runs
                if "already exists" in msg or "duplicate column" in msg:
                    # Record it as applied so we don't retry
                    with self._conn() as c:
                        try:
                            c.execute(
                                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                                (version, datetime.now(timezone.utc).isoformat()),
                            )
                        except Exception:
                            pass
                else:
                    raise




    # ── Stats (SQL-based, no Python counting) ─────────────────────────────────

    def get_stats(self) -> dict:
        """Dashboard stats computed entirely in SQL — single query for all counts."""
        with self._read_conn() as c:
            # Combine 6 COUNT queries into one cross-join (single table scan each)
            stats_row = _row(c.fetchone("""
                SELECT
                    (SELECT COUNT(*) FROM workflows)      AS wf_count,
                    (SELECT COUNT(*) FROM workflow_runs)   AS run_count,
                    (SELECT COUNT(*) FROM decisions)       AS dec_count,
                    (SELECT COUNT(*) FROM eval_runs)       AS er_count,
                    (SELECT COUNT(*) FROM comparisons WHERE decided=0) AS pending,
                    (SELECT COUNT(*) FROM eval_runs
                     WHERE status IN ('pending','running')) AS active_er
            """))
            wf_count  = stats_row["wf_count"]
            run_count = stats_row["run_count"]
            dec_count = stats_row["dec_count"]
            er_count  = stats_row["er_count"]
            pending   = stats_row["pending"]
            active_er = stats_row["active_er"]

            choice_rows = c.fetchall(
                "SELECT choice, COUNT(*) AS n FROM decisions GROUP BY choice")
            conf_rows = c.fetchall(
                "SELECT confidence, COUNT(*) AS n FROM decisions GROUP BY confidence")

        choice_breakdown = {"A": 0, "B": 0, "neither": 0, "both": 0}
        for r in choice_rows:
            r = _row(r)
            choice_breakdown[r["choice"]] = r["n"]

        conf_breakdown = {"high": 0, "medium": 0, "low": 0}
        for r in conf_rows:
            r = _row(r)
            conf_breakdown[r["confidence"]] = r["n"]

        return {
            "total_workflows":      wf_count,
            "total_runs":           run_count,
            "total_decisions":      dec_count,
            "total_eval_runs":      er_count,
            "pending_review":       pending,
            "active_eval_runs":     active_er,
            "choice_breakdown":     choice_breakdown,
            "confidence_breakdown": conf_breakdown,
        }

    # ── Cost Aggregation ──────────────────────────────────────────────────────

    def get_cost_breakdown(self, run_id: str = None,
                           comparison_id: str = None,
                           eval_run_id: str = None) -> dict:
        """Compute per-branch and total cost breakdown from step_outputs.

        Returns:
            {
                "total_cost_usd": float,
                "total_tokens_input": int,
                "total_tokens_output": int,
                "branches": [
                    {"branch_id": str, "branch_name": str, "model_id": str,
                     "cost_usd": float, "tokens_input": int, "tokens_output": int,
                     "step_count": int},
                    ...
                ]
            }
        """
        with self._conn() as c:
            if comparison_id:
                # Get branch IDs from comparison
                comp = c.fetchone(
                    "SELECT branch_a_id, branch_b_id FROM comparisons WHERE id=?",
                    (comparison_id,),
                )
                if not comp:
                    return {"total_cost_usd": 0, "total_tokens_input": 0,
                            "total_tokens_output": 0, "branches": []}
                comp = _row(comp)
                branch_ids = (comp["branch_a_id"], comp["branch_b_id"])
                rows = c.fetchall("""
                    SELECT s.branch_id,
                           b.name AS branch_name,
                           s.model_id,
                           COALESCE(SUM(s.cost_usd), 0) AS cost_usd,
                           COALESCE(SUM(s.tokens_input), 0) AS tokens_input,
                           COALESCE(SUM(s.tokens_output), 0) AS tokens_output,
                           COUNT(*) AS step_count
                    FROM step_outputs s
                    JOIN branches b ON b.id = s.branch_id
                    WHERE s.branch_id IN (?, ?)
                    GROUP BY s.branch_id, s.model_id
                    ORDER BY cost_usd DESC
                """, branch_ids)
            elif eval_run_id:
                rows = c.fetchall("""
                    SELECT s.branch_id,
                           b.name AS branch_name,
                           s.model_id,
                           COALESCE(SUM(s.cost_usd), 0) AS cost_usd,
                           COALESCE(SUM(s.tokens_input), 0) AS tokens_input,
                           COALESCE(SUM(s.tokens_output), 0) AS tokens_output,
                           COUNT(*) AS step_count
                    FROM step_outputs s
                    JOIN branches b ON b.id = s.branch_id
                    JOIN workflow_runs wr ON wr.id = s.run_id
                    WHERE wr.eval_run_id = ?
                    GROUP BY s.branch_id, s.model_id
                    ORDER BY cost_usd DESC
                """, (eval_run_id,))
            elif run_id:
                rows = c.fetchall("""
                    SELECT s.branch_id,
                           b.name AS branch_name,
                           s.model_id,
                           COALESCE(SUM(s.cost_usd), 0) AS cost_usd,
                           COALESCE(SUM(s.tokens_input), 0) AS tokens_input,
                           COALESCE(SUM(s.tokens_output), 0) AS tokens_output,
                           COUNT(*) AS step_count
                    FROM step_outputs s
                    JOIN branches b ON b.id = s.branch_id
                    WHERE s.run_id = ?
                    GROUP BY s.branch_id, s.model_id
                    ORDER BY cost_usd DESC
                """, (run_id,))
            else:
                return {"total_cost_usd": 0, "total_tokens_input": 0,
                        "total_tokens_output": 0, "branches": []}

        branches = []
        total_cost = 0.0
        total_in = 0
        total_out = 0
        for r in rows:
            r = _row(r)
            branches.append({
                "branch_id":     r["branch_id"],
                "branch_name":   r["branch_name"],
                "model_id":      r["model_id"],
                "cost_usd":      float(r["cost_usd"]),
                "tokens_input":  int(r["tokens_input"]),
                "tokens_output": int(r["tokens_output"]),
                "step_count":    int(r["step_count"]),
            })
            total_cost += float(r["cost_usd"])
            total_in   += int(r["tokens_input"])
            total_out  += int(r["tokens_output"])

        return {
            "total_cost_usd":      round(total_cost, 6),
            "total_tokens_input":  total_in,
            "total_tokens_output": total_out,
            "branches":            branches,
        }

    # ── TestSets ──────────────────────────────────────────────────────────────

    def create_test_set(self, name: str, description: str = "",
                        workflow_id: str = None) -> TestSet:
        now = datetime.now(timezone.utc)
        ts = TestSet(
            id=str(uuid.uuid4()), name=name, description=description,
            workflow_id=workflow_id, created_at=now,
        )
        with self._conn() as c:
            c.execute(
                "INSERT INTO test_sets (id,name,description,workflow_id,created_at) VALUES (?,?,?,?,?)",
                (ts.id, ts.name, ts.description, ts.workflow_id, ts.created_at.isoformat()),
            )
        return ts

    def get_test_set(self, ts_id: str) -> Optional[TestSet]:
        with self._conn() as c:
            r = c.fetchone("""
                SELECT ts.*, COUNT(tc.id) AS case_count
                FROM test_sets ts
                LEFT JOIN test_cases tc ON tc.test_set_id = ts.id
                WHERE ts.id = ?
                GROUP BY ts.id
            """, (ts_id,))
        return TestSet.from_row(_row(r)) if r else None

    def list_test_sets(self, workflow_id: str = None) -> List[TestSet]:
        """Returns test sets with case_count populated via a single JOIN query."""
        with self._conn() as c:
            if workflow_id:
                rows = c.fetchall("""
                    SELECT ts.*, COUNT(tc.id) AS case_count
                    FROM test_sets ts
                    LEFT JOIN test_cases tc ON tc.test_set_id = ts.id
                    WHERE ts.workflow_id = ?
                    GROUP BY ts.id
                    ORDER BY ts.created_at DESC
                """, (workflow_id,))
            else:
                rows = c.fetchall("""
                    SELECT ts.*, COUNT(tc.id) AS case_count
                    FROM test_sets ts
                    LEFT JOIN test_cases tc ON tc.test_set_id = ts.id
                    GROUP BY ts.id
                    ORDER BY ts.created_at DESC
                """)
        return [TestSet.from_row(_row(r)) for r in rows]

    def delete_test_set(self, ts_id: str):
        with self._conn() as c:
            c.execute("DELETE FROM test_sets WHERE id=?", (ts_id,))

    # ── TestCases ─────────────────────────────────────────────────────────────

    def add_test_case(self, test_set_id: str, label: str,
                      input_data: dict = None, tags: list = None,
                      expected_output: str = None) -> TestCase:
        # Block mutations on frozen test sets
        ts = self.get_test_set(test_set_id)
        if ts and ts.is_frozen:
            raise ValueError(
                f"Test set '{ts.name}' is frozen (linked to an eval run). "
                f"Create a new version to add cases."
            )
        now = datetime.now(timezone.utc)
        tc = TestCase(
            id=str(uuid.uuid4()), test_set_id=test_set_id, label=label,
            input_data=input_data or {}, tags=tags or [], created_at=now,
            expected_output=expected_output,
        )
        with self._conn() as c:
            c.execute(
                "INSERT INTO test_cases (id,test_set_id,label,input_data,expected_output,tags,created_at) VALUES (?,?,?,?,?,?,?)",
                (tc.id, tc.test_set_id, tc.label,
                 json.dumps(tc.input_data), tc.expected_output, json.dumps(tc.tags), tc.created_at.isoformat()),
            )
        return tc

    def list_test_cases(self, test_set_id: str) -> List[TestCase]:
        with self._conn() as c:
            rows = c.fetchall(
                "SELECT * FROM test_cases WHERE test_set_id=? ORDER BY created_at", (test_set_id,))
        return [TestCase.from_row(_row(r)) for r in rows]

    def delete_test_case(self, tc_id: str, test_set_id: str = None):
        """Delete a test case.

        If test_set_id is provided, the delete is scoped to that test set —
        the row is only removed if it belongs to that set (prevents IDOR).
        Raises ValueError if the test set is frozen.
        """
        if test_set_id:
            ts = self.get_test_set(test_set_id)
            if ts and ts.is_frozen:
                raise ValueError(
                    f"Test set '{ts.name}' is frozen (linked to an eval run). "
                    f"Create a new version to modify cases."
                )
        with self._conn() as c:
            if test_set_id:
                c.execute("DELETE FROM test_cases WHERE id=? AND test_set_id=?",
                          (tc_id, test_set_id))
            else:
                c.execute("DELETE FROM test_cases WHERE id=?", (tc_id,))

    def freeze_test_set(self, ts_id: str) -> None:
        """Mark a test set as frozen — prevents future mutations."""
        with self._conn() as c:
            c.execute("UPDATE test_sets SET is_frozen=1 WHERE id=?", (ts_id,))

    def create_test_set_version(self, ts_id: str) -> TestSet:
        """Create a new mutable copy of a frozen test set with incremented version.

        Copies all test cases from the original set into the new one.
        """
        original = self.get_test_set(ts_id)
        if not original:
            raise ValueError(f"Test set {ts_id} not found")

        now = datetime.now(timezone.utc)
        new_ts = TestSet(
            id=str(uuid.uuid4()), name=original.name,
            description=original.description, workflow_id=original.workflow_id,
            created_at=now, version=original.version + 1, is_frozen=False,
        )
        with self._conn() as c:
            c.execute(
                "INSERT INTO test_sets (id,name,description,workflow_id,created_at,version,is_frozen) "
                "VALUES (?,?,?,?,?,?,?)",
                (new_ts.id, new_ts.name, new_ts.description, new_ts.workflow_id,
                 new_ts.created_at.isoformat(), new_ts.version, 0),
            )
            # Copy test cases (including expected_output)
            cases = self.list_test_cases(ts_id)
            for tc in cases:
                c.execute(
                    "INSERT INTO test_cases (id,test_set_id,label,input_data,expected_output,tags,created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), new_ts.id, tc.label,
                     json.dumps(tc.input_data), tc.expected_output, json.dumps(tc.tags),
                     now.isoformat()),
                )
        new_ts.case_count = len(cases)
        return new_ts

    def bulk_add_test_cases(self, test_set_id: str,
                            cases: List[Dict[str, Any]]) -> List[TestCase]:
        """Insert multiple test cases at once (single transaction)."""
        result = []
        now = datetime.now(timezone.utc)
        rows_to_insert = []
        for item in cases:
            tc = TestCase(
                id=str(uuid.uuid4()), test_set_id=test_set_id,
                label=item.get("label", f"case-{len(result)+1}"),
                input_data=item.get("input_data", {k: v for k, v in item.items()
                                                   if k not in ("label", "tags", "input_data", "expected_output")}),
                tags=item.get("tags", []), created_at=now,
                expected_output=item.get("expected_output"),
            )
            rows_to_insert.append(
                (tc.id, tc.test_set_id, tc.label,
                 json.dumps(tc.input_data), tc.expected_output, json.dumps(tc.tags), tc.created_at.isoformat())
            )
            result.append(tc)
        with self._conn() as c:
            c.executemany(
                "INSERT INTO test_cases (id,test_set_id,label,input_data,expected_output,tags,created_at) VALUES (?,?,?,?,?,?,?)",
                rows_to_insert,
            )
        return result

    # ── EvalRuns ──────────────────────────────────────────────────────────────

    def create_eval_run(self, workflow_id: str, name: str,
                        branch_a_config: dict, branch_b_config: dict,
                        description: str = "", test_set_id: str = None,
                        total_cases: int = 0) -> EvalRun:
        now = datetime.now(timezone.utc)
        er = EvalRun(
            id=str(uuid.uuid4()), workflow_id=workflow_id, name=name,
            description=description, test_set_id=test_set_id,
            branch_a_config=branch_a_config, branch_b_config=branch_b_config,
            status=EvalRunStatus.PENDING, total_cases=total_cases, created_at=now,
        )
        with self._conn() as c:
            c.execute("""
                INSERT INTO eval_runs
                (id,workflow_id,name,description,test_set_id,branch_a_config,
                 branch_b_config,status,total_cases,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (er.id, er.workflow_id, er.name, er.description, er.test_set_id,
                 json.dumps(er.branch_a_config), json.dumps(er.branch_b_config),
                 er.status.value, er.total_cases, er.created_at.isoformat()),
            )
            c.execute("UPDATE workflows SET eval_run_count=eval_run_count+1 WHERE id=?",
                      (workflow_id,))
        return er

    def get_eval_run(self, er_id: str) -> Optional[EvalRun]:
        with self._conn() as c:
            r = c.fetchone("SELECT * FROM eval_runs WHERE id=?", (er_id,))
        return EvalRun.from_row(_row(r)) if r else None

    def list_eval_runs(self, workflow_id: str = None, limit: int = 50) -> List[EvalRun]:
        with self._conn() as c:
            if workflow_id:
                rows = c.fetchall(
                    "SELECT * FROM eval_runs WHERE workflow_id=? ORDER BY created_at DESC LIMIT ?",
                    (workflow_id, limit))
            else:
                rows = c.fetchall(
                    "SELECT * FROM eval_runs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [EvalRun.from_row(_row(r)) for r in rows]

    def update_eval_run_status(self, er_id: str, status: EvalRunStatus,
                               total_cases: int = None):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            if status in (EvalRunStatus.COMPLETED, EvalRunStatus.FAILED):
                c.execute(
                    "UPDATE eval_runs SET status=?, completed_at=? WHERE id=?",
                    (status.value, now, er_id))
            else:
                c.execute("UPDATE eval_runs SET status=? WHERE id=?", (status.value, er_id))
            if total_cases is not None:
                c.execute("UPDATE eval_runs SET total_cases=? WHERE id=?", (total_cases, er_id))

    def get_eval_run_stats(self, er_id: str, comp_limit: int = 500) -> dict:
        """Aggregate stats for an eval run.

        Uses two queries:
          1. A full aggregate query (no LIMIT) for correct counts and averages.
          2. A limited query for the ``comparisons`` list shown in the UI.

        Args:
            comp_limit: Max comparisons to return in the ``comparisons`` list.
                        Does NOT affect total/decided/avg_divergence aggregates.
        """
        with self._conn() as c:
            # ── Aggregate query — full scan, no LIMIT ──────────────────────────
            agg_rows = c.fetchall("""
                SELECT
                    c.decided,
                    c.divergence_score,
                    d.choice,
                    d.confidence
                FROM comparisons c
                LEFT JOIN decisions d ON c.decision_id = d.id
                WHERE c.eval_run_id = ?
            """, (er_id,))
            agg_list = [_row(r) for r in agg_rows]

            # ── Limited list for UI display ────────────────────────────────────
            list_rows = c.fetchall("""
                SELECT
                    c.id,
                    c.decided,
                    c.divergence_score,
                    c.decision_id,
                    c.test_case_label,
                    d.choice,
                    d.confidence
                FROM comparisons c
                LEFT JOIN decisions d ON c.decision_id = d.id
                WHERE c.eval_run_id = ?
                ORDER BY COALESCE(c.divergence_score, -1) DESC
                LIMIT ?
            """, (er_id, comp_limit))
            comp_list = [_row(r) for r in list_rows]

            # ── Token totals per branch (for cost estimation in UI) ───────────
            tok_rows = c.fetchall("""
                SELECT 'A' AS side,
                       COALESCE(SUM(so.tokens_input),  0) AS tin,
                       COALESCE(SUM(so.tokens_output), 0) AS tout
                FROM step_outputs so
                JOIN comparisons   cp ON so.branch_id = cp.branch_a_id
                WHERE cp.eval_run_id = ?
                UNION ALL
                SELECT 'B' AS side,
                       COALESCE(SUM(so.tokens_input),  0) AS tin,
                       COALESCE(SUM(so.tokens_output), 0) AS tout
                FROM step_outputs so
                JOIN comparisons   cp ON so.branch_id = cp.branch_b_id
                WHERE cp.eval_run_id = ?
            """, (er_id, er_id))
            tok_map = {_row(r)["side"]: {"tokens_in": _row(r)["tin"], "tokens_out": _row(r)["tout"]} for r in tok_rows}

        total   = len(agg_list)
        decided = sum(1 for c in agg_list if c.get("decided"))
        scores  = [c["divergence_score"] for c in agg_list if c["divergence_score"] is not None]
        avg_div = round(sum(scores) / len(scores), 4) if scores else None

        buckets = [0, 0, 0, 0, 0]
        for s in scores:
            if not (0.0 <= s <= 1.0):
                continue  # skip malformed scores outside [0,1]
            idx = min(int(s * 5), 4)
            buckets[idx] += 1

        choice_breakdown = {"A": 0, "B": 0, "neither": 0, "both": 0}
        conf_breakdown   = {"high": 0, "medium": 0, "low": 0}
        for comp in agg_list:
            if comp.get("choice"):
                choice_breakdown[comp["choice"]] = choice_breakdown.get(comp["choice"], 0) + 1
            if comp.get("confidence"):
                conf_breakdown[comp["confidence"]] = conf_breakdown.get(comp["confidence"], 0) + 1

        return {
            "total":                total,
            "decided":              decided,
            "pending":              total - decided,
            "avg_divergence":       avg_div,
            "divergence_buckets":   buckets,
            "choice_breakdown":     choice_breakdown,
            "confidence_breakdown": conf_breakdown,
            "comparisons":          comp_list,   # includes choice field — no N+1 in UI
            "tokens_a":             tok_map.get("A", {}).get("tokens_in",  0),
            "tokens_a_out":         tok_map.get("A", {}).get("tokens_out", 0),
            "tokens_b":             tok_map.get("B", {}).get("tokens_in",  0),
            "tokens_b_out":         tok_map.get("B", {}).get("tokens_out", 0),
        }

    def batch_eval_run_stats(self, er_ids: List[str]) -> Dict[str, dict]:
        """Return lightweight stats for multiple eval runs in a single query.

        Used by list_eval_runs to avoid one get_eval_run_stats() call per row.
        Returns a dict keyed by eval_run_id.
        """
        if not er_ids:
            return {}
        placeholders = ",".join("?" * len(er_ids))
        with self._conn() as c:
            rows = c.fetchall(f"""
                SELECT
                    c.eval_run_id,
                    COUNT(c.id)                         AS total,
                    SUM(c.decided)                      AS decided,
                    AVG(c.divergence_score)             AS avg_divergence
                FROM comparisons c
                WHERE c.eval_run_id IN ({placeholders})
                GROUP BY c.eval_run_id
            """, er_ids)
        result: Dict[str, dict] = {}
        for r in rows:
            r = _row(r)
            eid = r["eval_run_id"]
            total   = r["total"]   or 0
            decided = r["decided"] or 0
            result[eid] = {
                "total":          total,
                "decided":        decided,
                "pending":        total - decided,
                "avg_divergence": round(r["avg_divergence"], 4) if r["avg_divergence"] is not None else None,
            }
        # Fill zeros for any er_id that had no comparisons yet
        for eid in er_ids:
            if eid not in result:
                result[eid] = {"total": 0, "decided": 0, "pending": 0, "avg_divergence": None}
        return result

    def delete_eval_run(self, er_id: str):
        with self._conn() as c:
            c.execute("DELETE FROM eval_runs WHERE id=?", (er_id,))

    # ── Workflows ─────────────────────────────────────────────────────────────

    def upsert_workflow(self, name: str, description: str = "", tags: list = None) -> Workflow:
        """Insert-or-update a workflow by name.

        Race-safe: if two concurrent callers try to create the same workflow
        simultaneously, the one that loses the INSERT race will catch the UNIQUE
        violation and retry with a SELECT on the next iteration.
        """
        now    = datetime.now(timezone.utc)
        new_id = str(uuid.uuid4())

        for attempt in range(2):
            try:
                with self._conn() as c:
                    row = c.fetchone("SELECT * FROM workflows WHERE name = ?", (name,))
                    if row:
                        wf = Workflow.from_row(_row(row))
                        new_desc = description if description is not None else wf.description
                        c.execute("UPDATE workflows SET description=?, updated_at=? WHERE id=?",
                                  (new_desc, now.isoformat(), wf.id))
                        wf.description = new_desc
                        wf.updated_at  = now
                        return wf
                    wf = Workflow(
                        id=new_id, name=name, description=description,
                        created_at=now, updated_at=now, tags=tags or [],
                    )
                    c.execute("""INSERT INTO workflows
                                 (id,name,description,created_at,updated_at,tags)
                                 VALUES (?,?,?,?,?,?)""",
                              (wf.id, wf.name, wf.description,
                               wf.created_at.isoformat(), wf.updated_at.isoformat(),
                               json.dumps(wf.tags)))
                    return wf
            except Exception as e:
                msg = str(e).lower()
                if ("unique" in msg or "duplicate" in msg) and attempt == 0:
                    continue   # lost the race — retry; SELECT will find the winner's row
                raise
        raise RuntimeError("upsert_workflow: exceeded retries on UNIQUE conflict")

    def get_workflow(self, wf_id: str) -> Optional[Workflow]:
        with self._conn() as c:
            r = c.fetchone("SELECT * FROM workflows WHERE id=?", (wf_id,))
        return Workflow.from_row(_row(r)) if r else None

    def list_workflows(self) -> List[Workflow]:
        """Scalar subqueries — no cartesian explosion from multi-table JOINs."""
        with self._conn() as c:
            rows = c.fetchall("""
                SELECT
                    w.*,
                    (SELECT COUNT(*) FROM workflow_runs r WHERE r.workflow_id = w.id) AS run_count,
                    (SELECT COUNT(*) FROM decisions d WHERE d.workflow_id = w.id)     AS decision_count,
                    (SELECT COUNT(*) FROM eval_runs e WHERE e.workflow_id = w.id)     AS eval_run_count
                FROM workflows w
                ORDER BY w.updated_at DESC
            """)
        return [Workflow.from_row(_row(r)) for r in rows]

    def delete_workflow(self, wf_id: str):
        with self._conn() as c:
            c.execute("DELETE FROM workflows WHERE id=?", (wf_id,))

    # ── Runs ──────────────────────────────────────────────────────────────────

    def list_runs(self, workflow_id: str, limit: int = 50, cursor: str = None) -> List[WorkflowRun]:
        filters, params = ["workflow_id=?"], [workflow_id]
        if cursor:
            filters.append("created_at < ?"); params.append(cursor)
        where = " AND ".join(filters)
        with self._conn() as c:
            rows = c.execute(
                f"SELECT * FROM workflow_runs WHERE {where} ORDER BY created_at DESC LIMIT ?",
                (*params, limit)
            ).fetchall()
        return [WorkflowRun.from_row(_row(r)) for r in rows]

    def create_run(self, workflow_id: str, input_data: dict = None,
                   metadata: dict = None, sdk_key_prefix: str = "",
                   eval_run_id: str = None, test_case_label: str = "") -> WorkflowRun:
        now = datetime.now(timezone.utc)
        run = WorkflowRun(
            id=str(uuid.uuid4()), workflow_id=workflow_id,
            status=RunStatus.RUNNING, created_at=now, completed_at=None,
            input_data=input_data or {}, metadata=metadata or {},
            sdk_key_prefix=sdk_key_prefix, eval_run_id=eval_run_id,
            test_case_label=test_case_label,
        )
        with self._conn() as c:
            c.execute("""INSERT INTO workflow_runs
                (id,workflow_id,status,created_at,input_data,metadata,sdk_key_prefix,
                 eval_run_id,test_case_label)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (run.id, run.workflow_id, run.status.value, run.created_at.isoformat(),
                 json.dumps(run.input_data), json.dumps(run.metadata), sdk_key_prefix,
                 eval_run_id, test_case_label))
        return run

    def complete_run(self, run_id: str, status: RunStatus = RunStatus.COMPLETED):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            c.execute("UPDATE workflow_runs SET status=?,completed_at=? WHERE id=?",
                      (status.value, now, run_id))

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        with self._conn() as c:
            r = c.fetchone("SELECT * FROM workflow_runs WHERE id=?", (run_id,))
        return WorkflowRun.from_row(_row(r)) if r else None


    # ── Branches ──────────────────────────────────────────────────────────────

    def create_branch(self, run_id: str, workflow_id: str, name: str, model_id: str,
                      temperature: float = 0.7, system_prompt: str = None,
                      extra_config: dict = None, is_baseline: bool = False) -> Branch:
        now = datetime.now(timezone.utc)
        b = Branch(
            id=str(uuid.uuid4()), run_id=run_id, workflow_id=workflow_id,
            name=name, model_id=model_id, temperature=temperature,
            system_prompt=system_prompt, extra_config=extra_config or {},
            created_at=now, is_baseline=is_baseline,
        )
        with self._conn() as c:
            c.execute("""INSERT INTO branches
                (id,run_id,workflow_id,name,model_id,temperature,system_prompt,
                 extra_config,created_at,is_baseline)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (b.id, b.run_id, b.workflow_id, b.name, b.model_id, b.temperature,
                 b.system_prompt, json.dumps(b.extra_config),
                 b.created_at.isoformat(), int(b.is_baseline)))
        return b

    def get_branch(self, branch_id: str) -> Optional[Branch]:
        with self._conn() as c:
            r = c.fetchone("SELECT * FROM branches WHERE id=?", (branch_id,))
        return Branch.from_row(_row(r)) if r else None

    def list_branches(self, run_id: str) -> List[Branch]:
        with self._conn() as c:
            rows = c.fetchall("SELECT * FROM branches WHERE run_id=? ORDER BY created_at", (run_id,))
        return [Branch.from_row(_row(r)) for r in rows]

    # ── Step Outputs ──────────────────────────────────────────────────────────

    def save_step_output(self, run_id: str, branch_id: str, step_name: str,
                         step_index: int, input_messages: list, output_text: str,
                         model_id: str, temperature: float = 0.7,
                         tokens_input: int = 0, tokens_output: int = 0,
                         latency_ms: int = 0, error: str = None,
                         trace_id: str = None, span_id: str = None,
                         cost_usd: float = None) -> StepOutput:
        # Generate OTel trace/span IDs if tracing is enabled and none were provided
        from .tracing import tracer as _otel_tracer
        if _otel_tracer.enabled and not trace_id:
            with _otel_tracer.step_span(
                step_name, model_id=model_id, temperature=temperature,
                run_id=run_id,
            ) as span:
                _otel_tracer.record_step_result(
                    span, tokens_in=tokens_input, tokens_out=tokens_output,
                    latency_ms=latency_ms, error=error,
                )
                trace_id, span_id = _otel_tracer.get_ids(span)

        # Auto-estimate cost if not provided and tokens are available
        if cost_usd is None and (tokens_input or tokens_output):
            cost_usd = _estimate_cost(model_id, tokens_input, tokens_output)

        now = datetime.now(timezone.utc)
        so = StepOutput(
            id=str(uuid.uuid4()), run_id=run_id, branch_id=branch_id,
            step_name=step_name, step_index=step_index, input_messages=input_messages,
            output_text=output_text, model_id=model_id, temperature=temperature,
            tokens_input=tokens_input, tokens_output=tokens_output,
            latency_ms=latency_ms, created_at=now, error=error,
            trace_id=trace_id, span_id=span_id, cost_usd=cost_usd,
        )
        with self._conn() as c:
            c.execute("""INSERT INTO step_outputs
                (id,run_id,branch_id,step_name,step_index,input_messages,output_text,
                 model_id,temperature,tokens_input,tokens_output,latency_ms,created_at,error,
                 trace_id,span_id,cost_usd)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (so.id, so.run_id, so.branch_id, so.step_name, so.step_index,
                 json.dumps(so.input_messages), so.output_text, so.model_id,
                 so.temperature, so.tokens_input, so.tokens_output,
                 so.latency_ms, so.created_at.isoformat(), so.error,
                 so.trace_id, so.span_id, so.cost_usd))
        return so

    def batch_save_step_outputs(self, steps: List[dict]) -> List[StepOutput]:
        """Insert many step outputs in a single transaction (10x fewer roundtrips)."""
        now = datetime.now(timezone.utc).isoformat()
        records = []
        objects = []
        for s in steps:
            so = StepOutput(
                id=str(uuid.uuid4()),
                run_id=s["run_id"], branch_id=s["branch_id"],
                step_name=s["step_name"], step_index=s.get("step_index", 0),
                input_messages=s.get("input_messages", []),
                output_text=s.get("output_text", ""),
                model_id=s.get("model_id", ""), temperature=s.get("temperature", 0.7),
                tokens_input=s.get("tokens_input", 0), tokens_output=s.get("tokens_output", 0),
                latency_ms=s.get("latency_ms", 0), created_at=datetime.now(timezone.utc),
                error=s.get("error"),
            )
            records.append((
                so.id, so.run_id, so.branch_id, so.step_name, so.step_index,
                json.dumps(so.input_messages), so.output_text, so.model_id,
                so.temperature, so.tokens_input, so.tokens_output,
                so.latency_ms, so.created_at.isoformat(), so.error,
            ))
            objects.append(so)
        with self._conn() as c:
            c.executemany("""INSERT INTO step_outputs
                (id,run_id,branch_id,step_name,step_index,input_messages,output_text,
                 model_id,temperature,tokens_input,tokens_output,latency_ms,created_at,error)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", records)
        return objects

    def get_step_outputs_for_branch(self, branch_id: str) -> List[StepOutput]:
        with self._conn() as c:
            rows = c.fetchall(
                "SELECT * FROM step_outputs WHERE branch_id=? ORDER BY step_index",
                (branch_id,))
        return [StepOutput.from_row(_row(r)) for r in rows]

    def get_step_outputs_for_branches(self, branch_a_id: str, branch_b_id: str) -> List[StepOutput]:
        """Fetch all step outputs for two branches in one query (used by sdk_create_comparison)."""
        with self._conn() as c:
            rows = c.fetchall(
                "SELECT * FROM step_outputs WHERE branch_id IN (?, ?) ORDER BY branch_id, step_index",
                (branch_a_id, branch_b_id))
        return [StepOutput.from_row(_row(r)) for r in rows]

    def get_step_outputs_bulk(self, branch_ids: List[str]) -> Dict[str, List[StepOutput]]:
        """Batch-fetch step outputs for many branches in one query.

        Returns {branch_id: [StepOutput, ...]} dict.
        SQLite has a variable limit (~999), so we chunk large batches.
        """
        result: Dict[str, List[StepOutput]] = {bid: [] for bid in branch_ids}
        if not branch_ids:
            return result
        CHUNK = 900
        with self._conn() as c:
            for i in range(0, len(branch_ids), CHUNK):
                chunk = branch_ids[i:i + CHUNK]
                placeholders = ",".join("?" * len(chunk))
                rows = c.fetchall(
                    f"SELECT * FROM step_outputs WHERE branch_id IN ({placeholders}) "
                    "ORDER BY branch_id, step_index",
                    chunk)
                for r in rows:
                    so = StepOutput.from_row(_row(r))
                    result.setdefault(so.branch_id, []).append(so)
        return result

    def get_step_outputs_for_run(self, run_id: str) -> List[StepOutput]:
        with self._conn() as c:
            rows = c.fetchall(
                "SELECT * FROM step_outputs WHERE run_id=? ORDER BY branch_id, step_index",
                (run_id,))
        return [StepOutput.from_row(_row(r)) for r in rows]

    def prune_step_outputs(self, older_than_days: int = 30) -> int:
        """Delete step_outputs older than N days. Preserves comparisons and decisions.

        step_outputs are the heaviest table (input_messages + output_text per LLM call).
        Old ones are only needed to re-render the CompareView diff — comparisons already
        cache divergence_score and step_divergence_scores so stats are unaffected.

        Returns the number of rows deleted.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        with self._conn() as c:
            cur = c.execute(
                "DELETE FROM step_outputs WHERE created_at < ?", (cutoff,)
            )
            # rowcount works on both SQLite and psycopg2
            return getattr(cur, "rowcount", 0)

    # ── Comparisons ───────────────────────────────────────────────────────────

    def create_comparison(self, run_id: str, workflow_id: str,
                          branch_a_id: str, branch_b_id: str,
                          step_names: list = None,
                          eval_run_id: str = None,
                          test_case_label: str = "",
                          divergence_score: float = None,
                          step_divergence_scores: dict = None,
                          eval_results: dict = None,
                          scoring_status: str = "completed") -> Comparison:
        now = datetime.now(timezone.utc)
        comp = Comparison(
            id=str(uuid.uuid4()), run_id=run_id, workflow_id=workflow_id,
            branch_a_id=branch_a_id, branch_b_id=branch_b_id,
            step_names=step_names or [], created_at=now,
            eval_run_id=eval_run_id, test_case_label=test_case_label,
            divergence_score=divergence_score,
            step_divergence_scores=step_divergence_scores or {},
            eval_results=eval_results or {},
            scoring_status=ScoringStatus(scoring_status),
        )
        with self._conn() as c:
            c.execute("""INSERT INTO comparisons
                (id,run_id,workflow_id,branch_a_id,branch_b_id,step_names,created_at,
                 eval_run_id,test_case_label,divergence_score,step_divergence_scores,
                 eval_results,scoring_status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (comp.id, comp.run_id, comp.workflow_id, comp.branch_a_id,
                 comp.branch_b_id, json.dumps(comp.step_names),
                 comp.created_at.isoformat(), comp.eval_run_id,
                 comp.test_case_label, comp.divergence_score,
                 json.dumps(comp.step_divergence_scores),
                 json.dumps(comp.eval_results), comp.scoring_status.value))
        # ── Flywheel 1: auto-record divergence in performance corpus ──────────
        if comp.test_case_label and comp.eval_run_id:
            try:
                self.record_test_case_performance(
                    test_case_label=comp.test_case_label,
                    workflow_id=workflow_id,
                    eval_run_id=comp.eval_run_id,
                    comparison_id=comp.id,
                    divergence_score=divergence_score,
                )
            except Exception:
                _log.warning("Flywheel: failed to record test-case performance in create_comparison", exc_info=True)
        return comp

    def update_comparison_scoring(self, comp_id: str,
                                  divergence_score: float = None,
                                  step_divergence_scores: dict = None,
                                  eval_results: dict = None,
                                  scoring_status: str = None) -> None:
        """Update scoring results on a comparison (called by background worker)."""
        updates, params = [], []
        if divergence_score is not None:
            updates.append("divergence_score=?"); params.append(divergence_score)
        if step_divergence_scores is not None:
            updates.append("step_divergence_scores=?"); params.append(json.dumps(step_divergence_scores))
        if eval_results is not None:
            updates.append("eval_results=?"); params.append(json.dumps(eval_results))
        if scoring_status is not None:
            updates.append("scoring_status=?"); params.append(scoring_status)
        if not updates:
            return
        params.append(comp_id)
        with self._conn() as c:
            c.execute(f"UPDATE comparisons SET {', '.join(updates)} WHERE id=?", params)

    def get_comparison(self, comp_id: str) -> Optional[Comparison]:
        with self._conn() as c:
            r = c.fetchone("SELECT * FROM comparisons WHERE id=?", (comp_id,))
        return Comparison.from_row(_row(r)) if r else None

    def get_comparison_full(self, comp_id: str) -> Optional[dict]:
        """Fetch comparison + branches + steps + decision + eval_run + run in one
        connection context (6 queries vs the previous 8 round-trips).

        Returns a dict with keys:
            comp, branch_a, branch_b, steps_a, steps_b,
            decision, eval_run_info, run_input
        or None if the comparison doesn't exist.
        """
        with self._conn() as c:
            # 1. Comparison row
            r = c.fetchone("SELECT * FROM comparisons WHERE id=?", (comp_id,))
            if not r:
                return None
            comp = Comparison.from_row(_row(r))

            # 2. Both branches in a single IN query
            branch_rows = c.fetchall(
                "SELECT * FROM branches WHERE id IN (?, ?)",
                (comp.branch_a_id, comp.branch_b_id))
            branches: Dict[str, Branch] = {}
            for br in branch_rows:
                b = Branch.from_row(_row(br))
                branches[b.id] = b

            # 3. All step outputs for both branches in one query
            step_rows = c.fetchall(
                "SELECT * FROM step_outputs "
                "WHERE branch_id IN (?, ?) "
                "ORDER BY branch_id, step_index",
                (comp.branch_a_id, comp.branch_b_id))
            steps_by_branch: Dict[str, List[StepOutput]] = {
                comp.branch_a_id: [], comp.branch_b_id: []}
            for sr in step_rows:
                so = StepOutput.from_row(_row(sr))
                steps_by_branch.setdefault(so.branch_id, []).append(so)

            # 4. Decision (optional)
            decision_obj = None
            if comp.decision_id:
                dr = c.fetchone("SELECT * FROM decisions WHERE id=?",
                                (comp.decision_id,))
                if dr:
                    decision_obj = Decision.from_row(_row(dr))

            # 5. Eval run — only id + name needed by the response
            eval_run_info = None
            if comp.eval_run_id:
                er = c.fetchone("SELECT id, name FROM eval_runs WHERE id=?",
                                (comp.eval_run_id,))
                if er:
                    r2 = _row(er)
                    eval_run_info = {"id": r2["id"], "name": r2["name"]}

            # 6. Run input data
            run_input: dict = {}
            rr = c.fetchone("SELECT * FROM workflow_runs WHERE id=?", (comp.run_id,))
            if rr:
                run_input = WorkflowRun.from_row(_row(rr)).input_data

        return {
            "comp":          comp,
            "branch_a":      branches.get(comp.branch_a_id),
            "branch_b":      branches.get(comp.branch_b_id),
            "steps_a":       steps_by_branch.get(comp.branch_a_id, []),
            "steps_b":       steps_by_branch.get(comp.branch_b_id, []),
            "decision":      decision_obj,
            "eval_run_info": eval_run_info,
            "run_input":     run_input,
        }

    def list_comparisons(self, workflow_id: str = None, undecided_only: bool = False,
                         eval_run_id: str = None, run_id: str = None,
                         limit: int = 200, offset: int = 0, cursor: str = None) -> List[Comparison]:
        filters, params = [], []
        if workflow_id:
            filters.append("workflow_id=?"); params.append(workflow_id)
        if undecided_only:
            filters.append("decided=0")
        if eval_run_id:
            filters.append("eval_run_id=?"); params.append(eval_run_id)
        if run_id:
            filters.append("run_id=?"); params.append(run_id)
        if cursor:
            filters.append("created_at < ?"); params.append(cursor)
        
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        order = "ORDER BY COALESCE(divergence_score, -1) DESC, created_at DESC"
        with self._conn() as c:
            rows = c.fetchall(
                f"SELECT * FROM comparisons {where} {order} LIMIT ? OFFSET ?",
                params + [limit, offset])
        return [Comparison.from_row(_row(r)) for r in rows]

    def mark_comparison_decided(self, comp_id: str, decision_id: str):
        with self._conn() as c:
            c.execute("UPDATE comparisons SET decided=1, decision_id=? WHERE id=?",
                      (decision_id, comp_id))

    # ── Decisions ─────────────────────────────────────────────────────────────

    def create_decision(self, comparison_id: str, run_id: str, workflow_id: str,
                        reviewer_id: str, choice: DecisionChoice,
                        confidence: ConfidenceLevel, rationale_for_choice: str,
                        rationale_for_rejection: str, tags: list = None,
                        branch_winner_id: str = None, branch_loser_id: str = None,
                        divergence_score: float = 0.0,
                        divergence_summary: str = None,
                        eval_run_id: str = None) -> Decision:
        import hashlib
        now = datetime.now(timezone.utc)
        d = Decision(
            id=str(uuid.uuid4()), comparison_id=comparison_id, run_id=run_id,
            workflow_id=workflow_id, reviewer_id=reviewer_id, choice=choice,
            confidence=confidence, rationale_for_choice=rationale_for_choice,
            rationale_for_rejection=rationale_for_rejection, tags=tags or [],
            created_at=now, branch_winner_id=branch_winner_id,
            branch_loser_id=branch_loser_id, divergence_score=divergence_score,
            divergence_summary=divergence_summary, eval_run_id=eval_run_id,
        )
        _comp_row = None
        with self._conn() as c:
            c.execute("""INSERT INTO decisions
                (id,comparison_id,run_id,workflow_id,reviewer_id,choice,confidence,
                 rationale_for_choice,rationale_for_rejection,tags,created_at,
                 branch_winner_id,branch_loser_id,divergence_score,divergence_summary,
                 eval_run_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (d.id, d.comparison_id, d.run_id, d.workflow_id, d.reviewer_id,
                 d.choice.value, d.confidence.value, d.rationale_for_choice,
                 d.rationale_for_rejection, json.dumps(d.tags),
                 d.created_at.isoformat(), d.branch_winner_id, d.branch_loser_id,
                 d.divergence_score, d.divergence_summary, d.eval_run_id))
            c.execute("UPDATE comparisons SET decided=1, decision_id=? WHERE id=?",
                      (d.id, comparison_id))
            c.execute("UPDATE workflows SET decision_count=decision_count+1 WHERE id=?",
                      (workflow_id,))

            # ── Flywheel 2: compute provenance_hash + data_category ───────────
            run_row = c.fetchone(
                "SELECT input_data FROM workflow_runs WHERE id=?", (run_id,))
            raw_input = ""
            if run_row:
                try:
                    _rr = _row(run_row)
                    raw_input = json.loads(_rr.get("input_data") or "{}").get("input", "") or ""
                except Exception:
                    _rr = _row(run_row)
                    raw_input = str(_rr.get("input_data") or "")
            ph = hashlib.sha256(
                f"{workflow_id}:{d.id}:{str(raw_input)[:200]}".encode()
            ).hexdigest()
            # auto-classify data_category from tags
            tag_str = " ".join(tags or []).lower()
            if any(w in tag_str for w in ("legal", "lawsuit", "attorney", "injury", "cpsc")):
                dc = "legal"
            elif any(w in tag_str for w in ("billing", "charge", "refund", "payment")):
                dc = "billing"
            elif any(w in tag_str for w in ("safety", "allergy", "medical", "health")):
                dc = "safety"
            elif any(w in tag_str for w in ("churn", "retention", "vip", "escalation")):
                dc = "retention"
            else:
                dc = "general"
            c.execute(
                "UPDATE decisions SET provenance_hash=?, data_category=? WHERE id=?",
                (ph, dc, d.id),
            )

            # grab test_case_label + eval_run_id from comparison for flywheel 1
            _comp_row = c.fetchone(
                "SELECT test_case_label, eval_run_id FROM comparisons WHERE id=?",
                (comparison_id,),
            )

        # ── Flywheel 1: record human choice in performance corpus ─────────────
        if _comp_row:
            _cr = _row(_comp_row)
            tcl  = _cr.get("test_case_label") or ""
            erid = _cr.get("eval_run_id") or eval_run_id or ""
            if tcl and erid:
                try:
                    self.record_test_case_performance(
                        test_case_label=tcl,
                        workflow_id=workflow_id,
                        eval_run_id=erid,
                        decision_choice=choice.value,
                        reviewer_confidence=confidence.value,
                    )
                except Exception:
                    _log.warning("Flywheel: failed to record performance in create_decision", exc_info=True)
        return d

    def update_decision(self, decision_id: str, choice: DecisionChoice,
                        confidence: ConfidenceLevel, rationale_for_choice: str,
                        rationale_for_rejection: str, tags: list,
                        reviewer_id: str = None,
                        branch_winner_id: str = None,
                        branch_loser_id: str = None) -> Optional[Decision]:
        """Update an existing decision in place (edit flow).

        Also updates branch_winner_id/branch_loser_id and sets updated_at so the
        edit is auditable — previously these fields went stale after an edit.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            if reviewer_id:
                c.execute("""
                    UPDATE decisions
                    SET choice=?, confidence=?, rationale_for_choice=?,
                        rationale_for_rejection=?, tags=?, reviewer_id=?,
                        branch_winner_id=?, branch_loser_id=?, updated_at=?
                    WHERE id=?
                """, (choice.value, confidence.value, rationale_for_choice,
                      rationale_for_rejection, json.dumps(tags), reviewer_id,
                      branch_winner_id, branch_loser_id, now, decision_id))
            else:
                c.execute("""
                    UPDATE decisions
                    SET choice=?, confidence=?, rationale_for_choice=?,
                        rationale_for_rejection=?, tags=?,
                        branch_winner_id=?, branch_loser_id=?, updated_at=?
                    WHERE id=?
                """, (choice.value, confidence.value, rationale_for_choice,
                      rationale_for_rejection, json.dumps(tags),
                      branch_winner_id, branch_loser_id, now, decision_id))
            r = c.fetchone("SELECT * FROM decisions WHERE id=?", (decision_id,))
        return Decision.from_row(_row(r)) if r else None

    def get_decision(self, decision_id: str) -> Optional[Decision]:
        with self._conn() as c:
            r = c.fetchone("SELECT * FROM decisions WHERE id=?", (decision_id,))
        return Decision.from_row(_row(r)) if r else None

    def list_decisions(self, workflow_id: str = None, eval_run_id: str = None,
                       limit: int = 100, offset: int = 0) -> List[Decision]:
        filters, params = [], []
        if workflow_id:
            filters.append("workflow_id=?"); params.append(workflow_id)
        if eval_run_id:
            filters.append("eval_run_id=?"); params.append(eval_run_id)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        with self._conn() as c:
            rows = c.fetchall(
                f"SELECT * FROM decisions {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset])
        return [Decision.from_row(_row(r)) for r in rows]

    def list_decision_tags(self, workflow_id: str = None) -> List[str]:
        """Return distinct tags used across decisions, sorted by frequency."""
        filters = ["tags IS NOT NULL", "tags != '[]'"]
        params: List = []
        if workflow_id:
            filters.append("workflow_id=?")
            params.append(workflow_id)
        where = "WHERE " + " AND ".join(filters)
        with self._conn() as c:
            rows = c.fetchall(f"SELECT tags FROM decisions {where}", params)
        freq: Dict[str, int] = {}
        for row in rows:
            r = _row(row)
            try:
                tags = json.loads(r.get("tags") or "[]")
            except Exception:
                continue
            for t in tags:
                if isinstance(t, str) and t.strip():
                    freq[t.strip()] = freq.get(t.strip(), 0) + 1
        return sorted(freq.keys(), key=lambda t: -freq[t])

    def export_decisions_jsonl(self, workflow_id: str = None,
                               eval_run_id: str = None):
        filters, params = [], []
        if workflow_id:
            filters.append("workflow_id=?"); params.append(workflow_id)
        if eval_run_id:
            filters.append("eval_run_id=?"); params.append(eval_run_id)
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        
        with self._read_conn() as c:
            cur = c.execute(f"SELECT * FROM decisions {where} ORDER BY created_at DESC", params)
            for row in cur:
                d = Decision.from_row(_row(row))
                yield json.dumps({
                    "comparison_id":          d.comparison_id,
                    "eval_run_id":            d.eval_run_id,
                    "choice":                 d.choice.value,
                    "confidence":             d.confidence.value,
                    "rationale_for_choice":   d.rationale_for_choice,
                    "rationale_for_rejection":d.rationale_for_rejection,
                    "tags":                   d.tags,
                    "divergence_score":       d.divergence_score,
                    "created_at":             d.created_at.isoformat(),
                }) + "\n"

    def export_dpo_jsonl(self, workflow_id: str = None,
                         eval_run_id: str = None,
                         min_confidence: str = None,
                         min_divergence: float = None,
                         require_consent: bool = False):
        """Export decisions as DPO (Direct Preference Optimization) training data.

        Format per line:
            {"prompt": "<input>", "chosen": "<winner_output>", "rejected": "<loser_output>"}

        Only exports decisions with a clear winner (A or B), skipping 'both'/'neither'.

        Filters:
            min_confidence: minimum confidence level (low/medium/high/definitive)
            min_divergence: minimum divergence score (0.0–1.0)
            require_consent: if True, skip workflows without active 'training_data' consent
        """
        CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2, "definitive": 3}
        min_conf_val = CONFIDENCE_ORDER.get(min_confidence, -1) if min_confidence else -1

        filters, params = [], []
        if workflow_id:
            filters.append("d.workflow_id=?"); params.append(workflow_id)
        if eval_run_id:
            filters.append("d.eval_run_id=?"); params.append(eval_run_id)
        filters.append("d.choice IN ('A', 'B')")
        filters.append("d.branch_winner_id IS NOT NULL")
        filters.append("d.branch_loser_id IS NOT NULL")
        where = "WHERE " + " AND ".join(filters)

        # Consent cache for per-workflow checks
        consent_cache: dict = {}

        with self._read_conn() as c:
            rows = c.fetchall(f"""
                SELECT d.*, r.input_data
                FROM decisions d
                JOIN workflow_runs r ON r.id = d.run_id
                {where}
                ORDER BY d.created_at DESC
            """, params)

            # Parse decisions + collect branch IDs for bulk fetch
            decisions_with_input = []
            branch_ids = set()
            for row in rows:
                r = _row(row)
                input_data = json.loads(r.pop("input_data", None) or "{}")
                decision = Decision.from_row(r)

                # Confidence filter
                if min_conf_val >= 0:
                    dec_conf = CONFIDENCE_ORDER.get(decision.confidence.value, -1)
                    if dec_conf < min_conf_val:
                        continue

                # Divergence filter
                if min_divergence is not None and decision.divergence_score is not None:
                    if decision.divergence_score < min_divergence:
                        continue

                # Consent filter
                if require_consent:
                    wid = decision.workflow_id or ""
                    if wid not in consent_cache:
                        consent_cache[wid] = self.has_consent(wid, "training_data")
                    if not consent_cache[wid]:
                        continue

                decisions_with_input.append((decision, input_data))
                if decision.branch_winner_id:
                    branch_ids.add(decision.branch_winner_id)
                if decision.branch_loser_id:
                    branch_ids.add(decision.branch_loser_id)

            # Single bulk query instead of 2N individual queries
            steps_by_branch = self.get_step_outputs_bulk(list(branch_ids))

            for decision, input_data in decisions_with_input:
                winner_steps = steps_by_branch.get(decision.branch_winner_id, [])
                loser_steps = steps_by_branch.get(decision.branch_loser_id, [])

                chosen = " ".join(s.output_text for s in winner_steps if s.output_text)
                rejected = " ".join(s.output_text for s in loser_steps if s.output_text)

                if not chosen or not rejected:
                    continue

                prompt = json.dumps(input_data) if input_data else ""

                yield json.dumps({
                    "prompt":   prompt,
                    "chosen":   chosen,
                    "rejected": rejected,
                    "metadata": {
                        "comparison_id":    decision.comparison_id,
                        "confidence":       decision.confidence.value,
                        "divergence_score": decision.divergence_score,
                    },
                }) + "\n"

    def export_openai_ft_jsonl(self, workflow_id: str = None,
                               eval_run_id: str = None):
        """Export decisions as OpenAI fine-tuning format.

        Format per line (chat completion):
            {"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}

        Uses the winning branch output as the assistant response.
        """
        filters, params = [], []
        if workflow_id:
            filters.append("d.workflow_id=?"); params.append(workflow_id)
        if eval_run_id:
            filters.append("d.eval_run_id=?"); params.append(eval_run_id)
        filters.append("d.choice IN ('A', 'B')")
        filters.append("d.branch_winner_id IS NOT NULL")
        where = "WHERE " + " AND ".join(filters)

        with self._read_conn() as c:
            rows = c.fetchall(f"""
                SELECT d.*, r.input_data
                FROM decisions d
                JOIN workflow_runs r ON r.id = d.run_id
                {where}
                ORDER BY d.created_at DESC
            """, params)

            # Parse decisions + collect branch IDs for bulk fetch
            decisions_with_input = []
            branch_ids = set()
            for row in rows:
                r = _row(row)
                input_data = json.loads(r.pop("input_data", None) or "{}")
                decision = Decision.from_row(r)
                decisions_with_input.append((decision, input_data))
                if decision.branch_winner_id:
                    branch_ids.add(decision.branch_winner_id)

            # Single bulk query instead of N individual queries
            steps_by_branch = self.get_step_outputs_bulk(list(branch_ids))

            for decision, input_data in decisions_with_input:
                winner_steps = steps_by_branch.get(decision.branch_winner_id, [])
                chosen = " ".join(s.output_text for s in winner_steps if s.output_text)
                if not chosen:
                    continue

                user_content = json.dumps(input_data) if input_data else ""

                messages = []
                if winner_steps and winner_steps[0].input_messages:
                    for msg in winner_steps[0].input_messages:
                        if msg.get("role") == "system":
                            messages.append(msg)
                            break

                messages.append({"role": "user", "content": user_content})
                messages.append({"role": "assistant", "content": chosen})

                yield json.dumps({"messages": messages}) + "\n"

    # ── API Keys ──────────────────────────────────────────────────────────────

    def create_api_key(self, name: str) -> tuple:
        """Create a new API key hashed with argon2id (includes embedded salt)."""
        if _ph is None:
            raise RuntimeError(
                "argon2-cffi is required for API key management. "
                "Install it: pip install argon2-cffi"
            )
        import secrets
        raw      = "fm_" + secrets.token_urlsafe(32)
        key_hash = _ph.hash(raw)   # argon2id; salt is embedded in the hash string
        now      = datetime.now(timezone.utc)
        ak = ApiKey(
            id=str(uuid.uuid4()), name=name, key_hash=key_hash,
            key_prefix=raw[:8], created_at=now,
        )
        with self._conn() as c:
            c.execute("INSERT INTO api_keys (id,name,key_hash,key_prefix,created_at) VALUES (?,?,?,?,?)",
                      (ak.id, ak.name, ak.key_hash, ak.key_prefix, ak.created_at.isoformat()))
        return ak, raw

    def verify_api_key(self, raw_key: str) -> Optional[ApiKey]:
        """Verify an API key.

        Algorithm:
          1. Check bounded LRU TTL cache — avoids argon2 computation on hot paths.
          2. Look up candidate rows by key_prefix (fast indexed lookup).
          3. Verify with argon2id; auto-upgrade legacy SHA-256 keys on first match.
          4. Cache the result for _VERIFY_TTL seconds; debounce last_used_at DB write.
        """
        import hashlib
        # ── 1. Cache hit ──────────────────────────────────────────────────────
        now_ts = time.time()
        with _verify_lock:
            entry = _verify_cache.get(raw_key)
            if entry and entry[0] > now_ts:
                return entry[1]

        # ── 2. Look up by key_prefix ──────────────────────────────────────────
        key_prefix  = raw_key[:8]
        matched_row = None
        needs_upgrade = False

        with self._conn() as c:
            rows = c.fetchall(
                "SELECT * FROM api_keys WHERE key_prefix=? AND is_active=1", (key_prefix,))

            for raw_row in rows:
                row    = _row(raw_row)
                stored = row["key_hash"]
                try:
                    if stored.startswith("$argon2") and _ph:
                        # argon2id path — uses module-level singleton
                        _ph.verify(stored, raw_key)
                        matched_row = row
                        if _ph.check_needs_rehash(stored):
                            c.execute("UPDATE api_keys SET key_hash=? WHERE id=?",
                                      (_ph.hash(raw_key), row["id"]))
                    else:
                        # Legacy SHA-256 — verify and schedule upgrade
                        if hashlib.sha256(raw_key.encode()).hexdigest() == stored:
                            matched_row = row
                            needs_upgrade = True
                    if matched_row:
                        break
                except (VerifyMismatchError, VerificationError, InvalidHashError):
                    continue
                except Exception:
                    continue

            if matched_row is None:
                _cache_put(raw_key, (now_ts + _VERIFY_TTL, None))
                return None

            # ── 3. Auto-upgrade legacy SHA-256 key to argon2id ────────────────
            if needs_upgrade and _ph:
                c.execute("UPDATE api_keys SET key_hash=? WHERE id=?",
                          (_ph.hash(raw_key), matched_row["id"]))

            # ── 4. Debounce last_used_at write (max 1 write per 60s per key) ──
            last = matched_row.get("last_used_at")
            now  = datetime.now(timezone.utc)
            if not last or (now - datetime.fromisoformat(last)).total_seconds() > 60:
                c.execute("UPDATE api_keys SET last_used_at=? WHERE id=?",
                          (now.isoformat(), matched_row["id"]))

        ak = ApiKey.from_row(matched_row)
        _cache_put(raw_key, (now_ts + _VERIFY_TTL, ak))
        return ak

    def list_api_keys(self, active_only: bool = True) -> List[ApiKey]:
        sql = ("SELECT * FROM api_keys WHERE is_active=1 ORDER BY created_at DESC"
               if active_only else
               "SELECT * FROM api_keys ORDER BY created_at DESC")
        with self._conn() as c:
            rows = c.fetchall(sql)
        return [ApiKey.from_row(_row(r)) for r in rows]

    def revoke_api_key(self, key_id: str):
        with self._conn() as c:
            c.execute("UPDATE api_keys SET is_active=0 WHERE id=?", (key_id,))

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._conn() as c:
            row = c.fetchone("SELECT value FROM settings WHERE key=?", (key,))
            if row is None:
                return default
            value = _row(row)["value"]
            return _decrypt_setting(value) if key in _SENSITIVE_KEYS else value

    def set_setting(self, key: str, value: str) -> None:
        stored = _encrypt_setting(value) if key in _SENSITIVE_KEYS else value
        with self._conn() as c:
            c.execute(
                "INSERT INTO settings(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, stored),
            )

    def get_all_settings(self) -> dict:
        with self._conn() as c:
            rows = c.fetchall("SELECT key, value FROM settings", ())
            result = {}
            for r in rows:
                rd = _row(r)
                k, v = rd["key"], rd["value"]
                result[k] = _decrypt_setting(v) if k in _SENSITIVE_KEYS else v
            return result

    # ── LLM Providers ────────────────────────────────────────────────────────

    def create_provider(self, name: str, provider_type: str = "openai",
                        base_url: str = "", api_key: str = "",
                        is_default: bool = False) -> dict:
        """Create an LLM provider entry. API key is encrypted at rest."""
        now = datetime.now(timezone.utc).isoformat()
        pid = str(uuid.uuid4())
        encrypted = _encrypt_setting(api_key) if api_key else ""
        with self._conn() as c:
            # If this is the first provider or is_default, clear other defaults
            if is_default:
                c.execute("UPDATE llm_providers SET is_default=0")
            # If no providers exist yet, make this one the default
            existing = c.fetchone("SELECT COUNT(*) AS cnt FROM llm_providers")
            cnt = _row(existing).get("cnt", 0)
            if cnt == 0:
                is_default = True
            c.execute("""INSERT INTO llm_providers
                (id, name, provider_type, base_url, api_key_encrypted,
                 is_default, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (pid, name, provider_type, base_url, encrypted,
                 int(is_default), now, now))
        return {
            "id": pid, "name": name, "provider_type": provider_type,
            "base_url": base_url, "is_default": bool(is_default),
            "created_at": now, "updated_at": now,
        }

    def list_providers(self) -> list:
        """List all providers. API keys are NOT returned."""
        with self._read_conn() as c:
            rows = c.fetchall(
                "SELECT id, name, provider_type, base_url, api_key_encrypted, "
                "is_default, created_at, updated_at "
                "FROM llm_providers ORDER BY is_default DESC, created_at ASC")
        result = []
        for r in rows:
            rd = _row(r)
            # Mask the key — never return raw
            encrypted = rd.pop("api_key_encrypted", "")
            has_key = bool(encrypted)
            masked = ""
            if has_key:
                try:
                    raw = _decrypt_setting(encrypted)
                    masked = raw[:4] + "..." + raw[-4:] if len(raw) > 8 else "***"
                except Exception:
                    masked = "***"
            rd["api_key_set"] = has_key
            rd["api_key_masked"] = masked
            rd["is_default"] = bool(rd.get("is_default"))
            result.append(rd)
        return result

    def get_provider(self, provider_id: str) -> Optional[dict]:
        """Get a single provider (without raw key)."""
        with self._read_conn() as c:
            r = c.fetchone(
                "SELECT id, name, provider_type, base_url, api_key_encrypted, "
                "is_default, created_at, updated_at "
                "FROM llm_providers WHERE id=?", (provider_id,))
        if not r:
            return None
        rd = _row(r)
        encrypted = rd.pop("api_key_encrypted", "")
        has_key = bool(encrypted)
        masked = ""
        if has_key:
            try:
                raw = _decrypt_setting(encrypted)
                masked = raw[:4] + "..." + raw[-4:] if len(raw) > 8 else "***"
            except Exception:
                masked = "***"
        rd["api_key_set"] = has_key
        rd["api_key_masked"] = masked
        rd["is_default"] = bool(rd.get("is_default"))
        return rd

    def get_provider_credentials(self, provider_id: str) -> Optional[dict]:
        """Get provider credentials (decrypted key + base_url) for LLM calls.
        Internal use only — never expose via API.
        """
        with self._read_conn() as c:
            r = c.fetchone(
                "SELECT base_url, api_key_encrypted, provider_type "
                "FROM llm_providers WHERE id=?", (provider_id,))
        if not r:
            return None
        rd = _row(r)
        encrypted = rd.get("api_key_encrypted", "")
        api_key = _decrypt_setting(encrypted) if encrypted else ""
        return {
            "api_key": api_key,
            "base_url": rd.get("base_url", ""),
            "provider_type": rd.get("provider_type", "openai"),
        }

    def get_default_provider_credentials(self) -> Optional[dict]:
        """Get the default provider's credentials. Falls back to legacy settings."""
        with self._read_conn() as c:
            r = c.fetchone(
                "SELECT id, base_url, api_key_encrypted, provider_type "
                "FROM llm_providers WHERE is_default=1 LIMIT 1")
        if r:
            rd = _row(r)
            encrypted = rd.get("api_key_encrypted", "")
            api_key = _decrypt_setting(encrypted) if encrypted else ""
            if api_key:
                return {
                    "api_key": api_key,
                    "base_url": rd.get("base_url", ""),
                    "provider_type": rd.get("provider_type", "openai"),
                    "provider_id": rd.get("id"),
                }
        # Fallback to legacy settings
        return None

    def update_provider(self, provider_id: str, *,
                        name: str = None, provider_type: str = None,
                        base_url: str = None, api_key: str = None,
                        is_default: bool = None) -> Optional[dict]:
        """Update a provider. Pass api_key="" to keep the existing key."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            existing = c.fetchone("SELECT * FROM llm_providers WHERE id=?",
                                  (provider_id,))
            if not existing:
                return None
            rd = _row(existing)
            if name is not None:
                rd["name"] = name
            if provider_type is not None:
                rd["provider_type"] = provider_type
            if base_url is not None:
                rd["base_url"] = base_url
            if api_key is not None and api_key != "":
                rd["api_key_encrypted"] = _encrypt_setting(api_key)
            if is_default is True:
                c.execute("UPDATE llm_providers SET is_default=0")
                rd["is_default"] = 1
            rd["updated_at"] = now
            c.execute("""UPDATE llm_providers
                SET name=?, provider_type=?, base_url=?, api_key_encrypted=?,
                    is_default=?, updated_at=?
                WHERE id=?""",
                (rd["name"], rd["provider_type"], rd["base_url"],
                 rd["api_key_encrypted"], rd["is_default"], now, provider_id))
        return self.get_provider(provider_id)

    def delete_provider(self, provider_id: str) -> bool:
        """Delete a provider. Cannot delete the last default provider."""
        with self._conn() as c:
            r = c.fetchone("SELECT is_default FROM llm_providers WHERE id=?",
                           (provider_id,))
            if not r:
                return False
            rd = _row(r)
            if rd.get("is_default"):
                # Check if there are other providers
                cnt = c.fetchone(
                    "SELECT COUNT(*) AS cnt FROM llm_providers WHERE id != ?",
                    (provider_id,))
                if _row(cnt).get("cnt", 0) > 0:
                    # Promote the oldest remaining provider to default
                    c.execute("""UPDATE llm_providers SET is_default=1
                        WHERE id = (SELECT id FROM llm_providers
                                    WHERE id != ? ORDER BY created_at ASC LIMIT 1)""",
                        (provider_id,))
            c.execute("DELETE FROM llm_providers WHERE id=?", (provider_id,))
        return True

    def migrate_legacy_provider(self) -> Optional[str]:
        """Auto-migrate legacy openai_api_key setting to a provider entry.

        Called on first provider list/access. If llm_providers table is empty
        and openai_api_key exists in settings, creates a "Default" provider.
        Returns the new provider_id or None.
        """
        with self._conn() as c:
            cnt = c.fetchone("SELECT COUNT(*) AS cnt FROM llm_providers")
            if _row(cnt).get("cnt", 0) > 0:
                return None  # Already have providers
            # Check for legacy key
            row = c.fetchone("SELECT value FROM settings WHERE key='openai_api_key'")
            if not row:
                return None
            raw_key = _row(row).get("value", "")
            if not raw_key:
                return None
            # Decrypt if needed
            decrypted = _decrypt_setting(raw_key)
            if not decrypted:
                return None
            # Get legacy base_url
            url_row = c.fetchone("SELECT value FROM settings WHERE key='openai_base_url'")
            base_url = _row(url_row).get("value", "") if url_row else ""
            # Determine provider type from base_url
            ptype = "openai"
            if base_url:
                lower = base_url.lower()
                if "openrouter" in lower:
                    ptype = "openrouter"
                elif "anthropic" in lower:
                    ptype = "anthropic"
                elif "localhost" in lower or "127.0.0.1" in lower:
                    ptype = "ollama"
            now = datetime.now(timezone.utc).isoformat()
            pid = str(uuid.uuid4())
            encrypted = _encrypt_setting(decrypted)
            c.execute("""INSERT INTO llm_providers
                (id, name, provider_type, base_url, api_key_encrypted,
                 is_default, created_at, updated_at)
                VALUES (?,?,?,?,?,1,?,?)""",
                (pid, "Default (migrated)", ptype, base_url, encrypted, now, now))
        return pid

    # ── Flywheel 1: test-case metadata ────────────────────────────────────────

    def update_test_case_metadata(
        self, tc_id: str, *,
        domain: str = "",
        industry: str = "",
        use_case_type: str = "",
        failure_mode: str = "",
        test_goal: str = "",
    ) -> None:
        """Enrich a test case with domain/use-case metadata for the generation corpus."""
        with self._conn() as c:
            c.execute(
                """UPDATE test_cases
                   SET domain=?, industry=?, use_case_type=?,
                       failure_mode=?, test_goal=?
                   WHERE id=?""",
                (domain, industry, use_case_type, failure_mode, test_goal, tc_id),
            )

    def record_test_case_performance(
        self, *,
        test_case_label: str,
        workflow_id: str,
        eval_run_id: str,
        comparison_id: str = None,
        divergence_score: float = None,
        decision_choice: str = None,
        reviewer_confidence: str = None,
    ) -> None:
        """Upsert a performance record for a (label, eval_run_id) pair.

        Called automatically from create_comparison (divergence) and
        create_decision (human choice + confidence).
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            # Try to update an existing row for this (label, eval_run_id)
            existing = c.fetchone(
                "SELECT id FROM test_case_performance WHERE test_case_label=? AND eval_run_id=?",
                (test_case_label, eval_run_id),
            )
            if existing:
                row_id = _row(existing)["id"]
                if comparison_id is not None:
                    c.execute("UPDATE test_case_performance SET comparison_id=?, divergence_score=? WHERE id=?",
                              (comparison_id, divergence_score, row_id))
                if decision_choice is not None:
                    c.execute("UPDATE test_case_performance SET decision_choice=?, reviewer_confidence=? WHERE id=?",
                              (decision_choice, reviewer_confidence, row_id))
            else:
                c.execute(
                    """INSERT INTO test_case_performance
                       (id, test_case_label, workflow_id, eval_run_id, comparison_id,
                        divergence_score, decision_choice, reviewer_confidence, recorded_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), test_case_label, workflow_id, eval_run_id,
                     comparison_id, divergence_score, decision_choice, reviewer_confidence, now),
                )

    def get_test_case_performance_stats(
        self, test_case_label: str, workflow_id: str = None
    ) -> dict:
        """Aggregate performance history for a test case label.

        Returns: avg_divergence, eval_run_count, decision_breakdown, win_rate_a, win_rate_b
        """
        filters, params = ["test_case_label=?"], [test_case_label]
        if workflow_id:
            filters.append("workflow_id=?"); params.append(workflow_id)
        where = "WHERE " + " AND ".join(filters)
        with self._conn() as c:
            rows = c.fetchall(
                f"""SELECT divergence_score, decision_choice, reviewer_confidence
                    FROM test_case_performance {where}""",
                params,
            )
        parsed = [_row(r) for r in rows]
        scores = [p["divergence_score"] for p in parsed if p["divergence_score"] is not None]
        choices = [p["decision_choice"] for p in parsed if p["decision_choice"]]
        from collections import Counter
        breakdown = dict(Counter(choices))
        total = len(choices)
        return {
            "test_case_label": test_case_label,
            "eval_run_count":  len(rows),
            "avg_divergence":  round(sum(scores) / len(scores), 4) if scores else None,
            "decision_breakdown": breakdown,
            "win_rate_a": round(breakdown.get("a_wins", 0) / total, 3) if total else None,
            "win_rate_b": round(breakdown.get("b_wins", 0) / total, 3) if total else None,
            "decision_rate": round(total / len(rows), 3) if rows else 0,
        }

    def export_test_case_corpus_jsonl(
        self,
        workflow_id: str = None,
        min_eval_runs: int = 1,
        include_performance: bool = True,
    ):
        """Export enriched test cases as JSONL for training an automated test-case generator.

        Each line:
          {label, input, domain, industry, use_case_type, failure_mode, test_goal,
           tags, performance: {avg_divergence, eval_run_count, win_rate_a, win_rate_b, decision_breakdown}}

        Only includes test cases that have been run at least min_eval_runs times.
        """
        import hashlib
        tc_filter  = "WHERE ts.workflow_id=?" if workflow_id else ""
        tc_params  = [workflow_id] if workflow_id else []

        with self._read_conn() as c:
            rows = c.fetchall(
                f"""SELECT tc.id, tc.label, tc.input_data, tc.expected_output,
                           tc.tags, tc.domain, tc.industry, tc.use_case_type,
                           tc.failure_mode, tc.test_goal, ts.workflow_id
                    FROM test_cases tc
                    JOIN test_sets ts ON tc.test_set_id = ts.id
                    {tc_filter}
                    ORDER BY tc.created_at""",
                tc_params,
            )

        # Batch-fetch performance counts to avoid N+1 queries
        perf_counts: Dict[str, int] = {}
        perf_cache: Dict[str, dict] = {}
        if include_performance:
            all_labels = list({_row(r)["label"] for r in rows})
            CHUNK = 900
            with self._read_conn() as c:
                for i in range(0, len(all_labels), CHUNK):
                    chunk = all_labels[i:i + CHUNK]
                    ph = ",".join("?" * len(chunk))
                    cnt_rows = c.fetchall(
                        f"SELECT test_case_label, COUNT(*) AS n "
                        f"FROM test_case_performance WHERE test_case_label IN ({ph}) "
                        f"GROUP BY test_case_label", chunk)
                    for cr in cnt_rows:
                        crd = _row(cr)
                        perf_counts[crd["test_case_label"]] = crd["n"]

        for row in rows:
            r = _row(row)
            label = r["label"]
            wid   = r.get("workflow_id") or workflow_id or ""

            perf = {}
            if include_performance:
                if perf_counts.get(label, 0) < min_eval_runs:
                    continue
                if label not in perf_cache:
                    perf_cache[label] = self.get_test_case_performance_stats(label, wid)
                perf = perf_cache[label]

            input_data = json.loads(r["input_data"]) if r["input_data"] else {}
            tags = json.loads(r["tags"]) if r["tags"] else []

            yield json.dumps({
                "id":            r["id"],
                "label":         label,
                "input":         input_data.get("input", input_data),
                "expected_output": r.get("expected_output") or "",
                "domain":        r.get("domain") or "",
                "industry":      r.get("industry") or "",
                "use_case_type": r.get("use_case_type") or "",
                "failure_mode":  r.get("failure_mode") or "",
                "test_goal":     r.get("test_goal") or "",
                "tags":          tags,
                "performance":   perf,
            })

    # ── Flywheel 2: reviewer profiles ─────────────────────────────────────────

    def upsert_reviewer_profile(
        self, reviewer_id: str, *,
        display_name: str = "",
        role: str = "reviewer",
        expertise_level: str = "intermediate",
        domain_expertise: list = None,
    ) -> dict:
        """Create or update a reviewer profile.

        Roles: domain_expert | ml_engineer | product_manager | end_user | reviewer
        Expertise levels: novice | intermediate | expert
        """
        now = datetime.now(timezone.utc).isoformat()
        domains_json = json.dumps(domain_expertise or [])
        with self._conn() as c:
            existing = c.fetchone(
                "SELECT reviewer_id FROM reviewer_profiles WHERE reviewer_id=?",
                (reviewer_id,),
            )
            if existing:
                c.execute(
                    """UPDATE reviewer_profiles
                       SET display_name=?, role=?, expertise_level=?,
                           domain_expertise=?, updated_at=?
                       WHERE reviewer_id=?""",
                    (display_name, role, expertise_level, domains_json, now, reviewer_id),
                )
            else:
                c.execute(
                    """INSERT INTO reviewer_profiles
                       (reviewer_id, display_name, role, expertise_level,
                        domain_expertise, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (reviewer_id, display_name, role, expertise_level,
                     domains_json, now, now),
                )
        return self.get_reviewer_profile(reviewer_id)

    def get_reviewer_profile(self, reviewer_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.fetchone(
                "SELECT * FROM reviewer_profiles WHERE reviewer_id=?", (reviewer_id,)
            )
        if not row:
            return None
        r = _row(row)
        return {
            "reviewer_id":     r["reviewer_id"],
            "display_name":    r.get("display_name") or "",
            "role":            r.get("role") or "reviewer",
            "expertise_level": r.get("expertise_level") or "intermediate",
            "domain_expertise": json.loads(r.get("domain_expertise") or "[]"),
            "created_at":      r.get("created_at") or "",
            "updated_at":      r.get("updated_at") or "",
        }

    # ── Flywheel 2: data consent ───────────────────────────────────────────────

    def grant_consent(
        self, *,
        scope: str = "global",
        workflow_id: str = None,
        consent_type: str,
        granted_by: str,
        notes: str = "",
        expires_at: str = None,
    ) -> dict:
        """Record that an organisation has opted in to a specific type of data sharing."""
        now = datetime.now(timezone.utc).isoformat()
        cid = str(uuid.uuid4())
        with self._conn() as c:
            c.execute(
                """INSERT INTO data_consent
                   (id, scope, workflow_id, consent_type, granted_by,
                    granted_at, expires_at, is_active, notes)
                   VALUES (?,?,?,?,?,?,?,1,?)""",
                (cid, scope, workflow_id, consent_type, granted_by,
                 now, expires_at, notes),
            )
        return self.get_consent(cid)

    def get_consent(self, consent_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.fetchone("SELECT * FROM data_consent WHERE id=?", (consent_id,))
        return _row(row) if row else None

    def list_consents(self, workflow_id: str = None, active_only: bool = True) -> List[dict]:
        conditions, params = [], []
        if active_only:
            conditions.append("is_active=1")
        if workflow_id:
            conditions.append("(workflow_id=? OR scope='global')")
            params.append(workflow_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        with self._conn() as c:
            rows = c.fetchall(
                f"SELECT * FROM data_consent {where} ORDER BY granted_at DESC", params
            )
        now_iso = datetime.now(timezone.utc).isoformat()
        result = []
        for row in rows:
            r = _row(row)
            # Treat expired consents as inactive
            if r.get("expires_at") and r["expires_at"] < now_iso:
                continue
            result.append(r)
        return result

    def revoke_consent(self, consent_id: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE data_consent SET is_active=0 WHERE id=?", (consent_id,))

    def has_consent(self, workflow_id: str, consent_type: str) -> bool:
        """Return True if an active, unexpired consent record covers this workflow."""
        consents = self.list_consents(workflow_id=workflow_id, active_only=True)
        return any(r["consent_type"] == consent_type for r in consents)

    # ── Flywheel 2: preference corpus export ──────────────────────────────────

    def export_preference_corpus_jsonl(
        self,
        workflow_id: str = None,
        eval_run_id: str = None,
        anonymize: bool = True,
        require_consent: bool = True,
    ):
        """Export the full preference corpus as JSONL for B2B data licensing.

        Richer than export_dpo_jsonl — includes reviewer metadata, confidence,
        structured rationale, divergence score, and data category.

        Each line:
          {
            prompt, chosen, rejected,
            rationale_for_choice, rationale_for_rejection,
            confidence, tags, data_category, divergence_score,
            reviewer: {role, expertise_level, domain_expertise},
            provenance_hash  (anonymized cross-record key),
          }

        anonymize=True: replaces raw prompt text with provenance_hash.
        require_consent=True: skips workflows without an active data_consent record.
        """
        import hashlib

        filters = ["d.choice IN ('A', 'B')"]
        params: list = []
        if workflow_id:
            filters.append("d.workflow_id=?"); params.append(workflow_id)
        if eval_run_id:
            filters.append("d.eval_run_id=?"); params.append(eval_run_id)
        filters.append("d.branch_winner_id IS NOT NULL")
        where = "WHERE " + " AND ".join(filters)

        with self._read_conn() as c:
            rows = c.fetchall(
                f"""SELECT d.*, r.input_data AS run_input
                    FROM decisions d
                    LEFT JOIN workflow_runs r ON r.id = d.run_id
                    {where}
                    ORDER BY d.created_at DESC""",
                params,
            )

        # Parse decisions and collect branch IDs for bulk fetch
        parsed_rows = [_row(row) for row in rows]
        branch_ids = set()
        for d in parsed_rows:
            if d.get("branch_winner_id"):
                branch_ids.add(d["branch_winner_id"])
            if d.get("branch_loser_id"):
                branch_ids.add(d["branch_loser_id"])
        steps_by_branch = self.get_step_outputs_bulk(list(branch_ids))

        # Batch consent check — one query per workflow, cached
        consent_cache: Dict[str, bool] = {}
        # Pre-load reviewer profiles (batch)
        reviewer_cache: dict = {}

        for d in parsed_rows:
            # Consent check — skip if require_consent and no active consent
            if require_consent:
                wid = d.get("workflow_id") or ""
                if wid not in consent_cache:
                    consent_cache[wid] = self.has_consent(wid, "training_data")
                if not consent_cache[wid]:
                    continue

            # Build chosen/rejected text from bulk-fetched step outputs
            winner_steps = steps_by_branch.get(d.get("branch_winner_id", ""), [])
            loser_steps = steps_by_branch.get(d.get("branch_loser_id", ""), [])
            d["chosen_text"] = " ".join(s.output_text for s in winner_steps if s.output_text)
            d["rejected_text"] = " ".join(s.output_text for s in loser_steps if s.output_text)

            # Reviewer profile
            rid = d.get("reviewer_id") or ""
            if rid not in reviewer_cache:
                reviewer_cache[rid] = self.get_reviewer_profile(rid) or {}
            rp = reviewer_cache[rid]

            # Prompt text
            raw_input = d.get("run_input") or ""
            try:
                raw_input = json.loads(raw_input).get("input", raw_input)
            except Exception:
                pass

            # Provenance hash — deterministic across records, never exposes raw text
            ph = d.get("provenance_hash") or ""
            if not ph:
                ph = hashlib.sha256(
                    f"{d.get('workflow_id','')}:{d.get('test_case_label','')}:{str(raw_input)[:200]}"
                    .encode()
                ).hexdigest()

            yield json.dumps({
                "provenance_hash":        ph,
                "prompt":                 ph if anonymize else raw_input,
                "chosen":                 d.get("chosen_text") or "",
                "rejected":               d.get("rejected_text") or "",
                "rationale_for_choice":   d.get("rationale_for_choice") or "",
                "rationale_for_rejection": d.get("rationale_for_rejection") or "",
                "confidence":             d.get("confidence") or "",
                "tags":                   json.loads(d.get("tags") or "[]"),
                "data_category":          d.get("data_category") or "",
                "divergence_score":       d.get("divergence_score"),
                "reviewer": {
                    "role":             rp.get("role") or "reviewer",
                    "expertise_level":  rp.get("expertise_level") or "intermediate",
                    "domain_expertise": rp.get("domain_expertise") or [],
                },
            })

    # ── Collaboration: comments ─────────────────────────────────────────────

    def add_comment(self, comparison_id: str, author_id: str, body: str,
                    author_name: str = "", parent_id: str = None) -> dict:
        """Add a comment to a comparison. Supports threading via parent_id."""
        cid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT INTO comments
                   (id, comparison_id, author_id, author_name, body, parent_id,
                    created_at, updated_at, is_resolved)
                   VALUES (?,?,?,?,?,?,?,?,0)""",
                (cid, comparison_id, author_id, author_name, body, parent_id,
                 now, now),
            )
        return self.get_comment(cid)

    def get_comment(self, comment_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.fetchone("SELECT * FROM comments WHERE id=?", (comment_id,))
        return _row(row) if row else None

    def list_comments(self, comparison_id: str) -> List[dict]:
        """List all comments for a comparison, ordered chronologically."""
        with self._conn() as c:
            rows = c.fetchall(
                "SELECT * FROM comments WHERE comparison_id=? ORDER BY created_at ASC",
                (comparison_id,),
            )
        return [_row(r) for r in rows]

    def update_comment(self, comment_id: str, body: str = None,
                       is_resolved: bool = None) -> Optional[dict]:
        """Update a comment body or resolve status."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            if body is not None:
                c.execute("UPDATE comments SET body=?, updated_at=? WHERE id=?",
                          (body, now, comment_id))
            if is_resolved is not None:
                c.execute("UPDATE comments SET is_resolved=?, updated_at=? WHERE id=?",
                          (1 if is_resolved else 0, now, comment_id))
        return self.get_comment(comment_id)

    def delete_comment(self, comment_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM comments WHERE id=?", (comment_id,))

    # ── Collaboration: review assignments ───────────────────────────────────

    def assign_review(self, eval_run_id: str, comparison_id: str,
                      reviewer_id: str, assigned_by: str = "",
                      notes: str = "") -> dict:
        """Assign a comparison to a reviewer."""
        aid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT INTO review_assignments
                   (id, eval_run_id, comparison_id, reviewer_id, assigned_by,
                    status, assigned_at, notes)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (aid, eval_run_id, comparison_id, reviewer_id, assigned_by,
                 "pending", now, notes),
            )
            # Update comparison status
            c.execute(
                "UPDATE comparisons SET review_status='assigned', assigned_to=? WHERE id=?",
                (reviewer_id, comparison_id),
            )
        return self.get_assignment(aid)

    def get_assignment(self, assignment_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.fetchone("SELECT * FROM review_assignments WHERE id=?",
                             (assignment_id,))
        return _row(row) if row else None

    def list_assignments(self, eval_run_id: str = None,
                         reviewer_id: str = None,
                         status: str = None) -> List[dict]:
        """List review assignments with optional filters."""
        conditions, params = [], []
        if eval_run_id:
            conditions.append("eval_run_id=?"); params.append(eval_run_id)
        if reviewer_id:
            conditions.append("reviewer_id=?"); params.append(reviewer_id)
        if status:
            conditions.append("status=?"); params.append(status)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        with self._conn() as c:
            rows = c.fetchall(
                f"SELECT * FROM review_assignments {where} ORDER BY assigned_at DESC",
                params,
            )
        return [_row(r) for r in rows]

    def update_assignment_status(self, assignment_id: str, status: str,
                                 notes: str = None) -> Optional[dict]:
        """Update assignment status: pending → in_review → completed / skipped."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            updates = ["status=?"]
            params = [status]
            if status in ("completed", "skipped"):
                updates.append("completed_at=?")
                params.append(now)
            if notes is not None:
                updates.append("notes=?")
                params.append(notes)
            params.append(assignment_id)
            c.execute(
                f"UPDATE review_assignments SET {', '.join(updates)} WHERE id=?",
                params,
            )
            # Sync comparison review_status (inline read to avoid nested lock)
            row = c.fetchone("SELECT * FROM review_assignments WHERE id=?",
                             (assignment_id,))
            if row:
                comp_id = _row(row)["comparison_id"]
                comp_status = "reviewed" if status == "completed" else status
                c.execute(
                    "UPDATE comparisons SET review_status=? WHERE id=?",
                    (comp_status, comp_id),
                )
        return self.get_assignment(assignment_id)

    def bulk_assign_reviews(self, eval_run_id: str, reviewer_ids: List[str],
                            assigned_by: str = "") -> List[dict]:
        """Round-robin assign all unassigned comparisons in an eval run to reviewers."""
        with self._conn() as c:
            rows = c.fetchall(
                "SELECT id FROM comparisons WHERE eval_run_id=? AND review_status='pending'",
                (eval_run_id,),
            )
        comp_ids = [_row(r)["id"] for r in rows]
        if not comp_ids or not reviewer_ids:
            return []

        assignments = []
        for i, comp_id in enumerate(comp_ids):
            reviewer = reviewer_ids[i % len(reviewer_ids)]
            a = self.assign_review(eval_run_id, comp_id, reviewer, assigned_by)
            if a:
                assignments.append(a)
        return assignments

    def get_review_queue(self, reviewer_id: str) -> List[dict]:
        """Get a reviewer's pending queue with comparison details."""
        with self._conn() as c:
            rows = c.fetchall(
                """SELECT ra.*, c.divergence_score, c.eval_run_id AS comp_eval_run_id
                   FROM review_assignments ra
                   JOIN comparisons c ON c.id = ra.comparison_id
                   WHERE ra.reviewer_id=? AND ra.status IN ('pending', 'in_review')
                   ORDER BY c.divergence_score DESC""",
                (reviewer_id,),
            )
        return [_row(r) for r in rows]

    def get_review_stats(self, eval_run_id: str) -> dict:
        """Get review progress stats for an eval run."""
        with self._conn() as c:
            total = c.fetchone(
                "SELECT COUNT(*) as cnt FROM comparisons WHERE eval_run_id=?",
                (eval_run_id,),
            )
            reviewed = c.fetchone(
                "SELECT COUNT(*) as cnt FROM comparisons WHERE eval_run_id=? AND review_status='reviewed'",
                (eval_run_id,),
            )
            assigned = c.fetchone(
                "SELECT COUNT(*) as cnt FROM comparisons WHERE eval_run_id=? AND review_status='assigned'",
                (eval_run_id,),
            )
            pending = c.fetchone(
                "SELECT COUNT(*) as cnt FROM comparisons WHERE eval_run_id=? AND review_status='pending'",
                (eval_run_id,),
            )
        return {
            "total": _row(total)["cnt"] if total else 0,
            "reviewed": _row(reviewed)["cnt"] if reviewed else 0,
            "assigned": _row(assigned)["cnt"] if assigned else 0,
            "pending": _row(pending)["cnt"] if pending else 0,
        }

    # ── Agent comparison CRUD ────────────────────────────────────────────────

    def create_trace_event(self, **kw) -> None:
        """Insert a single trace event."""
        from core.agent_models import TraceEvent
        kw.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        for json_field in ("input_data", "output_data", "metadata"):
            if json_field in kw and isinstance(kw[json_field], dict):
                kw[json_field] = json.dumps(kw[json_field])
        cols = ", ".join(kw.keys())
        placeholders = ", ".join("?" for _ in kw)
        with self._conn() as c:
            c.execute(
                f"INSERT INTO trace_events ({cols}) VALUES ({placeholders})",
                tuple(kw.values()),
            )

    def create_trace_events_batch(self, events: List[dict]) -> None:
        """Bulk-insert trace events."""
        if not events:
            return
        for ev in events:
            ev.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            for json_field in ("input_data", "output_data", "metadata"):
                if json_field in ev and isinstance(ev[json_field], dict):
                    ev[json_field] = json.dumps(ev[json_field])
        cols = sorted(events[0].keys())
        placeholders = ", ".join("?" for _ in cols)
        col_str = ", ".join(cols)
        with self._conn() as c:
            for ev in events:
                vals = tuple(ev.get(k) for k in cols)
                c.execute(
                    f"INSERT INTO trace_events ({col_str}) VALUES ({placeholders})",
                    vals,
                )

    def get_trace_events(self, branch_id: str = None, run_id: str = None,
                         parent_event_id: str = "__UNSET__") -> list:
        """Retrieve trace events with flexible filtering.

        Parameters
        ----------
        branch_id : str, optional
            Filter by branch.
        run_id : str, optional
            Filter by workflow run.
        parent_event_id : str
            Filter by parent. Pass None to get root events only.
            Pass "__UNSET__" (default) to skip this filter.
        """
        from core.agent_models import TraceEvent
        clauses, params = [], []
        if branch_id:
            clauses.append("branch_id = ?")
            params.append(branch_id)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if parent_event_id != "__UNSET__":
            if parent_event_id is None:
                clauses.append("parent_event_id IS NULL")
            else:
                clauses.append("parent_event_id = ?")
                params.append(parent_event_id)
        where = " AND ".join(clauses) if clauses else "1=1"
        with self._read_conn() as c:
            rows = c.fetchall(
                f"SELECT * FROM trace_events WHERE {where} ORDER BY event_index",
                tuple(params),
            )
        return [TraceEvent.from_row(_row(r)) for r in rows]

    def create_trajectory_outcome(self, **kw) -> None:
        """Insert a trajectory outcome record."""
        kw.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        for json_field in ("tool_sequence_detail", "outcome_detail", "efficiency_detail"):
            if json_field in kw and isinstance(kw[json_field], dict):
                kw[json_field] = json.dumps(kw[json_field])
        cols = ", ".join(kw.keys())
        placeholders = ", ".join("?" for _ in kw)
        with self._conn() as c:
            c.execute(
                f"INSERT INTO trajectory_outcomes ({cols}) VALUES ({placeholders})",
                tuple(kw.values()),
            )

    def get_trajectory_outcomes(self, comparison_id: str = None,
                                 workflow_id: str = None,
                                 run_id: str = None) -> list:
        """Retrieve trajectory outcomes with flexible filtering."""
        from core.agent_models import TrajectoryOutcome
        clauses, params = [], []
        if comparison_id:
            clauses.append("comparison_id = ?")
            params.append(comparison_id)
        if workflow_id:
            clauses.append("workflow_id = ?")
            params.append(workflow_id)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        where = " AND ".join(clauses) if clauses else "1=1"
        with self._read_conn() as c:
            rows = c.fetchall(
                f"SELECT * FROM trajectory_outcomes WHERE {where} ORDER BY created_at DESC",
                tuple(params),
            )
        return [TrajectoryOutcome.from_row(_row(r)) for r in rows]
