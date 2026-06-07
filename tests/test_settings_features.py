"""Tests for new Settings features:
  1. Divergence Scorer Strategy (UI-configurable)
  2. Theme preference persistence
  3. Background Workers slider (system-info)
  4. Notification preferences
  5. User Profile & Team Settings
  6. Enterprise feature status endpoint

These tests validate both the API endpoints and the underlying
settings persistence layer.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("FM_DB_PATH", ":memory:")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_client(tmp_path, env_overrides=None):
    """Create a fresh TestClient with isolated DB and optional env overrides."""
    env = {
        "FM_DB_PATH": str(tmp_path / "settings_test.db"),
        "FM_REQUIRE_UI_AUTH": "false",
    }
    if env_overrides:
        env.update(env_overrides)

    for k, v in env.items():
        os.environ[k] = v

    # Force reimport to pick up new DB path and config
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith(("core.store", "backend.main", "config")):
            importlib.reload(sys.modules[mod_name])

    from backend.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ── 1. Divergence Scorer Strategy ────────────────────────────────────────────

class TestDivergenceScorerSettings:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.client = _make_client(tmp_path)

    def test_get_settings_returns_default_scorer(self):
        resp = self.client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "divergence_scorer" in data
        assert data["divergence_scorer"] in ("auto", "lexical", "semantic", "openai", "llm_judge")

    def test_get_settings_returns_default_st_model(self):
        resp = self.client.get("/api/settings")
        data = resp.json()
        assert data["st_model"] == "all-MiniLM-L6-v2"

    def test_get_settings_returns_default_embed_model(self):
        resp = self.client.get("/api/settings")
        data = resp.json()
        assert data["embed_model"] == "text-embedding-3-small"

    def test_patch_divergence_scorer_valid(self):
        for scorer in ("auto", "lexical", "semantic", "openai", "llm_judge"):
            resp = self.client.patch("/api/settings", json={"divergence_scorer": scorer})
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

        # Verify the last one stuck
        resp = self.client.get("/api/settings")
        assert resp.json()["divergence_scorer"] == "llm_judge"

    def test_patch_divergence_scorer_invalid(self):
        resp = self.client.patch("/api/settings", json={"divergence_scorer": "invalid_mode"})
        assert resp.status_code == 400
        assert "Invalid divergence_scorer" in resp.json()["detail"]

    def test_patch_scorer_case_insensitive(self):
        resp = self.client.patch("/api/settings", json={"divergence_scorer": "LLM_JUDGE"})
        assert resp.status_code == 200

        resp = self.client.get("/api/settings")
        assert resp.json()["divergence_scorer"] == "llm_judge"

    def test_patch_st_model(self):
        resp = self.client.patch("/api/settings", json={
            "divergence_scorer": "semantic",
            "st_model": "paraphrase-MiniLM-L3-v2"
        })
        assert resp.status_code == 200

        resp = self.client.get("/api/settings")
        assert resp.json()["st_model"] == "paraphrase-MiniLM-L3-v2"

    def test_patch_embed_model(self):
        resp = self.client.patch("/api/settings", json={
            "divergence_scorer": "openai",
            "embed_model": "text-embedding-3-large"
        })
        assert resp.status_code == 200

        resp = self.client.get("/api/settings")
        assert resp.json()["embed_model"] == "text-embedding-3-large"


# ── 2. Theme Preference ─────────────────────────────────────────────────────

class TestThemeSettings:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.client = _make_client(tmp_path)

    def test_default_theme_is_dark(self):
        resp = self.client.get("/api/settings")
        assert resp.json()["theme"] == "dark"

    def test_set_theme_light(self):
        resp = self.client.patch("/api/settings", json={"theme": "light"})
        assert resp.status_code == 200

        resp = self.client.get("/api/settings")
        assert resp.json()["theme"] == "light"

    def test_set_theme_dark(self):
        # Set light first, then back to dark
        self.client.patch("/api/settings", json={"theme": "light"})
        resp = self.client.patch("/api/settings", json={"theme": "dark"})
        assert resp.status_code == 200

        resp = self.client.get("/api/settings")
        assert resp.json()["theme"] == "dark"

    def test_theme_persists_across_reads(self):
        self.client.patch("/api/settings", json={"theme": "light"})
        # Read multiple times
        for _ in range(3):
            resp = self.client.get("/api/settings")
            assert resp.json()["theme"] == "light"


# ── 3. Background Workers ───────────────────────────────────────────────────

class TestBackgroundWorkerSettings:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.client = _make_client(tmp_path)

    def test_system_info_returns_workers(self):
        resp = self.client.get("/api/system-info")
        assert resp.status_code == 200
        data = resp.json()
        assert "background_workers" in data
        assert isinstance(data["background_workers"], int)
        assert data["background_workers"] >= 1

    def test_patch_workers_valid(self):
        resp = self.client.patch("/api/system-info", json={"background_workers": 8})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["restart_required"] is True

    def test_patch_workers_minimum(self):
        resp = self.client.patch("/api/system-info", json={"background_workers": 1})
        assert resp.status_code == 200

    def test_patch_workers_maximum(self):
        resp = self.client.patch("/api/system-info", json={"background_workers": 16})
        assert resp.status_code == 200

    def test_patch_workers_too_low(self):
        resp = self.client.patch("/api/system-info", json={"background_workers": 0})
        assert resp.status_code == 400
        assert "between 1 and 16" in resp.json()["detail"]

    def test_patch_workers_too_high(self):
        resp = self.client.patch("/api/system-info", json={"background_workers": 100})
        assert resp.status_code == 400
        assert "between 1 and 16" in resp.json()["detail"]

    def test_patch_workers_negative(self):
        resp = self.client.patch("/api/system-info", json={"background_workers": -1})
        assert resp.status_code == 400


# ── 4. Notification Preferences ─────────────────────────────────────────────

class TestNotificationSettings:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.client = _make_client(tmp_path)

    def test_default_notifications(self):
        resp = self.client.get("/api/settings")
        data = resp.json()
        assert data["notifications_toast"] == "true"
        assert data["notifications_browser"] == "false"
        assert data["notifications_auto_dismiss"] == "5"

    def test_disable_toast_notifications(self):
        resp = self.client.patch("/api/settings", json={
            "notifications_toast": "false"
        })
        assert resp.status_code == 200

        resp = self.client.get("/api/settings")
        assert resp.json()["notifications_toast"] == "false"

    def test_enable_browser_notifications(self):
        resp = self.client.patch("/api/settings", json={
            "notifications_browser": "true"
        })
        assert resp.status_code == 200

        resp = self.client.get("/api/settings")
        assert resp.json()["notifications_browser"] == "true"

    def test_set_auto_dismiss(self):
        resp = self.client.patch("/api/settings", json={
            "notifications_auto_dismiss": "10"
        })
        assert resp.status_code == 200

        resp = self.client.get("/api/settings")
        assert resp.json()["notifications_auto_dismiss"] == "10"

    def test_multiple_notification_settings_at_once(self):
        resp = self.client.patch("/api/settings", json={
            "notifications_toast": "false",
            "notifications_browser": "true",
            "notifications_auto_dismiss": "8"
        })
        assert resp.status_code == 200

        resp = self.client.get("/api/settings")
        data = resp.json()
        assert data["notifications_toast"] == "false"
        assert data["notifications_browser"] == "true"
        assert data["notifications_auto_dismiss"] == "8"


# ── 5. User Profile ─────────────────────────────────────────────────────────

class TestUserProfileSettings:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.client = _make_client(tmp_path)

    def test_default_profile(self):
        resp = self.client.get("/api/settings")
        data = resp.json()
        assert data["display_name"] == ""
        assert data["timezone"] == ""

    def test_set_display_name(self):
        resp = self.client.patch("/api/settings", json={
            "display_name": "Alice Chen"
        })
        assert resp.status_code == 200

        resp = self.client.get("/api/settings")
        assert resp.json()["display_name"] == "Alice Chen"

    def test_set_timezone(self):
        resp = self.client.patch("/api/settings", json={
            "timezone": "America/New_York"
        })
        assert resp.status_code == 200

        resp = self.client.get("/api/settings")
        assert resp.json()["timezone"] == "America/New_York"

    def test_update_profile_preserves_other_settings(self):
        # Set theme and scorer first
        self.client.patch("/api/settings", json={
            "theme": "light",
            "divergence_scorer": "lexical"
        })
        # Now update profile
        self.client.patch("/api/settings", json={
            "display_name": "Bob",
            "timezone": "Europe/London"
        })

        resp = self.client.get("/api/settings")
        data = resp.json()
        assert data["display_name"] == "Bob"
        assert data["timezone"] == "Europe/London"
        assert data["theme"] == "light"
        assert data["divergence_scorer"] == "lexical"


# ── 6. Enterprise Feature Status ────────────────────────────────────────────

class TestEnterpriseFeatureStatus:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.client = _make_client(tmp_path)

    def test_system_info_returns_enterprise_flags(self):
        resp = self.client.get("/api/system-info")
        assert resp.status_code == 200
        data = resp.json()
        # All enterprise features should be present
        assert "multi_tenant" in data
        assert "scim_enabled" in data
        assert "device_flow_enabled" in data
        assert "otel_enabled" in data
        assert "require_ui_auth" in data

    def test_enterprise_flags_are_booleans(self):
        resp = self.client.get("/api/system-info")
        data = resp.json()
        for key in ("multi_tenant", "scim_enabled", "device_flow_enabled",
                     "otel_enabled", "require_ui_auth"):
            assert isinstance(data[key], bool), f"{key} should be bool, got {type(data[key])}"

    def test_default_enterprise_flags_are_off(self):
        """In test environment with no env vars set, all enterprise flags should be False."""
        resp = self.client.get("/api/system-info")
        data = resp.json()
        assert data["multi_tenant"] is False
        assert data["scim_enabled"] is False
        assert data["device_flow_enabled"] is False

    def test_system_info_returns_version(self):
        resp = self.client.get("/api/system-info")
        data = resp.json()
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_patch_require_ui_auth_valid(self):
        resp = self.client.patch("/api/system-info", json={"require_ui_auth": "true"})
        assert resp.status_code == 200
        assert resp.json()["restart_required"] is True

    def test_patch_require_ui_auth_invalid(self):
        resp = self.client.patch("/api/system-info", json={"require_ui_auth": "maybe"})
        assert resp.status_code == 400
        assert "true" in resp.json()["detail"] and "false" in resp.json()["detail"]


# ── 7. Settings Persistence (store layer) ───────────────────────────────────

class TestSettingsPersistence:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        from core.store import Database
        self.db = Database(str(tmp_path / "persist_test.db"))

    def test_set_and_get_setting(self):
        self.db.set_setting("divergence_scorer", "semantic")
        assert self.db.get_setting("divergence_scorer") == "semantic"

    def test_overwrite_setting(self):
        self.db.set_setting("theme", "dark")
        self.db.set_setting("theme", "light")
        assert self.db.get_setting("theme") == "light"

    def test_get_all_includes_new_keys(self):
        self.db.set_setting("divergence_scorer", "lexical")
        self.db.set_setting("theme", "light")
        self.db.set_setting("display_name", "Test User")

        all_settings = self.db.get_all_settings()
        assert all_settings["divergence_scorer"] == "lexical"
        assert all_settings["theme"] == "light"
        assert all_settings["display_name"] == "Test User"

    def test_missing_setting_returns_default(self):
        assert self.db.get_setting("nonexistent", "fallback") == "fallback"

    def test_multiple_settings_independent(self):
        """Saving one setting should not affect another."""
        self.db.set_setting("notifications_toast", "false")
        self.db.set_setting("notifications_browser", "true")

        assert self.db.get_setting("notifications_toast") == "false"
        assert self.db.get_setting("notifications_browser") == "true"


# ── 8. Config save_env_setting ──────────────────────────────────────────────

class TestSaveEnvSetting:
    def test_save_and_reload(self, tmp_path):
        """save_env_setting should write to .env and be loadable."""
        from config import save_env_setting, _load_dotenv

        # Override FM_HOME to use tmp_path
        env_dir = tmp_path / ".forkmark"
        env_dir.mkdir()
        env_file = env_dir / ".env"

        import config as cfg
        original_home = cfg._FM_HOME
        original_env = cfg._ENV_FILE
        try:
            cfg._FM_HOME = env_dir
            cfg._ENV_FILE = env_file

            save_env_setting("FM_BACKGROUND_WORKERS", "12")

            # Verify file content
            content = env_file.read_text()
            assert "FM_BACKGROUND_WORKERS=12" in content

            # Verify update in place
            save_env_setting("FM_BACKGROUND_WORKERS", "8")
            content = env_file.read_text()
            assert "FM_BACKGROUND_WORKERS=8" in content
            assert content.count("FM_BACKGROUND_WORKERS") == 1

        finally:
            cfg._FM_HOME = original_home
            cfg._ENV_FILE = original_env

    def test_save_new_key_appends(self, tmp_path):
        from config import save_env_setting

        env_dir = tmp_path / ".forkmark"
        env_dir.mkdir()
        env_file = env_dir / ".env"
        env_file.write_text("FM_HOST=0.0.0.0\n")

        import config as cfg
        original_home = cfg._FM_HOME
        original_env = cfg._ENV_FILE
        try:
            cfg._FM_HOME = env_dir
            cfg._ENV_FILE = env_file

            save_env_setting("FM_BACKGROUND_WORKERS", "6")

            content = env_file.read_text()
            assert "FM_HOST=0.0.0.0" in content
            assert "FM_BACKGROUND_WORKERS=6" in content
        finally:
            cfg._FM_HOME = original_home
            cfg._ENV_FILE = original_env


# ── 9. Combined Settings — no cross-contamination ───────────────────────────

class TestSettingsIsolation:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.client = _make_client(tmp_path)

    def test_patch_only_updates_specified_fields(self):
        """PATCH with one field should not reset others."""
        # Set multiple fields
        self.client.patch("/api/settings", json={
            "divergence_scorer": "semantic",
            "theme": "light",
            "display_name": "Alice",
        })

        # Now update only one
        self.client.patch("/api/settings", json={
            "divergence_scorer": "lexical",
        })

        resp = self.client.get("/api/settings")
        data = resp.json()
        assert data["divergence_scorer"] == "lexical"
        assert data["theme"] == "light"        # unchanged
        assert data["display_name"] == "Alice"  # unchanged

    def test_system_info_and_settings_are_independent(self):
        """Patching system-info should not affect /api/settings and vice versa."""
        self.client.patch("/api/settings", json={"theme": "light"})

        # system-info PATCH writes to .env for next restart — it does NOT
        # change the in-memory config.BACKGROUND_WORKERS value
        initial_workers = self.client.get("/api/system-info").json()["background_workers"]
        self.client.patch("/api/system-info", json={"background_workers": 8})

        settings = self.client.get("/api/settings").json()
        sysinfo = self.client.get("/api/system-info").json()

        assert settings["theme"] == "light"
        # Workers still reflect the startup value (not the pending restart value)
        assert sysinfo["background_workers"] == initial_workers

    def test_unknown_settings_keys_ignored(self):
        """Extra keys in PATCH body should be silently ignored, not error."""
        resp = self.client.patch("/api/settings", json={
            "theme": "dark",
            "nonexistent_key_xyz": "value",
        })
        assert resp.status_code == 200  # no 422 or 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
