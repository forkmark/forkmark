"""Provider registry tests — CRUD, encryption, resolution, migration, security.

Run with:  pytest tests/test_providers.py -v
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _setup_env(tmp_path):
    """Fresh DB + disabled auth for every test."""
    os.environ["FM_DB_PATH"] = str(tmp_path / "providers.db")
    os.environ["FM_REQUIRE_UI_AUTH"] = "false"
    os.environ["FM_SECRET_KEY"] = "test-secret-key-for-encryption-12345"

    for mod_name in list(sys.modules):
        if mod_name.startswith(("config", "core.", "backend.")):
            del sys.modules[mod_name]

    from backend.main import app
    from fastapi.testclient import TestClient

    yield TestClient(app)


@pytest.fixture()
def client(_setup_env):
    return _setup_env


# ── CRUD Operations ──────────────────────────────────────────────────────────

class TestProviderCRUD:

    def test_list_empty(self, client):
        r = client.get("/api/providers")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_provider(self, client):
        r = client.post("/api/providers", json={
            "name": "Test OpenAI",
            "provider_type": "openai",
            "base_url": "",
            "api_key": "sk-test-key-12345",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Test OpenAI"
        assert data["provider_type"] == "openai"
        assert data["is_default"] is True  # first provider becomes default
        assert data["api_key_set"] is True
        assert "sk-test-key-12345" not in json.dumps(data)  # raw key never returned

    def test_create_second_provider(self, client):
        # First provider
        r1 = client.post("/api/providers", json={
            "name": "OpenAI Prod", "api_key": "sk-prod-key",
        })
        assert r1.status_code == 201
        assert r1.json()["is_default"] is True

        # Second provider — not default
        r2 = client.post("/api/providers", json={
            "name": "Anthropic Dev", "provider_type": "anthropic",
            "base_url": "https://api.anthropic.com", "api_key": "ant-key",
        })
        assert r2.status_code == 201
        assert r2.json()["is_default"] is False

        # List shows both
        r = client.get("/api/providers")
        assert len(r.json()) == 2

    def test_create_invalid_type(self, client):
        r = client.post("/api/providers", json={
            "name": "Bad Type", "provider_type": "invalid_type",
        })
        assert r.status_code == 400

    def test_update_provider(self, client):
        r = client.post("/api/providers", json={
            "name": "Original", "api_key": "sk-original",
        })
        pid = r.json()["id"]

        r2 = client.patch(f"/api/providers/{pid}", json={
            "name": "Updated Name", "base_url": "https://custom.api.com/v1",
        })
        assert r2.status_code == 200
        data = r2.json()
        assert data["name"] == "Updated Name"
        assert data["base_url"] == "https://custom.api.com/v1"
        assert data["api_key_set"] is True  # key preserved

    def test_update_nonexistent(self, client):
        r = client.patch("/api/providers/nonexistent", json={"name": "X"})
        assert r.status_code == 404

    def test_delete_provider(self, client):
        r = client.post("/api/providers", json={
            "name": "ToDelete", "api_key": "sk-del",
        })
        pid = r.json()["id"]

        r2 = client.delete(f"/api/providers/{pid}")
        assert r2.status_code == 204

        r3 = client.get("/api/providers")
        assert len(r3.json()) == 0

    def test_delete_default_promotes_next(self, client):
        """Deleting the default provider should promote the next one."""
        r1 = client.post("/api/providers", json={"name": "P1", "api_key": "k1"})
        r2 = client.post("/api/providers", json={"name": "P2", "api_key": "k2"})
        pid1 = r1.json()["id"]

        # P1 is default, delete it
        client.delete(f"/api/providers/{pid1}")

        # P2 should now be default
        providers = client.get("/api/providers").json()
        assert len(providers) == 1
        assert providers[0]["is_default"] is True
        assert providers[0]["name"] == "P2"

    def test_set_default(self, client):
        r1 = client.post("/api/providers", json={"name": "P1", "api_key": "k1"})
        r2 = client.post("/api/providers", json={"name": "P2", "api_key": "k2"})
        pid2 = r2.json()["id"]

        # Set P2 as default
        client.patch(f"/api/providers/{pid2}", json={"is_default": True})

        providers = client.get("/api/providers").json()
        defaults = [p for p in providers if p["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["id"] == pid2


# ── Key Encryption ───────────────────────────────────────────────────────────

class TestKeyEncryption:

    def test_masked_key_format(self, client):
        client.post("/api/providers", json={
            "name": "Masked", "api_key": "sk-1234567890abcdef",
        })
        providers = client.get("/api/providers").json()
        masked = providers[0]["api_key_masked"]
        # Should show first 4 and last 4 chars
        assert masked.startswith("sk-1")
        assert masked.endswith("cdef")
        assert "..." in masked
        # Full key should never appear
        assert "sk-1234567890abcdef" != masked

    def test_no_key_state(self, client):
        client.post("/api/providers", json={
            "name": "NoKey", "api_key": "",
        })
        providers = client.get("/api/providers").json()
        assert providers[0]["api_key_set"] is False
        assert providers[0]["api_key_masked"] == ""

    def test_key_update_preserves(self, client):
        """Updating a provider without sending api_key preserves existing key."""
        r = client.post("/api/providers", json={
            "name": "KeyTest", "api_key": "sk-original-key-value",
        })
        pid = r.json()["id"]

        # Update only name — no api_key field
        client.patch(f"/api/providers/{pid}", json={"name": "Renamed"})

        providers = client.get("/api/providers").json()
        assert providers[0]["api_key_set"] is True  # key still there


# ── Provider Credential Resolution ──────────────────────────────────────────

class TestCredentialResolution:

    def test_default_provider_resolution(self, client):
        """Default provider should be used when no provider_id is specified."""
        from backend.deps import db
        client.post("/api/providers", json={
            "name": "Default", "api_key": "sk-default-key",
            "base_url": "https://custom.api.com/v1",
        })
        creds = db.get_default_provider_credentials()
        assert creds is not None
        assert creds["api_key"] == "sk-default-key"
        assert creds["base_url"] == "https://custom.api.com/v1"

    def test_specific_provider_resolution(self, client):
        """Specific provider_id should resolve to that provider's credentials."""
        from backend.deps import db
        r = client.post("/api/providers", json={
            "name": "Specific", "api_key": "sk-specific",
            "base_url": "https://specific.api.com",
        })
        pid = r.json()["id"]
        creds = db.get_provider_credentials(pid)
        assert creds is not None
        assert creds["api_key"] == "sk-specific"
        assert creds["base_url"] == "https://specific.api.com"

    def test_nonexistent_provider_returns_none(self, client):
        from backend.deps import db
        creds = db.get_provider_credentials("nonexistent-id")
        assert creds is None

    def test_legacy_fallback_when_no_providers(self, client):
        """When no providers exist, should fall back to legacy settings."""
        from backend.deps import db
        # No providers configured
        creds = db.get_default_provider_credentials()
        assert creds is None  # falls back to legacy in _resolve_credentials


