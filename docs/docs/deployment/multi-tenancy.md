# Multi-Tenancy

Forkmark implements PostgreSQL schema-level tenant isolation. Each workspace gets its own schema, making cross-tenant data leakage impossible at the database level.

## Enabling multi-tenancy

```bash
FM_MULTI_TENANT=true
FM_DATABASE_URL=postgresql://fp:fp@localhost:5432/forkmark
```

Multi-tenancy requires PostgreSQL. SQLite is not supported for multi-tenant deployments.

## How it works

When multi-tenancy is enabled, the `WorkspaceRouter`:

1. Validates the `workspace_id` from the URL path
2. Looks up the workspace's schema name from the control plane (`public` schema)
3. Acquires a pooled connection and sets `search_path` to the workspace schema
4. Yields the connection (queries can only hit the workspace schema)
5. Resets `search_path` on connection return

Schema names follow the pattern `workspace_{slug}` and are validated against `^workspace_[a-z0-9_]{1,50}$` to prevent SQL injection.

## Workspace provisioning

### Via API

```bash
curl -X POST http://localhost:7700/api/workspaces \
  -H "X-API-Key: fm_..." \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Fraud Detection Team",
    "org_id": "org_acme",
    "slug": "fraud_detection"
  }'
```

### Via SCIM 2.0

Forkmark supports SCIM provisioning via WorkOS for enterprise directory sync:

- User provisioning and deactivation
- Group-to-workspace mapping
- Domain-based auto-routing
- HMAC-verified webhooks

Configure WorkOS credentials in your environment:

```bash
WORKOS_API_KEY=sk_...
WORKOS_WEBHOOK_SECRET=whsec_...
```

## RBAC

Users are assigned roles per workspace. See [Authentication](../api/authentication.md) for the full role matrix.

## Sandbox workspaces

Sandbox workspaces are restricted environments that block sensitive operations:

- DPO/preference data exports
- Decision creation
- Workflow deletion

This allows teams to experiment safely without affecting production data pipelines.

## Data residency

For compliance requirements (GDPR, EU AI Act), Forkmark supports region-aware workspace routing:

| Region | Env vars |
|--------|----------|
| US (us-east-1) | `FM_DB_URL_US`, `FM_REDIS_URL_US` |
| EU (eu-west-1) | `FM_DB_URL_EU`, `FM_REDIS_URL_EU` |
| APAC (ap-southeast-1) | `FM_DB_URL_APAC`, `FM_REDIS_URL_APAC` |

Each region has its own PostgreSQL cluster and Redis instance. Cross-region access is denied at the middleware level.

## Cache management

The workspace router caches schema lookups (up to 1000 entries) with bounded LRU eviction. The cache is invalidated automatically on workspace deletion. For manual invalidation:

```python
router.invalidate_cache("workspace_id")
```
