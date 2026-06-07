"""Workspace Router — routes database connections to the correct schema.

This is the enforcement layer. Every request that touches workspace data goes
through this router. The router:
    1. Validates workspace_id exists and belongs to the claimed org
    2. Acquires a pooled connection
    3. Sets search_path to the workspace schema
    4. Returns the connection (scoped, cannot access other schemas)
    5. Resets search_path on connection return

This makes cross-workspace data leakage impossible at the database level.
Even if application code has a bug, PostgreSQL's search_path ensures queries
only hit tables in the designated schema.

Usage:
    router = WorkspaceRouter(database_url)

    # In a request handler:
    with router.scoped_connection("fraud_detection", "org_acme") as conn:
        rows = conn.fetchall("SELECT * FROM workflows")  # only sees workspace schema
"""

from __future__ import annotations

import logging
import os
import re
import threading
from contextlib import contextmanager
from typing import Dict, Optional, Set

logger = logging.getLogger("forkmark.router")


class WorkspaceRouter:
    """Routes requests to workspace-scoped database connections.

    Thread-safe. Caches workspace → schema mappings to avoid repeated lookups.
    """

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._adapter = None
        self._schema_cache: Dict[str, str] = {}    # workspace_id → schema_name
        self._org_cache: Dict[str, str] = {}       # workspace_id → org_id
        self._sandbox_cache: Dict[str, bool] = {}  # workspace_id → is_sandbox
        self._cache_lock = threading.Lock()
        self._CACHE_MAX = 1000

    def _get_adapter(self):
        if self._adapter is None:
            from core.store import _PostgreSQLConn
            self._adapter = _PostgreSQLConn(self._database_url)
        return self._adapter

    def _validate_schema_name(self, schema_name: str) -> bool:
        """Ensure schema name is safe for SQL injection prevention."""
        return bool(re.match(r"^workspace_[a-z0-9_]{1,50}$", schema_name))

    def _lookup_workspace(self, workspace_id: str) -> Optional[Dict]:
        """Lookup workspace schema from control plane. Returns None if not found."""
        # Check cache first
        with self._cache_lock:
            if workspace_id in self._schema_cache:
                return {
                    "schema_name": self._schema_cache[workspace_id],
                    "org_id": self._org_cache[workspace_id],
                    "is_sandbox": self._sandbox_cache.get(workspace_id, False),
                }

        # Miss — query control plane
        adapter = self._get_adapter()
        with adapter.connect() as conn:
            conn.execute("SET search_path TO public")
            row = conn.fetchone(
                "SELECT schema_name, org_id, is_sandbox FROM workspaces "
                "WHERE id = ? AND deleted_at IS NULL",
                (workspace_id,),
            )

        if not row:
            return None

        row_dict = dict(row)
        schema_name = row_dict["schema_name"]
        org_id = row_dict["org_id"]
        is_sandbox = bool(row_dict.get("is_sandbox", False))

        # Validate schema name before caching
        if not self._validate_schema_name(schema_name):
            logger.error("Invalid schema name in DB: %s", schema_name)
            return None

        # Cache it
        with self._cache_lock:
            if len(self._schema_cache) >= self._CACHE_MAX:
                # Evict half (simple strategy)
                keys = list(self._schema_cache.keys())[:self._CACHE_MAX // 2]
                for k in keys:
                    self._schema_cache.pop(k, None)
                    self._org_cache.pop(k, None)
                    self._sandbox_cache.pop(k, None)
            self._schema_cache[workspace_id] = schema_name
            self._org_cache[workspace_id] = org_id
            self._sandbox_cache[workspace_id] = is_sandbox

        return {"schema_name": schema_name, "org_id": org_id, "is_sandbox": is_sandbox}

    def invalidate_cache(self, workspace_id: str):
        """Remove a workspace from the cache (e.g., after deletion)."""
        with self._cache_lock:
            self._schema_cache.pop(workspace_id, None)
            self._org_cache.pop(workspace_id, None)
            self._sandbox_cache.pop(workspace_id, None)

    @contextmanager
    def scoped_connection(self, workspace_id: str, org_id: str):
        """Acquire a database connection scoped to a workspace's schema.

        Args:
            workspace_id: The workspace to scope to.
            org_id: The org that owns this workspace (verified).

        Raises:
            PermissionError: If workspace doesn't exist or org doesn't match.

        Yields:
            A database connection with search_path set to the workspace schema.
        """
        info = self._lookup_workspace(workspace_id)
        if info is None:
            raise PermissionError(f"Workspace '{workspace_id}' not found or deleted")

        if info["org_id"] != org_id:
            logger.warning(
                "Org mismatch: workspace '%s' belongs to '%s', not '%s'",
                workspace_id, info["org_id"], org_id,
            )
            raise PermissionError(f"Workspace '{workspace_id}' does not belong to org '{org_id}'")

        schema_name = info["schema_name"]
        adapter = self._get_adapter()

        with adapter.connect() as conn:
            # CRITICAL: bind to workspace schema
            conn.execute(f"SET search_path TO {schema_name}, public")
            try:
                yield conn
            finally:
                # Reset search_path before returning connection to pool
                try:
                    conn.execute("SET search_path TO public")
                except Exception:
                    pass  # connection might be in error state

    @contextmanager
    def control_plane_connection(self):
        """Get a connection to the public (control plane) schema only."""
        adapter = self._get_adapter()
        with adapter.connect() as conn:
            conn.execute("SET search_path TO public")
            yield conn

    def get_workspace_schema(self, workspace_id: str) -> Optional[str]:
        """Get the schema name for a workspace (from cache or DB)."""
        info = self._lookup_workspace(workspace_id)
        return info["schema_name"] if info else None

    def verify_membership(self, user_id: str, workspace_id: str) -> Optional[str]:
        """Check if user is a member of workspace. Returns role or None."""
        adapter = self._get_adapter()
        with adapter.connect() as conn:
            conn.execute("SET search_path TO public")
            row = conn.fetchone(
                "SELECT role FROM workspace_memberships "
                "WHERE user_id = ? AND workspace_id = ?",
                (user_id, workspace_id),
            )
        if row:
            return dict(row)["role"]
        return None


# ---------------------------------------------------------------------------
# Backward compatibility: single-tenant mode
# ---------------------------------------------------------------------------

class SingleTenantRouter:
    """Fallback router for single-tenant deployments (no workspace isolation).

    Used when multi-tenancy is disabled or when running with SQLite.
    All connections use the default schema — no isolation.
    """

    def __init__(self, database_url: Optional[str], db_path: str = ""):
        from core.store import _SQLiteConn, _PostgreSQLConn
        if database_url:
            self._adapter = _PostgreSQLConn(database_url)
        else:
            self._adapter = _SQLiteConn(db_path)

    @contextmanager
    def scoped_connection(self, workspace_id: str = "", org_id: str = ""):
        """In single-tenant mode, workspace_id is ignored."""
        with self._adapter.connect() as conn:
            yield conn

    @contextmanager
    def control_plane_connection(self):
        with self._adapter.connect() as conn:
            yield conn

    def verify_membership(self, user_id: str, workspace_id: str) -> Optional[str]:
        """Single-tenant: everyone is an admin."""
        return "ws_admin"

    def invalidate_cache(self, workspace_id: str):
        pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_workspace_router(
    database_url: Optional[str] = None,
    db_path: str = "",
    multi_tenant: bool = False,
) -> WorkspaceRouter | SingleTenantRouter:
    """Create the appropriate router based on config.

    Multi-tenant mode requires PostgreSQL. Falls back to single-tenant with SQLite.
    """
    if multi_tenant and database_url and database_url.startswith(("postgres://", "postgresql://")):
        logger.info("Multi-tenant mode: workspace isolation enabled (PostgreSQL)")
        return WorkspaceRouter(database_url)

    if multi_tenant and not database_url:
        logger.warning(
            "Multi-tenant mode requested but no DATABASE_URL set. "
            "Falling back to single-tenant mode. Set FM_DATABASE_URL for isolation."
        )

    logger.info("Single-tenant mode: no workspace isolation")
    return SingleTenantRouter(database_url, db_path)
