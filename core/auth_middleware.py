"""Tenant-aware authentication middleware for Forkmark API.

Provides FastAPI dependencies that:
    1. Authenticate the request (API key or JWT)
    2. Resolve the workspace from the URL path
    3. Verify the user belongs to that workspace
    4. Inject a WorkspaceContext with a scoped DB connection

Usage in endpoints:
    @app.get("/api/workspaces/{workspace_id}/workflows")
    async def list_workflows(ctx: WorkspaceContext = Depends(get_workspace_context)):
        with ctx.connect(router._get_adapter()) as conn:
            ...

Backward compatibility:
    When multi-tenancy is disabled (single-tenant mode), the middleware passes
    through without workspace checks. Existing endpoints continue to work.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set

from fastapi import Depends, Header, HTTPException, Path, Request

logger = logging.getLogger("forkmark.auth")


# ---------------------------------------------------------------------------
# Roles and Permissions
# ---------------------------------------------------------------------------

class Role(str, Enum):
    ORG_ADMIN = "org_admin"
    WS_ADMIN = "ws_admin"
    EVALUATOR = "evaluator"
    VIEWER = "viewer"
    SDK_ONLY = "sdk_only"


class Permission(str, Enum):
    WORKSPACE_CREATE = "workspace:create"
    WORKSPACE_DELETE = "workspace:delete"
    WORKSPACE_MANAGE_MEMBERS = "workspace:manage_members"
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_DELETE = "workflow:delete"
    RUN_CREATE = "run:create"
    DECISION_CREATE = "decision:create"
    EXPORT_READ = "export:read"
    EXPORT_DPO = "export:dpo"
    SETTINGS_WRITE = "settings:write"
    KEY_MANAGE = "key:manage"


ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.ORG_ADMIN: set(Permission),  # all permissions
    Role.WS_ADMIN: {
        Permission.WORKSPACE_MANAGE_MEMBERS,
        Permission.WORKFLOW_CREATE, Permission.WORKFLOW_READ, Permission.WORKFLOW_DELETE,
        Permission.RUN_CREATE, Permission.DECISION_CREATE,
        Permission.EXPORT_READ, Permission.EXPORT_DPO,
        Permission.SETTINGS_WRITE, Permission.KEY_MANAGE,
    },
    Role.EVALUATOR: {
        Permission.WORKFLOW_READ, Permission.RUN_CREATE,
        Permission.DECISION_CREATE, Permission.EXPORT_READ,
    },
    Role.VIEWER: {
        Permission.WORKFLOW_READ, Permission.EXPORT_READ,
    },
    Role.SDK_ONLY: {
        Permission.WORKFLOW_READ, Permission.RUN_CREATE,
    },
}

# Sandbox restrictions: these operations are blocked in sandbox workspaces
SANDBOX_BLOCKED: Set[Permission] = {
    Permission.EXPORT_DPO,
    Permission.DECISION_CREATE,
    Permission.WORKFLOW_DELETE,
}


# ---------------------------------------------------------------------------
# Authenticated User model
# ---------------------------------------------------------------------------

@dataclass
class AuthenticatedUser:
    """Represents the authenticated caller (from API key or JWT)."""
    user_id: str
    org_id: str
    workspace_ids: list[str]       # workspaces this user belongs to
    key_workspace_id: Optional[str] = None  # if using a workspace-scoped key
    auth_method: str = "api_key"   # "api_key" | "jwt" | "ci_token"


# ---------------------------------------------------------------------------
# Dependencies for FastAPI
# ---------------------------------------------------------------------------

def check_permission(required: Permission):
    """Factory: create a dependency that checks a specific permission."""

    async def _checker(
        workspace_id: str = Path(...),
        request: Request = None,
    ):
        # Get the workspace router from app state
        router = request.app.state.workspace_router
        ctx = request.state.workspace_context if hasattr(request.state, "workspace_context") else None

        if ctx is None:
            raise HTTPException(401, "Authentication required")

        # Check role has permission
        try:
            role = Role(ctx.role)
        except ValueError:
            raise HTTPException(403, f"Unknown role: {ctx.role}")

        role_perms = ROLE_PERMISSIONS.get(role, set())
        if required not in role_perms:
            raise HTTPException(
                403,
                f"Role '{ctx.role}' lacks permission '{required.value}' "
                f"in workspace '{ctx.workspace_id}'"
            )

        # Check sandbox restrictions
        if ctx.is_sandbox and required in SANDBOX_BLOCKED:
            raise HTTPException(
                403,
                {
                    "error": "sandbox_restricted",
                    "message": f"Operation '{required.value}' is not available in sandbox workspaces. "
                               "Ask your IT admin to create a proper workspace via SCIM.",
                    "docs": "https://docs.forkmark.dev/setup/scim",
                }
            )

        return ctx

    return Depends(_checker)


async def get_workspace_context(
    workspace_id: str = Path(...),
    request: Request = None,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Main dependency: authenticate + resolve workspace + verify membership.

    Attaches WorkspaceContext to request.state for downstream use.
    """
    from core.multitenancy import WorkspaceContext

    router = getattr(request.app.state, "workspace_router", None)
    if router is None:
        raise HTTPException(500, "Workspace router not initialized")

    # In single-tenant mode, skip all checks
    from core.workspace_router import SingleTenantRouter
    if isinstance(router, SingleTenantRouter):
        ctx = WorkspaceContext(
            workspace_id=workspace_id or "default",
            org_id="default",
            schema_name="public",
            role="ws_admin",
            user_id="local",
            is_sandbox=False,
        )
        request.state.workspace_context = ctx
        return ctx

    # Multi-tenant: authenticate the caller
    user = await _authenticate_request(request, x_api_key)
    if user is None:
        raise HTTPException(401, "Invalid or missing authentication")

    # Verify user belongs to this workspace
    role = router.verify_membership(user.user_id, workspace_id)
    if role is None and user.org_id:
        # Org admins can access all workspaces in their org
        # Check if user is org_admin via any workspace membership
        from core.workspace_router import WorkspaceRouter
        if isinstance(router, WorkspaceRouter):
            with router.control_plane_connection() as conn:
                adapter = router._get_adapter()
                row = conn.fetchone(
                    adapter.param(
                        "SELECT role FROM workspace_memberships "
                        "WHERE user_id = ? AND role = 'org_admin' LIMIT 1"
                    ),
                    (user.user_id,),
                )
                if row:
                    role = "org_admin"

    if role is None:
        raise HTTPException(403, f"Not a member of workspace '{workspace_id}'")

    # Look up workspace metadata
    info = router._lookup_workspace(workspace_id)
    if info is None:
        raise HTTPException(404, f"Workspace '{workspace_id}' not found")

    ctx = WorkspaceContext(
        workspace_id=workspace_id,
        org_id=info["org_id"],
        schema_name=info["schema_name"],
        role=role,
        user_id=user.user_id,
        is_sandbox=info.get("is_sandbox", False),
    )
    request.state.workspace_context = ctx
    return ctx