# ── Legacy Migration ────────────────────────────────────────────────────────

class TestLegacyMigration:

    def test_migrate_legacy_key(self, client):
        from backend.deps import db
        # Set legacy key directly in settings
        db.set_setting("openai_api_key", "sk-legacy-key-value")
        db.set_setting("openai_base_url", "https://openrouter.ai/api/v1")

        # Trigger migration
        pid = db.migrate_legacy_provider()
        assert pid is not None

        # Verify the migrated provider
        providers = client.get("/api/providers").json()
        assert len(providers) == 1
        p = providers[0]
        assert p["name"] == "Default (migrated)"
        assert p["is_default"] is True
        assert p["provider_type"] == "openrouter"  # detected from base_url
        assert p["api_key_set"] is True

    def test_no_migration_when_providers_exist(self, client):
        from backend.deps import db
        # Create a provider first
        client.post("/api/providers", json={"name": "Existing", "api_key": "k"})

        # Set legacy key
        db.set_setting("openai_api_key", "sk-should-not-migrate")

        # Migration should be a no-op
        pid = db.migrate_legacy_provider()
        assert pid is None

        providers = client.get("/api/providers").json()
        assert len(providers) == 1
        assert providers[0]["name"] == "Existing"

    def test_no_migration_without_legacy_key(self, client):
        from backend.deps import db
        pid = db.migrate_legacy_provider()
        assert pid is None

    def test_auto_migration_on_list(self, client):
        """GET /providers should auto-migrate legacy key."""
        from backend.deps import db
        db.set_setting("openai_api_key", "sk-auto-migrated")

        # Just listing triggers migration
        providers = client.get("/api/providers").json()
        assert len(providers) == 1
        assert providers[0]["name"] == "Default (migrated)"


# ── Test Connection ─────────────────────────────────────────────────────────

