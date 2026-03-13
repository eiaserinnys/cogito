"""Tests for @capability and @config decorators."""

from __future__ import annotations

import pytest

from cogito.decorators import CapabilityMeta, ConfigMeta, capability, config


class TestCapabilityDecorator:
    def test_attaches_metadata(self):
        @capability(name="test_cap", description="Test capability")
        def func():
            pass

        assert hasattr(func, "__cogito_capability__")
        meta = func.__cogito_capability__
        assert isinstance(meta, CapabilityMeta)
        assert meta.name == "test_cap"
        assert meta.description == "Test capability"
        assert meta.tools == []
        assert meta.tags == []

    def test_with_tools_and_tags(self):
        @capability(
            name="rich_cap",
            description="Rich",
            tools=["tool_a", "tool_b"],
            tags=["tag1"],
        )
        def func():
            pass

        meta = func.__cogito_capability__
        assert meta.tools == ["tool_a", "tool_b"]
        assert meta.tags == ["tag1"]

    def test_preserves_function(self):
        @capability(name="cap", description="test")
        def my_func(x: int) -> int:
            return x + 1

        assert my_func(5) == 6


class TestConfigDecorator:
    def test_attaches_config_list(self):
        @config("MY_KEY", sensitive=True)
        def func():
            pass

        assert hasattr(func, "__cogito_configs__")
        configs = func.__cogito_configs__
        assert len(configs) == 1
        assert configs[0].key == "MY_KEY"
        assert configs[0].sensitive is True

    def test_multiple_configs_accumulate(self):
        @config("KEY_A")
        @config("KEY_B", sensitive=True)
        def func():
            pass

        configs = func.__cogito_configs__
        assert len(configs) == 2
        keys = {c.key for c in configs}
        assert keys == {"KEY_A", "KEY_B"}

    def test_config_defaults(self):
        @config("SIMPLE_KEY")
        def func():
            pass

        cfg = func.__cogito_configs__[0]
        assert cfg.source == "env"
        assert cfg.source_path is None
        assert cfg.sensitive is False
        assert cfg.required is True


class TestConfigValidation:
    def test_invalid_source_raises(self):
        with pytest.raises(ValueError, match="Invalid config source"):

            @config("KEY", source="database")
            def func():
                pass

    def test_valid_sources(self):
        for src in ("env", "file", "arg"):

            @config("KEY", source=src)
            def func():
                pass

            assert func.__cogito_configs__[-1].source == src


class TestDecoratorStacking:
    """Test that @capability reads configs from @config below it."""

    def test_capability_reads_configs(self):
        @capability(name="stacked", description="Stacked test")
        @config("API_KEY", sensitive=True)
        @config("MODEL_NAME")
        def func():
            pass

        # capability should be on func
        assert hasattr(func, "__cogito_capability__")
        cap = func.__cogito_capability__
        assert cap.name == "stacked"

        # configs should also be on func
        configs = func.__cogito_configs__
        assert len(configs) == 2

    def test_decorator_order_matters(self):
        """Bottom-up: config("B") applied first, then config("A"), then capability."""

        @capability(name="ordered", description="Order test")
        @config("KEY_A")
        @config("KEY_B")
        def func():
            pass

        configs = func.__cogito_configs__
        # KEY_B is applied first (closest to func), KEY_A second
        assert configs[0].key == "KEY_B"
        assert configs[1].key == "KEY_A"