async def _authenticate_request(
    request: Request, x_api_key: Optional[str]
) -> Optional[AuthenticatedUser]:
    """Authenticate request via API key or Bearer JWT."""

    # Try API key first
    if x_api_key:
        return await _auth_via_api_key(request, x_api_key)

    # Try Authorization: Bearer header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return await _auth_via_jwt(request, token)

    # Try CI token
    ci_token = request.headers.get("X-CI-Token")
    if ci_token:
        return await _auth_via_ci_token(request, ci_token)

    return None


async def _auth_via_api_key(request: Request, raw_key: str) -> Optional[AuthenticatedUser]:
    """Authenticate using an API key (existing fm_ key system)."""
    # Delegate to existing key verification in store
    db = getattr(request.app.state, "db", None)
    if db is None:
        return None

    try:
        key_record = db.verify_api_key(raw_key)
        if key_record is None:
            return None

        return AuthenticatedUser(
            user_id=key_record.get("created_by", "api_key_user"),
            org_id=key_record.get("org_id", "default"),
            workspace_ids=[key_record["workspace_id"]] if key_record.get("workspace_id") else [],
            key_workspace_id=key_record.get("workspace_id"),
            auth_method="api_key",
        )
    except Exception:
        return None


async def _auth_via_jwt(request: Request, token: str) -> Optional[AuthenticatedUser]:
    """Authenticate using a JWT (from device flow or SSO).

    Verifies the token signature (HS256), checks expiry, and extracts
    user/org/workspace claims.  The signing key must match the one used
    by the device-flow token endpoint (JWT_SIGNING_KEY env var).
    """
    signing_key = os.getenv("JWT_SIGNING_KEY", "")
    if not signing_key:
        logger.debug("JWT auth skipped: JWT_SIGNING_KEY not configured")
        return None

    try:
        import jwt as pyjwt
    except ImportError:
        logger.warning("JWT auth unavailable: PyJWT not installed (pip install PyJWT)")
        return None

    try:
        payload = pyjwt.decode(
            token,
            signing_key,
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "type"]},
        )
    except pyjwt.ExpiredSignatureError:
        logger.debug("JWT expired")
        return None
    except pyjwt.InvalidTokenError as exc:
        logger.debug("JWT invalid: %s", exc)
        return None

    # Only accept access tokens (not refresh tokens)
    if payload.get("type") != "access":
        logger.debug("JWT rejected: type=%s (expected 'access')", payload.get("type"))
        return None

    return AuthenticatedUser(
        user_id=payload["sub"],
        org_id=payload.get("org_id", ""),
        workspace_ids=payload.get("workspace_ids", []),
        auth_method="jwt",
    )


async def _auth_via_ci_token(request: Request, token: str) -> Optional[AuthenticatedUser]:
    """Authenticate using a CI/CD token."""
    import hmac
    expected = os.getenv("FORKMARK_CI_TOKEN", "")
    if not expected:
        return None
    if hmac.compare_digest(token, expected):
        return AuthenticatedUser(
            user_id="ci",
            org_id=os.getenv("FM_CI_ORG_ID", "default"),
            workspace_ids=[],
            auth_method="ci_token",
        )
    return None