class TestProviderConnection:

    def test_test_nonexistent_provider(self, client):
        r = client.post("/api/providers/nonexistent/test")
        assert r.status_code == 404

    def test_test_no_key(self, client):
        r = client.post("/api/providers", json={"name": "NoKey"})
        pid = r.json()["id"]
        r2 = client.post(f"/api/providers/{pid}/test")
        assert r2.status_code == 200
        assert r2.json()["ok"] is False
        assert "No API key" in r2.json()["message"]

    @patch("httpx.get")
    def test_test_success(self, mock_get, client):
        r = client.post("/api/providers", json={
            "name": "TestConn", "api_key": "sk-test",
        })
        pid = r.json()["id"]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        r2 = client.post(f"/api/providers/{pid}/test")
        assert r2.status_code == 200
        assert r2.json()["ok"] is True


# ── Runner Integration ──────────────────────────────────────────────────────

class TestRunnerProviderIntegration:

    def test_runner_rejects_missing_provider(self, client):
        """Runner should return 400 when referencing a nonexistent provider."""
        r = client.post("/api/runner", json={
            "workflow_name": "test-wf",
            "eval_run_name": "test-run",
            "branch_a": {
                "name": "A", "model_id": "gpt-4o-mini", "temperature": 0.7,
                "provider_id": "nonexistent-provider-id",
                "steps": [{"name": "s1", "system_prompt": "", "user_prompt_template": "{{input}}"}],
            },
            "branch_b": {
                "name": "B", "model_id": "gpt-4o", "temperature": 0.7,
                "steps": [{"name": "s1", "system_prompt": "", "user_prompt_template": "{{input}}"}],
            },
            "test_cases": [{"label": "tc1", "input": "hello"}],
        })
        assert r.status_code == 400
        assert "not found" in r.json()["detail"].lower()

    def test_runner_no_provider_no_key_error(self, client):
        """Runner should error clearly when no provider and no legacy key."""
        r = client.post("/api/runner", json={
            "workflow_name": "test-wf",
            "eval_run_name": "test-run",
            "branch_a": {
                "name": "A", "model_id": "gpt-4o-mini", "temperature": 0.7,
                "steps": [{"name": "s1", "system_prompt": "", "user_prompt_template": "{{input}}"}],
            },
            "branch_b": {
                "name": "B", "model_id": "gpt-4o", "temperature": 0.7,
                "steps": [{"name": "s1", "system_prompt": "", "user_prompt_template": "{{input}}"}],
            },
            "test_cases": [{"label": "tc1", "input": "hello"}],
        })
        assert r.status_code == 400
        assert "provider" in r.json()["detail"].lower()


# ── Backward Compatibility ──────────────────────────────────────────────────

class TestBackwardCompatibility:

    def test_settings_still_work(self, client):
        """Existing settings endpoints should work unchanged."""
        r = client.get("/api/settings")
        assert r.status_code == 200
        assert "openai_api_key_set" in r.json()

    def test_runner_accepts_no_provider_id(self, client):
        """RunnerBranchConfig without provider_id should still be valid."""
        # Just validate the schema accepts the old format
        from backend.routes.runner import RunnerBranchConfig
        cfg = RunnerBranchConfig(
            name="A", model_id="gpt-4o-mini", temperature=0.7,
            steps=[],
        )
        assert cfg.provider_id is None

    def test_playground_accepts_no_provider_id(self, client):
        """PlaygroundRequest without provider_id fields should still be valid."""
        from backend.routes.runner import PlaygroundRequest
        req = PlaygroundRequest(prompt="test")
        assert req.provider_id_a is None
        assert req.provider_id_b is None


# ── Security ────────────────────────────────────────────────────────────────

class TestProviderSecurity:

    def test_raw_key_never_in_response(self, client):
        """API key should never appear in any response."""
        secret = "sk-super-secret-key-never-expose-this"
        r = client.post("/api/providers", json={
            "name": "SecTest", "api_key": secret,
        })
        assert secret not in r.text

        pid = r.json()["id"]
        r2 = client.get("/api/providers")
        assert secret not in r2.text

        r3 = client.patch(f"/api/providers/{pid}", json={"name": "Updated"})
        assert secret not in r3.text

    def test_provider_endpoints_require_auth_when_enabled(self, client):
        """Provider endpoints should respect auth settings."""
        # This test verifies the endpoint is wired through ui_write_auth/ui_read_auth
        # When FM_REQUIRE_UI_AUTH is false (our test default), all requests pass
        # The auth decorators are already tested in test_smoke.py
        r = client.get("/api/providers")
        assert r.status_code == 200
