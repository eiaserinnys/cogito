"""Reflector — the core class that collects and serves reflection data.

A Reflector instance is the single point of registration for capabilities,
configs, and their associated functions.  It delegates data collection to
the ``collector`` module and type construction to ``types``.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from cogito.collector import (
    build_config_entry,
    collect_runtime,
    get_git_head,
    get_git_remote_url,
    resolve_source,
)
from cogito.decorators import CapabilityMeta, ConfigMeta
from cogito.decorators import capability as _capability_decorator
from cogito.decorators import config as _config_decorator
from cogito.types import Capability, ConfigEntry, Identity, SourceEntry

logger = logging.getLogger(__name__)


class Reflector:
    """Collects and serves service reflection data.

    Args:
        name: Service identifier.
        description: Human-readable service description.
        version_from: ``"git"`` to auto-detect from git HEAD, or an
            explicit version string.
        source_root: Project root directory (where pyproject.toml lives).
            Used as the base for computing relative source paths.
        language: Implementation language (default ``"python"``).
        port: Listening port number.
        transport: Transport protocol (e.g. ``"sse"``, ``"stdio"``).
    """

    def __init__(
        self,
        name: str,
        description: str,
        version_from: str = "git",
        source_root: str = ".",
        language: str = "python",
        port: int | None = None,
        transport: str | None = None,
    ) -> None:
        self._name = name
        self._description = description
        self._language = language
        self._port = port
        self._transport = transport

        # Resolve source root to absolute path
        self._source_root = str(Path(source_root).resolve())

        # Git info (cached once)
        if version_from == "git":
            self._version = get_git_head(cwd=self._source_root)
            if self._version == "unknown":
                logger.warning(
                    "git rev-parse HEAD failed for %s; version set to 'unknown'",
                    name,
                )
        else:
            self._version = version_from

        self._git_remote_url = get_git_remote_url(cwd=self._source_root)

        # Runtime health tracking
        self._start_time = time.monotonic()
        self._health_status = "healthy"
        self._last_error: str | None = None

        # Registry: capability_name -> (CapabilityMeta, func, [ConfigMeta])
        self._capabilities: dict[str, tuple[CapabilityMeta, Callable | None, list[ConfigMeta]]] = {}

        # Standalone configs (not tied to a capability)
        self._standalone_configs: list[ConfigMeta] = []

    @property
    def identity(self) -> Identity:
        return Identity(
            name=self._name,
            version=self._version,
            description=self._description,
            language=self._language,
            port=self._port,
            transport=self._transport,
        )

    def capability(
        self,
        name: str,
        description: str,
        tools: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Callable:
        """Decorator that registers a capability.

        Reads any ``@config`` decorators already applied to the function
        (stacked below this decorator) and associates them with this
        capability.
        """

        def decorator(func: Callable) -> Callable:
            # Apply the raw decorator to store metadata on func
            decorated = _capability_decorator(name, description, tools, tags)(func)

            # Collect any configs already attached by @config below
            configs: list[ConfigMeta] = getattr(decorated, "__cogito_configs__", [])
            cap_meta: CapabilityMeta = decorated.__cogito_capability__  # type: ignore[attr-defined]

            self._register_capability(name, cap_meta, decorated, list(configs))
            return decorated

        return decorator

    def _register_capability(
        self,
        name: str,
        meta: CapabilityMeta,
        func: Callable | None,
        configs: list[ConfigMeta],
    ) -> None:
        """Register a capability, raising on name collision."""
        if name in self._capabilities:
            raise ValueError(
                f"Capability '{name}' is already registered. "
                f"Each capability name must be unique within a Reflector."
            )
        self._capabilities[name] = (meta, func, configs)

    def config(
        self,
        key: str,
        source: str = "env",
        source_path: str | None = None,
        sensitive: bool = False,
        required: bool = True,
    ) -> Callable:
        """Decorator that declares a configuration dependency.

        Should be stacked below ``@capability``.  The capability decorator
        reads configs from the function when it runs.
        """
        return _config_decorator(
            key=key,
            source=source,
            source_path=source_path,
            sensitive=sensitive,
            required=required,
        )

    def declare_capability(
        self,
        name: str,
        description: str,
        tools: list[str] | None = None,
        tags: list[str] | None = None,
        configs: list[dict[str, Any]] | None = None,
    ) -> None:
        """Declaratively register a capability (no function)."""
        meta = CapabilityMeta(
            name=name,
            description=description,
            tools=list(tools or []),
            tags=list(tags or []),
        )
        config_metas = []
        for cfg in (configs or []):
            config_metas.append(
                ConfigMeta(
                    key=cfg["key"],
                    source=cfg.get("source", "env"),
                    source_path=cfg.get("source_path"),
                    sensitive=cfg.get("sensitive", False),
                    required=cfg.get("required", True),
                )
            )
        self._register_capability(name, meta, None, config_metas)

    def report_error(self, error: str) -> None:
        """Report an error, setting health to degraded."""
        self._last_error = error
        self._health_status = "degraded"

    def report_healthy(self) -> None:
        """Clear error state, setting health to healthy."""
        self._last_error = None
        self._health_status = "healthy"

    def declare_config(
        self,
        key: str,
        source: str = "env",
        source_path: str | None = None,
        sensitive: bool = False,
        required: bool = True,
    ) -> None:
        """Declare a standalone config (not tied to any capability)."""
        self._standalone_configs.append(
            ConfigMeta(
                key=key,
                source=source,
                source_path=source_path,
                sensitive=sensitive,
                required=required,
            )
        )

    def get_capabilities(self) -> list[Capability]:
        """Return all registered capabilities."""
        result = []
        for cap_meta, _, _ in self._capabilities.values():
            result.append(
                Capability(
                    name=cap_meta.name,
                    description=cap_meta.description,
                    tools=cap_meta.tools,
                    tags=cap_meta.tags,
                )
            )
        return result

    def get_configs(self, capability_name: str | None = None) -> list[ConfigEntry]:
        """Return config entries, optionally filtered by capability.

        Args:
            capability_name: If provided, return only configs for this
                capability.  If None, return all configs.
        """
        entries: list[ConfigEntry] = []

        for cap_name, (_, _, config_metas) in self._capabilities.items():
            if capability_name is not None and cap_name != capability_name:
                continue
            for cfg in config_metas:
                entries.append(
                    build_config_entry(
                        key=cfg.key,
                        capability=cap_name,
                        source=cfg.source,
                        source_path=cfg.source_path,
                        sensitive=cfg.sensitive,
                        required=cfg.required,
                    )
                )

        # Standalone configs (only when not filtering by capability)
        if capability_name is None:
            for cfg in self._standalone_configs:
                entries.append(
                    build_config_entry(
                        key=cfg.key,
                        capability=None,
                        source=cfg.source,
                        source_path=cfg.source_path,
                        sensitive=cfg.sensitive,
                        required=cfg.required,
                    )
                )

        return entries

    def get_sources(self, capability_name: str | None = None) -> list[SourceEntry]:
        """Return source entries, optionally filtered by capability."""
        entries: list[SourceEntry] = []

        for cap_name, (_, func, _) in self._capabilities.items():
            if capability_name is not None and cap_name != capability_name:
                continue
            if func is None:
                continue
            entry = resolve_source(
                func=func,
                capability_name=cap_name,
                source_root=self._source_root,
                git_head=self._version,
                git_remote_url=self._git_remote_url,
            )
            if entry is not None:
                entries.append(entry)

        return entries

    def get_runtime(self) -> dict:
        """Return runtime status."""
        return collect_runtime(
            start_time=self._start_time,
            health_status=self._health_status,
            last_error=self._last_error,
        ).to_dict()

    def get_level0(self) -> dict:
        """Level 0: identity + capabilities."""
        return {
            "identity": self.identity.to_dict(),
            "capabilities": [c.to_dict() for c in self.get_capabilities()],
        }

    def get_level1(self, capability_name: str | None = None) -> dict:
        """Level 1: config entries."""
        return {
            "configs": [c.to_dict() for c in self.get_configs(capability_name)],
        }

    def get_level2(self, capability_name: str | None = None) -> dict:
        """Level 2: source locations."""
        return {
            "sources": [s.to_dict() for s in self.get_sources(capability_name)],
        }

    def get_level3(self) -> dict:
        """Level 3: runtime status."""
        return self.get_runtime()

    def get_full(self) -> dict:
        """Full response: all levels combined."""
        result = self.get_level0()
        result["configs"] = self.get_level1()["configs"]
        result["sources"] = self.get_level2()["sources"]
        result["runtime"] = self.get_level3()
        return result
