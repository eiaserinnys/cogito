"""Tests for the FastAPI endpoint mount."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from cogito import Reflector
from cogito.endpoint import mount_cogito


@pytest.fixture
def app():
    """Create a FastAPI app with cogito endpoints mounted."""
    from fastapi import FastAPI

    app = FastAPI()
    reflect = Reflector(
        name="endpoint-test",
        description="Test service for endpoint",
        version_from="0.1.0",
        source_root=".",
    )

    @reflect.capability(
        name="greet",
        description="Greeting capability",
        tools=["say_hello"],
    )
    @reflect.config("GREET_LANG")
    async def greet():
        pass

    mount_cogito(app, reflect)
    return app


@pytest.fixture
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestLevel0Endpoint:
    @pytest.mark.asyncio
    async def test_get_reflect(self, client):
        resp = await client.get("/reflect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["identity"]["name"] == "endpoint-test"
        assert len(data["capabilities"]) == 1
        assert data["capabilities"][0]["name"] == "greet"


class TestLevel1Endpoint:
    @pytest.mark.asyncio
    async def test_get_all_configs(self, client):
        resp = await client.get("/reflect/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "configs" in data
        assert len(data["configs"]) >= 1

    @pytest.mark.asyncio
    async def test_get_config_by_capability(self, client):
        resp = await client.get("/reflect/config/greet")
        assert resp.status_code == 200
        data = resp.json()
        configs = data["configs"]
        assert all(c["capability"] == "greet" for c in configs)


class TestLevel2Endpoint:
    @pytest.mark.asyncio
    async def test_get_all_sources(self, client):
        resp = await client.get("/reflect/source")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        assert len(data["sources"]) >= 1

    @pytest.mark.asyncio
    async def test_get_source_by_capability(self, client):
        resp = await client.get("/reflect/source/greet")
        assert resp.status_code == 200
        data = resp.json()
        assert all(s["capability"] == "greet" for s in data["sources"])


class TestLevel3Endpoint:
    @pytest.mark.asyncio
    async def test_get_runtime(self, client):
        resp = await client.get("/reflect/runtime")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "pid" in data


class TestFullEndpoint:
    @pytest.mark.asyncio
    async def test_get_full(self, client):
        resp = await client.get("/reflect/full")
        assert resp.status_code == 200
        data = resp.json()
        assert "identity" in data
        assert "capabilities" in data
        assert "configs" in data
        assert "sources" in data
        assert "runtime" in data
