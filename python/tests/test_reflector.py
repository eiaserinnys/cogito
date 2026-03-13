"""Tests for the Reflector core class."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from cogito import Reflector


@pytest.fixture
def reflector(tmp_path):
    """Create a Reflector with a fixed version (no git dependency)."""
    return Reflector(
        name="test-service",
        description="A test service",
        version_from="1.0.0-test",
        source_root=str(tmp_path),
        language="python",
        port=8080,
        transport="http",
    )


class TestIdentity:
    def test_identity_fields(self, reflector):
        ident = reflector.identity
        assert ident.name == "test-service"
        assert ident.version == "1.0.0-test"
        assert ident.description == "A test service"
        assert ident.language == "python"
        assert ident.port == 8080
        assert ident.transport == "http"

    def test_identity_to_dict(self, reflector):
        d = reflector.identity.to_dict()
        assert d["name"] == "test-service"
        assert d["version"] == "1.0.0-test"
        assert "port" in d
        assert "transport" in d

    def test_identity_optional_fields_omitted(self, tmp_path):
        r = Reflector(
            name="minimal",
            description="minimal service",
            version_from="0.1",
            source_root=str(tmp_path),
        )
        d = r.identity.to_dict()
        assert "port" not in d
        assert "transport" not in d
        assert d["language"] == "python"


class TestVersionFromGit:
    def test_git_version_success(self, tmp_path):
        with patch("cogito.reflector.get_git_head", return_value="abc123"):
            r = Reflector(
                name="git-svc",
                description="test",
                version_from="git",
                source_root=str(tmp_path),
            )
        assert r.identity.version == "abc123"

    def test_git_version_failure_falls_back_to_unknown(self, tmp_path):
        with patch("cogito.reflector.get_git_head", return_value="unknown"):
            r = Reflector(
                name="git-svc",
                description="test",
                version_from="git",
                source_root=str(tmp_path),
            )
        assert r.identity.version == "unknown"


class TestCapabilityRegistration:
    def test_decorator_registers_capability(self, reflector):
        @reflector.capability(
            name="image_gen",
            description="Generate images",
            tools=["gen_image"],
            tags=["ai"],
        )
        async def gen_image():
            pass

        caps = reflector.get_capabilities()
        assert len(caps) == 1
        assert caps[0].name == "image_gen"
        assert caps[0].tools == ["gen_image"]
        assert caps[0].tags == ["ai"]

    def test_declare_capability(self, reflector):
        reflector.declare_capability(
            name="proc_mgmt",
            description="Process management",
            tools=["start", "stop"],
            configs=[{"key": "MAX_RESTARTS", "source": "env"}],
        )
        caps = reflector.get_capabilities()
        assert len(caps) == 1
        assert caps[0].name == "proc_mgmt"

    def test_duplicate_capability_raises(self, reflector):
        @reflector.capability(name="dup_cap", description="First")
        async def func1():
            pass

        with pytest.raises(ValueError, match="already registered"):

            @reflector.capability(name="dup_cap", description="Second")
            async def func2():
                pass

    def test_multiple_capabilities(self, reflector):
        @reflector.capability(name="cap1", description="First")
        async def func1():
            pass

        @reflector.capability(name="cap2", description="Second")
        async def func2():
            pass

        caps = reflector.get_capabilities()
        assert len(caps) == 2
        names = {c.name for c in caps}
        assert names == {"cap1", "cap2"}


class TestLevel0:
    def test_level0_structure(self, reflector):
        @reflector.capability(name="test_cap", description="Test")
        async def func():
            pass

        data = reflector.get_level0()
        assert "identity" in data
        assert "capabilities" in data
        assert len(data["capabilities"]) == 1
        assert data["identity"]["name"] == "test-service"


class TestLevel1Configs:
    def test_config_from_decorator(self, reflector):
        with patch.dict(os.environ, {"MY_KEY": "secret_value"}):

            @reflector.capability(name="cap1", description="Cap with config")
            @reflector.config("MY_KEY", sensitive=True)
            async def func():
                pass

            configs = reflector.get_configs()
            assert len(configs) == 1
            assert configs[0].key == "MY_KEY"
            assert configs[0].capability == "cap1"
            assert configs[0].sensitive is True
            assert configs[0].status == "valid"
            assert configs[0].current_value == "se***"

    def test_config_missing(self, reflector):
        with patch.dict(os.environ, {}, clear=True):

            @reflector.capability(name="cap1", description="Cap")
            @reflector.config("NONEXISTENT_KEY")
            async def func():
                pass

            configs = reflector.get_configs()
            assert configs[0].status == "missing"
            assert configs[0].current_value is None

    def test_config_empty(self, reflector):
        with patch.dict(os.environ, {"EMPTY_KEY": ""}):

            @reflector.capability(name="cap1", description="Cap")
            @reflector.config("EMPTY_KEY")
            async def func():
                pass

            configs = reflector.get_configs()
            assert configs[0].status == "empty"
            assert configs[0].current_value == ""

    def test_config_filter_by_capability(self, reflector):
        with patch.dict(os.environ, {"K1": "v1", "K2": "v2"}):

            @reflector.capability(name="cap1", description="Cap 1")
            @reflector.config("K1")
            async def func1():
                pass

            @reflector.capability(name="cap2", description="Cap 2")
            @reflector.config("K2")
            async def func2():
                pass

            configs = reflector.get_configs("cap1")
            assert len(configs) == 1
            assert configs[0].key == "K1"

    def test_standalone_config(self, reflector):
        with patch.dict(os.environ, {"STANDALONE": "val"}):
            reflector.declare_config("STANDALONE", source="env")
            configs = reflector.get_configs()
            standalone = [c for c in configs if c.capability is None]
            assert len(standalone) == 1
            assert standalone[0].key == "STANDALONE"


class TestLevel2Sources:
    def test_source_from_decorator(self, reflector):
        @reflector.capability(name="src_cap", description="Source test")
        async def my_func():
            pass

        sources = reflector.get_sources()
        assert len(sources) == 1
        assert sources[0].capability == "src_cap"
        assert sources[0].entry_point == "TestLevel2Sources.test_source_from_decorator.<locals>.my_func"
        assert sources[0].start_line > 0
        assert sources[0].end_line >= sources[0].start_line

    def test_source_filter_by_capability(self, reflector):
        @reflector.capability(name="cap_a", description="A")
        async def func_a():
            pass

        @reflector.capability(name="cap_b", description="B")
        async def func_b():
            pass

        sources = reflector.get_sources("cap_a")
        assert len(sources) == 1
        assert sources[0].capability == "cap_a"

    def test_declared_capability_has_no_source(self, reflector):
        reflector.declare_capability(name="no_src", description="No source")
        sources = reflector.get_sources()
        assert len(sources) == 0


class TestLevel3Runtime:
    def test_runtime_basic(self, reflector):
        data = reflector.get_level3()
        assert data["status"] == "healthy"
        assert "pid" in data
        assert data["uptime_seconds"] >= 0

    def test_runtime_includes_process_context(self, reflector):
        data = reflector.get_level3()
        assert "exe" in data
        assert "cmdline" in data
        assert isinstance(data["cmdline"], list)
        assert "cwd" in data

    def test_report_error_changes_status(self, reflector):
        reflector.report_error("something broke")
        data = reflector.get_level3()
        assert data["status"] == "degraded"
        assert data["last_error"] == "something broke"

    def test_report_healthy_clears_error(self, reflector):
        reflector.report_error("oops")
        reflector.report_healthy()
        data = reflector.get_level3()
        assert data["status"] == "healthy"
        assert data.get("last_error") is None


class TestFullResponse:
    def test_full_contains_all_levels(self, reflector):
        @reflector.capability(name="full_cap", description="Full test")
        @reflector.config("FULL_KEY")
        async def func():
            pass

        data = reflector.get_full()
        assert "identity" in data
        assert "capabilities" in data
        assert "configs" in data
        assert "sources" in data
        assert "runtime" in data
