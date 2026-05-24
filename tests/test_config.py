from pathlib import Path

from glm_cellphone.adb import find_adb
from glm_cellphone.config import Settings


def test_settings_accept_zai_key_alias():
    settings = Settings(ZAI_KEY="secret")
    assert settings.resolved_api_key == "secret"


def test_allowed_mcp_hosts_include_public_base_url_host():
    settings = Settings(GLM_CELLPHONE_PUBLIC_BASE_URL="http://100.64.0.10:8787")

    assert "100.64.0.10:*" in settings.allowed_mcp_hosts


def test_allowed_mcp_hosts_include_explicit_hosts():
    settings = Settings(GLM_CELLPHONE_MCP_ALLOWED_HOSTS="phone-mac:*,100.64.0.10:*")

    assert "phone-mac:*" in settings.allowed_mcp_hosts
    assert "100.64.0.10:*" in settings.allowed_mcp_hosts


def test_find_adb_prefers_configured_executable(tmp_path: Path):
    adb = tmp_path / "adb"
    adb.write_text("#!/bin/sh\n", encoding="utf-8")
    adb.chmod(0o755)

    assert find_adb(str(adb), []) == str(adb)
