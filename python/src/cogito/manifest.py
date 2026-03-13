"""Composition manifest loader.

Loads a YAML/JSON manifest that declares which services participate
in a composition, fetches live reflection data from internal services,
and merges in static data for external services.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Timeout per internal service HTTP request (seconds)
_SERVICE_TIMEOUT = 3.0


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Load a manifest file (YAML or JSON).

    Args:
        path: Path to the manifest file.

    Returns:
        Parsed manifest as a dict.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        ValueError: If the file format is unsupported.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Manifest not found: {p}")

    text = p.read_text(encoding="utf-8")

    if p.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:
            raise ImportError(
                "PyYAML is required to load YAML manifests. "
                "Install with: pip install pyyaml"
            ) from e
        result = yaml.safe_load(text)
    elif p.suffix == ".json":
        result = json.loads(text)
    else:
        raise ValueError(f"Unsupported manifest format: {p.suffix}")

    if not isinstance(result, dict):
        raise ValueError(
            f"Invalid manifest: expected dict, got {type(result).__name__}"
        )
    return result


async def fetch_service(endpoint: str) -> dict[str, Any]:
    """Fetch reflection data from a single internal service.

    Args:
        endpoint: The ``/reflect`` endpoint URL.

    Returns:
        The JSON response as a dict, or an error stub on failure.
    """
    if httpx is None:
        raise ImportError(
            "httpx is required for fetching service data. "
            "Install with: pip install httpx"
        )

    try:
        async with httpx.AsyncClient(timeout=_SERVICE_TIMEOUT) as client:
            resp = await client.get(endpoint)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", endpoint, e)
        # Extract service name from endpoint path (best effort)
        return {
            "identity": {"name": endpoint, "status": "unreachable"},
            "error": str(e),
        }


async def compose(manifest_path: str | Path) -> list[dict[str, Any]]:
    """Load manifest and compose reflection data from all services.

    For internal services, fetches live data from their /reflect endpoints.
    For external services, includes the static data from the manifest.
    On HTTP failure, includes a partial result with error info.

    Args:
        manifest_path: Path to the composition manifest file.

    Returns:
        List of service reflection data dicts.
    """
    manifest = load_manifest(manifest_path)
    services = manifest.get("services", [])

    async def _resolve(svc: dict[str, Any]) -> dict[str, Any]:
        svc_type = svc.get("type", "internal")
        name = svc.get("name", "unknown")

        if svc_type == "external":
            return svc.get("static", {})

        endpoint = svc.get("endpoint", "")
        if not endpoint:
            return {
                "identity": {"name": name, "status": "unreachable"},
                "error": "No endpoint configured",
            }
        return await fetch_service(endpoint)

    return list(await asyncio.gather(*[_resolve(svc) for svc in services]))
