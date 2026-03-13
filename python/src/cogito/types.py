"""Cogito protocol response types.

All types are plain dataclasses with a to_dict() method for JSON serialization.
No external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Identity:
    """Level 0: Service identity."""

    name: str
    version: str
    description: str
    language: str | None = None
    port: int | None = None
    transport: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
        }
        if self.language is not None:
            d["language"] = self.language
        if self.port is not None:
            d["port"] = self.port
        if self.transport is not None:
            d["transport"] = self.transport
        return d


@dataclass(frozen=True)
class Capability:
    """Level 0: A single capability declaration."""

    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "description": self.description}
        if self.tools:
            d["tools"] = list(self.tools)
        if self.tags:
            d["tags"] = list(self.tags)
        return d


@dataclass(frozen=True)
class ConfigEntry:
    """Level 1: A configuration entry."""

    key: str
    capability: str | None
    source: str
    sensitive: bool
    required: bool
    status: str
    current_value: str | None = None
    source_path: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "key": self.key,
            "capability": self.capability,
            "source": self.source,
            "sensitive": self.sensitive,
            "required": self.required,
            "status": self.status,
            "current_value": self.current_value,
        }
        if self.source_path is not None:
            d["source_path"] = self.source_path
        return d


@dataclass(frozen=True)
class SourceEntry:
    """Level 2: Source code location for a capability."""

    capability: str
    module: str
    path: str
    entry_point: str
    start_line: int
    end_line: int
    git_head: str
    git_remote_url: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "capability": self.capability,
            "module": self.module,
            "path": self.path,
            "entry_point": self.entry_point,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "git_head": self.git_head,
        }
        if self.git_remote_url is not None:
            d["git_remote_url"] = self.git_remote_url
        return d


@dataclass(frozen=True)
class RuntimeStatus:
    """Level 3: Runtime health and metrics."""

    status: str
    pid: int
    uptime_seconds: float
    metrics: dict = field(default_factory=dict)
    last_error: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "status": self.status,
            "pid": self.pid,
            "uptime_seconds": self.uptime_seconds,
        }
        if self.metrics:
            d["metrics"] = dict(self.metrics)
        if self.last_error is not None:
            d["last_error"] = self.last_error
        return d
