"""Tests for the composition manifest loader."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from cogito.manifest import compose, fetch_service, load_manifest


@pytest.fixture
def json_manifest(tmp_path):
    """Create a test manifest file."""
    manifest = {
        "services": [
            {
                "name": "svc-internal",
                "endpoint": "http://localhost:3104/reflect",
                "type": "internal",
            },
            {
                "name": "svc-external",
                "type": "external",
                "static": {
                    "identity": {
                        "name": "svc-external",
                        "description": "External service",
                        "language": "node",
                        "port": 3101,
                    },
                    "capabilities": [
                        {
                            "name": "read_channel",
                            "description": "Read channel messages",
                            "tools": ["channels_list"],
                        }
                    ],
                },
            },
        ]
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.fixture
def yaml_manifest(tmp_path):
    """Create a YAML manifest file."""
    content = """
services:
  - name: svc-a
    endpoint: http://localhost:3000/reflect
    type: internal
  - name: svc-b
    type: external
    static:
      identity:
        name: svc-b
        description: Static service
"""
    path = tmp_path / "manifest.yaml"
    path.write_text(content, encoding="utf-8")
    return path


class TestLoadManifest:
    def test_load_json(self, json_manifest):
        data = load_manifest(json_manifest)
        assert "services" in data
        assert len(data["services"]) == 2

    def test_load_yaml(self, yaml_manifest):
        data = load_manifest(yaml_manifest)
        assert "services" in data
        assert len(data["services"]) == 2

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_manifest(tmp_path / "nonexistent.json")

    def test_unsupported_format(self, tmp_path):
        path = tmp_path / "manifest.xml"
        path.write_text("<manifest/>")
        with pytest.raises(ValueError, match="Unsupported"):
            load_manifest(path)

    def test_empty_yaml_raises(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid manifest"):
            load_manifest(path)

    def test_non_dict_json_raises(self, tmp_path):
        path = tmp_path / "array.json"
        path.write_text('[{"name": "svc"}]', encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid manifest"):
            load_manifest(path)


class TestFetchService:
    @pytest.mark.asyncio
    async def test_success(self):
        from unittest.mock import MagicMock

        mock_data = {"identity": {"name": "svc", "version": "1.0", "description": "test"}}
        with patch("cogito.manifest.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await fetch_service("http://localhost:3104/reflect")
            assert result == mock_data

    @pytest.mark.asyncio
    async def test_failure_returns_error_stub(self):
        with patch("cogito.manifest.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await fetch_service("http://localhost:9999/reflect")
            assert result["identity"]["status"] == "unreachable"
            assert "error" in result


class TestCompose:
    @pytest.mark.asyncio
    async def test_external_service_uses_static(self, json_manifest):
        """External services should use static data from manifest."""
        with patch("cogito.manifest.fetch_service", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "identity": {"name": "svc-internal", "version": "abc", "description": "Internal"}
            }

            results = await compose(json_manifest)
            assert len(results) == 2

            # First is internal (fetched)
            assert results[0]["identity"]["name"] == "svc-internal"

            # Second is external (static)
            assert results[1]["identity"]["name"] == "svc-external"
            assert results[1]["capabilities"][0]["name"] == "read_channel"

            # fetch_service should only be called for internal
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_internal_failure_returns_partial(self, json_manifest):
        """If internal service fetch fails, include error stub."""
        with patch("cogito.manifest.fetch_service", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "identity": {"name": "http://localhost:3104/reflect", "status": "unreachable"},
                "error": "Connection refused",
            }

            results = await compose(json_manifest)
            assert len(results) == 2
            assert results[0]["identity"]["status"] == "unreachable"
            # External still works
            assert results[1]["identity"]["name"] == "svc-external"

    @pytest.mark.asyncio
    async def test_no_endpoint_configured(self, tmp_path):
        """Internal service with no endpoint should produce error stub."""
        manifest = {
            "services": [
                {"name": "no-endpoint", "type": "internal"},
            ]
        }
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")

        results = await compose(path)
        assert len(results) == 1
        assert results[0]["identity"]["status"] == "unreachable"
        assert "No endpoint" in results[0]["error"]
