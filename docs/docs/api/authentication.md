# Authentication

Forkmark supports three authentication methods: API keys, JWT tokens (via device flow), and CI tokens.

## API keys

The primary authentication method. Keys are prefixed with `fm_` and hashed with Argon2id at rest.

```bash
curl -X GET http://localhost:7700/api/workflows \
  -H "X-API-Key: fm_your_key_here"
```

### Creating your first key

The first API key can be created without authentication from localhost:

```bash
curl -X POST http://localhost:7700/api/keys \
  -H "Content-Type: application/json" \
  -d '{"label": "my-first-key"}'
```

For remote bootstrap, set `FM_BOOTSTRAP_TOKEN` and pass it as the `X-API-Key` header.

### Key scoping

Keys can be scoped to a specific workspace in multi-tenant mode. A workspace-scoped key can only access resources within that workspace.

## JWT tokens (device flow)

For CLI and desktop applications, Forkmark implements RFC 8628 Device Authorization Grant:

1. Client requests a device code from `/api/auth/device`
2. User visits the verification URL and enters the code
3. Client polls `/api/auth/token` until the user approves
4. Server issues a JWT (HS256) access token

JWTs are verified on every request using the `JWT_SIGNING_KEY` environment variable. Tokens include `sub` (user ID), `org_id`, `workspace_ids`, `type` (must be `access`), and `exp` claims.

```bash
# Using a JWT
curl -X GET http://localhost:7700/api/workflows \
  -H "Authorization: Bearer eyJ..."
```

## CI tokens

For CI/CD pipelines, set `FORKMARK_CI_TOKEN` on the server and pass it via:

```bash
curl -X GET http://localhost:7700/api/workflows \
  -H "X-CI-Token: your_ci_token"
```

CI tokens are verified using constant-time HMAC comparison.

## RBAC

In multi-tenant mode, users are assigned roles per workspace:

| Role | Scope | Key permissions |
|------|-------|----------------|
| `org_admin` | Organization | All permissions across all workspaces |
| `ws_admin` | Workspace | Manage members, settings, keys, full CRUD |
| `evaluator` | Workspace | Read workflows, create runs, make decisions |
| `viewer` | Workspace | Read-only access, export read |
| `sdk_only` | Workspace | Read workflows, create runs (no UI access) |

### Sandbox workspaces

Sandbox workspaces block sensitive operations: DPO exports, decision creation, and workflow deletion. This is enforced server-side regardless of user role.

## Single-tenant mode

When `FM_MULTI_TENANT` is not set (default), Forkmark runs in single-tenant mode:

- All users are treated as `ws_admin`
- Workspace isolation is disabled
- UI read endpoints are unauthenticated by default (set `FM_REQUIRE_UI_AUTH=true` to change)
