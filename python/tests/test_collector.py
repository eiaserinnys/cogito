"""Tests for collector functions."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from cogito.collector import (
    build_config_entry,
    collect_runtime,
    get_git_head,
    get_git_remote_url,
    resolve_config_status,
    resolve_source,
)


class TestResolveConfigStatus:
    def test_valid(self):
        with patch.dict(os.environ, {"MY_KEY": "secret123"}):
            status, value = resolve_config_status("MY_KEY", sensitive=False)
            assert status == "valid"
            assert value == "secret123"

    def test_valid_sensitive(self):
        with patch.dict(os.environ, {"MY_KEY": "secret123"}):
            status, value = resolve_config_status("MY_KEY", sensitive=True)
            assert status == "valid"
            assert value == "se***"

    def test_valid_sensitive_short(self):
        with patch.dict(os.environ, {"MY_KEY": "x"}):
            status, value = resolve_config_status("MY_KEY", sensitive=True)
            assert status == "valid"
            assert value == "***"

    def test_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            status, value = resolve_config_status("NONEXISTENT", sensitive=False)
            assert status == "missing"
            assert value is None

    def test_empty(self):
        with patch.dict(os.environ, {"EMPTY": ""}):
            status, value = resolve_config_status("EMPTY", sensitive=False)
            assert status == "empty"
            assert value == ""


class TestBuildConfigEntry:
    def test_builds_with_live_status(self):
        with patch.dict(os.environ, {"BUILD_KEY": "hello"}):
            entry = build_config_entry(
                key="BUILD_KEY",
                capability="cap1",
                source="env",
                source_path=".env",
                sensitive=False,
                required=True,
            )
            assert entry.key == "BUILD_KEY"
            assert entry.capability == "cap1"
            assert entry.status == "valid"
            assert entry.current_value == "hello"
            assert entry.source_path == ".env"


class TestResolveSource:
    def test_resolves_function(self, tmp_path):
        async def sample_func():
            pass

        entry = resolve_source(
            func=sample_func,
            capability_name="test_cap",
            source_root=str(tmp_path),
            git_head="abc123",
            git_remote_url="https://github.com/org/repo",
        )
        # The source file is this test file, not under tmp_path,
        # so path will be absolute (fallback behavior)
        assert entry is not None
        assert entry.capability == "test_cap"
        assert entry.git_head == "abc123"
        assert entry.start_line > 0
        assert entry.end_line >= entry.start_line
        assert "sample_func" in entry.entry_point

    def test_returns_none_for_builtin(self, tmp_path):
        # Built-in functions can't be inspected for source
        entry = resolve_source(
            func=len,
            capability_name="builtin",
            source_root=str(tmp_path),
            git_head="abc",
            git_remote_url=None,
        )
        assert entry is None


class TestGitHelpers:
    def test_get_git_head_in_repo(self, tmp_path):
        """Test git head in an actual git repo (may or may not be available)."""
        # This test runs from within the cogito repo, so git should work
        head = get_git_head(cwd=str(tmp_path))
        # tmp_path is not a git repo, so this should return "unknown"
        assert head == "unknown"

    def test_get_git_head_no_git(self):
        with patch("cogito.collector.subprocess.run", side_effect=FileNotFoundError):
            head = get_git_head()
            assert head == "unknown"

    def test_get_git_remote_url_no_repo(self, tmp_path):
        url = get_git_remote_url(cwd=str(tmp_path))
        assert url is None


class TestCollectRuntime:
    def test_basic_fields(self):
        import time

        rt = collect_runtime(start_time=time.monotonic() - 1.0)
        assert rt.status == "healthy"
        assert rt.pid > 0
        assert rt.uptime_seconds >= 0

    def test_to_dict(self):
        import time

        rt = collect_runtime(start_time=time.monotonic() - 1.0)
        d = rt.to_dict()
        assert "status" in d
        assert "pid" in d
        assert "uptime_seconds" in d

    def test_custom_health_status(self):
        import time

        rt = collect_runtime(
            start_time=time.monotonic(),
            health_status="degraded",
            last_error="test error",
        )
        assert rt.status == "degraded"
        assert rt.last_error == "test error"

    def test_runtime_includes_process_context(self):
        import time

        rt = collect_runtime(start_time=time.monotonic() - 1.0)
        assert rt.exe is not None
        assert rt.cmdline is not None
        assert rt.cwd is not None

    def test_runtime_exe_is_python(self):
        import time

        rt = collect_runtime(start_time=time.monotonic() - 1.0)
        # exe should contain 'python' regardless of psutil availability
        assert "python" in rt.exe.lower()

    def test_runtime_cwd_matches_os(self):
        import time

        rt = collect_runtime(start_time=time.monotonic() - 1.0)
        assert os.path.normcase(rt.cwd) == os.path.normcase(os.getcwd())

    def test_runtime_cmdline_is_tuple(self):
        import time

        rt = collect_runtime(start_time=time.monotonic() - 1.0)
        assert isinstance(rt.cmdline, tuple)
        assert len(rt.cmdline) > 0

    def test_runtime_to_dict_includes_process_context(self):
        import time

        rt = collect_runtime(start_time=time.monotonic() - 1.0)
        d = rt.to_dict()
        assert "exe" in d
        assert "cmdline" in d
        assert isinstance(d["cmdline"], list)
        assert "cwd" in d

    def test_runtime_fallback_without_psutil(self):
        import time

        with patch.dict("sys.modules", {"psutil": None}):
            rt = collect_runtime(start_time=time.monotonic() - 1.0)
            assert rt.exe == sys.executable
            assert rt.cmdline == tuple(sys.argv)
            assert os.path.normcase(rt.cwd) == os.path.normcase(os.getcwd())

    def test_to_dict_omits_none_process_context(self):
        from cogito.types import RuntimeStatus

        rt = RuntimeStatus(status="healthy", pid=1, uptime_seconds=0.0)
        d = rt.to_dict()
        assert "exe" not in d
        assert "cmdline" not in d
        assert "cwd" not in d
