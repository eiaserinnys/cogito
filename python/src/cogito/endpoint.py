"""FastAPI endpoint for the Cogito reflection protocol.

Usage::

    from fastapi import FastAPI
    from cogito import Reflector
    from cogito.endpoint import mount_cogito

    app = FastAPI()
    reflect = Reflector(name="my-service", description="...")
    mount_cogito(app, reflect)

This mounts the following routes:
    GET /reflect              → Level 0 (identity + capabilities)
    GET /reflect/config       → Level 1 (all configs)
    GET /reflect/config/{cap} → Level 1 (configs for a specific capability)
    GET /reflect/source       → Level 2 (all sources)
    GET /reflect/source/{cap} → Level 2 (sources for a specific capability)
    GET /reflect/runtime      → Level 3 (runtime status)
    GET /reflect/full         → Full response (all levels)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from cogito.reflector import Reflector


def mount_cogito(app: "FastAPI", reflect: "Reflector", prefix: str = "/reflect") -> None:
    """Mount cogito reflection endpoints on a FastAPI app.

    Args:
        app: A FastAPI application instance.
        reflect: The Reflector instance to serve.
        prefix: URL prefix for reflection routes (default: ``/reflect``).
    """
    try:
        from fastapi import APIRouter
        from fastapi.responses import JSONResponse
    except ImportError as e:
        raise ImportError(
            "FastAPI is required for cogito endpoints. "
            "Install with: pip install cogito[fastapi]"
        ) from e

    router = APIRouter(prefix=prefix, tags=["cogito"])

    @router.get("")
    async def reflect_level0() -> JSONResponse:
        """Level 0: identity + capabilities."""
        return JSONResponse(content=reflect.get_level0())

    @router.get("/config")
    async def reflect_config_all() -> JSONResponse:
        """Level 1: all configuration entries."""
        return JSONResponse(content=reflect.get_level1())

    @router.get("/config/{capability_name}")
    async def reflect_config_by_cap(capability_name: str) -> JSONResponse:
        """Level 1: configuration entries for a specific capability."""
        return JSONResponse(content=reflect.get_level1(capability_name))

    @router.get("/source")
    async def reflect_source_all() -> JSONResponse:
        """Level 2: all source locations."""
        return JSONResponse(content=reflect.get_level2())

    @router.get("/source/{capability_name}")
    async def reflect_source_by_cap(capability_name: str) -> JSONResponse:
        """Level 2: source locations for a specific capability."""
        return JSONResponse(content=reflect.get_level2(capability_name))

    @router.get("/runtime")
    async def reflect_runtime() -> JSONResponse:
        """Level 3: runtime status."""
        return JSONResponse(content=reflect.get_level3())

    @router.get("/full")
    async def reflect_full() -> JSONResponse:
        """Full response: all levels combined."""
        return JSONResponse(content=reflect.get_full())

    # Include router in the app
    app.include_router(router)  # type: ignore[attr-defined]
