"""Cogito decorators: @capability and @config.

These decorators annotate functions with reflection metadata.
They store metadata on the function object via __cogito_capability__
and __cogito_configs__ attributes, which the Reflector reads at
registration time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CapabilityMeta:
    """Metadata attached by @capability decorator."""

    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


_VALID_SOURCES = frozenset({"env", "file", "arg"})


@dataclass
class ConfigMeta:
    """Metadata attached by @config decorator."""

    key: str
    source: str = "env"
    source_path: str | None = None
    sensitive: bool = False
    required: bool = True

    def __post_init__(self) -> None:
        if self.source not in _VALID_SOURCES:
            raise ValueError(
                f"Invalid config source '{self.source}', "
                f"must be one of {sorted(_VALID_SOURCES)}"
            )


def capability(
    name: str,
    description: str,
    tools: list[str] | None = None,
    tags: list[str] | None = None,
) -> Callable:
    """Decorator that marks a function as a capability entry point.

    Usage::

        @reflect.capability(name="image_gen", description="Generate images")
        async def generate_image(...): ...

    The decorator stores a CapabilityMeta on the function.  Any @config
    decorators applied *below* this decorator (i.e., closer to the function
    definition) are automatically associated with this capability.
    """

    def decorator(func: Callable) -> Callable:
        meta = CapabilityMeta(
            name=name,
            description=description,
            tools=list(tools or []),
            tags=list(tags or []),
        )
        func.__cogito_capability__ = meta  # type: ignore[attr-defined]
        return func

    return decorator


def config(
    key: str,
    source: str = "env",
    source_path: str | None = None,
    sensitive: bool = False,
    required: bool = True,
) -> Callable:
    """Decorator that declares a configuration dependency.

    When stacked below @capability, the config is automatically
    associated with that capability.  When used standalone (no
    @capability above), it becomes a standalone config entry —
    use ``Reflector.declare_config()`` for that pattern instead.

    Usage::

        @reflect.capability(name="image_gen", description="...")
        @reflect.config("GEMINI_API_KEY", sensitive=True)
        @reflect.config("IMAGE_MODEL")
        async def generate_image(...): ...

    Decorator application order (bottom-up): config("IMAGE_MODEL")
    is applied first, then config("GEMINI_API_KEY"), then capability().
    """

    def decorator(func: Callable) -> Callable:
        meta = ConfigMeta(
            key=key,
            source=source,
            source_path=source_path,
            sensitive=sensitive,
            required=required,
        )
        # Accumulate configs on the function; capability decorator reads them
        if not hasattr(func, "__cogito_configs__"):
            func.__cogito_configs__ = []  # type: ignore[attr-defined]
        func.__cogito_configs__.append(meta)  # type: ignore[attr-defined]
        return func

    return decorator
