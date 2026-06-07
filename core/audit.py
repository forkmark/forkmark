"""Enterprise audit log — immutable, queryable, exportable.

Every security-relevant action is logged:
    - Authentication events (login, key creation, key revocation)
    - Authorization events (permission denied, role changes)
    - Data access (workspace access, export, DPO export)
    - Provisioning (workspace create/delete, user add/remove)
    - Configuration changes (settings, evaluator config)

Storage: PostgreSQL audit_log table (control plane schema).
Retention: configurable per-org (default 90 days, enterprise unlimited).
Export: CSV/JSON for compliance teams.

Usage:
    from core.audit import AuditLogger, AuditAction

    audit = AuditLogger(router)
    audit.log(
        org_id="org_acme",
        action=AuditAction.WORKSPACE_CREATED,
        user_id="user_123",
        workspace_id="ws_456",
        details={"name": "fraud-detection"},
        ip_address=request.client.host,
    )

    # Query:
    entries = audit.query(org_id="org_acme", action="workspace.*", limit=50)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("forkmark.audit")


# ---------------------------------------------------------------------------
# Audit actions
# ---------------------------------------------------------------------------

class AuditAction(str, Enum):
    # Auth
    LOGIN_SUCCESS = "auth.login_success"
    LOGIN_FAILED = "auth.login_failed"
    KEY_CREATED = "auth.key_created"
    KEY_REVOKED = "auth.key_revoked"
    DEVICE_FLOW_STARTED = "auth.device_flow_started"
    DEVICE_FLOW_APPROVED = "auth.device_flow_approved"

    # Workspace lifecycle
    WORKSPACE_CREATED = "workspace.created"
    WORKSPACE_DELETED = "workspace.deleted"
    WORKSPACE_ARCHIVED = "workspace.archived"

    # Membership
    MEMBER_ADDED = "membership.added"
    MEMBER_REMOVED = "membership.removed"
    ROLE_CHANGED = "membership.role_changed"

    # Data operations
    WORKFLOW_CREATED = "workflow.created"
    WORKFLOW_DELETED = "workflow.deleted"
    RUN_STARTED = "run.started"
    COMPARISON_CREATED = "comparison.created"
    DECISION_MADE = "decision.made"
    EXPORT_DOWNLOADED = "export.downloaded"
    DPO_EXPORTED = "export.dpo"

    # Settings
    SETTINGS_CHANGED = "settings.changed"
    EVALUATOR_CONFIG_CHANGED = "settings.evaluator_changed"

    # SCIM provisioning
    SCIM_USER_PROVISIONED = "scim.user_provisioned"
    SCIM_USER_DEACTIVATED = "scim.user_deactivated"
    SCIM_GROUP_CREATED = "scim.group_created"
    SCIM_GROUP_DELETED = "scim.group_deleted"


# ---------------------------------------------------------------------------
# Audit entry
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    """Single audit log entry."""
    id: Optional[int] = None
    timestamp: Optional[str] = None
    org_id: str = ""
    workspace_id: str = ""
    user_id: str = ""
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    details: Optional[Dict[str, Any]] = None
    ip_address: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details,
            "ip_address": self.ip_address,
        }


# ---------------------------------------------------------------------------
# Audit Logger
# ---------------------------------------------------------------------------

class AuditLogger:
    """Writes and queries audit log entries."""

    def __init__(self, workspace_router):
        self._router = workspace_router

    def log(
        self,
        org_id: str,
        action: str | AuditAction,
        user_id: str = "",
        workspace_id: str = "",
        resource_type: str = "",
        resource_id: str = "",
        details: Optional[Dict[str, Any]] = None,
        ip_address: str = "",
    ):
        """Write an audit entry. Non-blocking — failures are logged but don't raise."""
        action_str = action.value if isinstance(action, AuditAction) else action

        try:
            with self._router.control_plane_connection() as conn:
                conn.execute(
                    "INSERT INTO audit_log "
                    "(org_id, workspace_id, user_id, action, resource_type, "
                    "resource_id, details_json, ip_address) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        org_id,
                        workspace_id,
                        user_id,
                        action_str,
                        resource_type,
                        resource_id,
                        json.dumps(details) if details else None,
                        ip_address,
                    ),
                )
        except Exception as e:
            logger.error("Failed to write audit log: %s", e)

    def query(
        self,
        org_id: str,
        workspace_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEntry]:
        """Query audit log with filters.

        Args:
            action: Exact match or prefix with wildcard (e.g., "workspace.*")
        """
        conditions = ["org_id = ?"]
        params: list = [org_id]

        if workspace_id:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)

        if action:
            if action.endswith(".*"):
                prefix = action[:-2]
                conditions.append("action LIKE ?")
                params.append(f"{prefix}.%")
            else:
                conditions.append("action = ?")
                params.append(action)

        if since:
            conditions.append("timestamp >= ?")
            params.append(since.isoformat())

        if until:
            conditions.append("timestamp <= ?")
            params.append(until.isoformat())

        where_clause = " AND ".join(conditions)
        sql = (
            f"SELECT id, timestamp, org_id, workspace_id, user_id, action, "
            f"resource_type, resource_id, details_json, ip_address "
            f"FROM audit_log WHERE {where_clause} "
            f"ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])

        try:
            with self._router.control_plane_connection() as conn:
                conn.execute("SET search_path TO public")
                rows = conn.fetchall(sql, tuple(params))

            entries = []
            for row in rows:
                r = dict(row)
                entries.append(AuditEntry(
                    id=r.get("id"),
                    timestamp=str(r.get("timestamp", "")),
                    org_id=r.get("org_id", ""),
                    workspace_id=r.get("workspace_id", ""),
                    user_id=r.get("user_id", ""),
                    action=r.get("action", ""),
                    resource_type=r.get("resource_type", ""),
                    resource_id=r.get("resource_id", ""),
                    details=json.loads(r["details_json"]) if r.get("details_json") else None,
                    ip_address=r.get("ip_address", ""),
                ))
            return entries
        except Exception as e:
            logger.error("Audit query failed: %s", e)
            return []

    def count(self, org_id: str, since: Optional[datetime] = None) -> int:
        """Count audit entries for an org (for pagination)."""
        conditions = ["org_id = ?"]
        params: list = [org_id]
        if since:
            conditions.append("timestamp >= ?")
            params.append(since.isoformat())

        where_clause = " AND ".join(conditions)
        try:
            with self._router.control_plane_connection() as conn:
                conn.execute("SET search_path TO public")
                row = conn.fetchone(
                    f"SELECT COUNT(*) as cnt FROM audit_log WHERE {where_clause}",
                    tuple(params),
                )
            return dict(row)["cnt"] if row else 0
        except Exception:
            return 0

    def export_csv(self, org_id: str, since: datetime, until: datetime) -> str:
        """Export audit log entries as CSV string."""
        import csv
        import io

        entries = self.query(org_id=org_id, since=since, until=until, limit=10000)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "timestamp", "user_id", "workspace_id", "action",
            "resource_type", "resource_id", "details", "ip_address"
        ])
        for e in entries:
            writer.writerow([
                e.timestamp, e.user_id, e.workspace_id, e.action,
                e.resource_type, e.resource_id,
                json.dumps(e.details) if e.details else "",
                e.ip_address,
            ])

        return output.getvalue()

    def purge_old(self, org_id: str, retention_days: int = 90) -> int:
        """Purge audit entries older than retention period. Returns count deleted."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        try:
            with self._router.control_plane_connection() as conn:
                conn.execute("SET search_path TO public")
                conn.execute(
                    "DELETE FROM audit_log WHERE org_id = ? AND timestamp < ?",
                    (org_id, cutoff.isoformat()),
                )
                # Return affected rows (implementation-dependent)
                return 0  # placeholder — psycopg2 needs cursor.rowcount
        except Exception as e:
            logger.error("Audit purge failed: %s", e)
            return 0
