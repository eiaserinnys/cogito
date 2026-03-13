"""Cogito — Service reflection protocol for AI agent orchestrators.

Public API::

    from cogito import Reflector

    reflect = Reflector(
        name="my-service",
        description="My service description",
        version_from="git",
        source_root="src/my_service",
    )

    @reflect.capability(name="my_cap", description="...")
    @reflect.config("MY_API_KEY", sensitive=True)
    async def my_func(...): ...
"""

from cogito.reflector import Reflector

__all__ = ["Reflector"]
