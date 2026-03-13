# cogito

Service reflection protocol for AI agent orchestrators.

Each service describes itself — its identity, capabilities, configuration,
source locations, and runtime status — through a standard protocol.
An orchestrator (e.g. soulstream) composes these self-descriptions to
build context for AI agent sessions.

## Why

Static documentation about services goes stale.  With cogito, each
service is the canonical source of truth about itself.  The orchestrator
simply asks "what are you?" and assembles the answers.

## Protocol Levels

| Level | What | When |
|-------|------|------|
| 0 | Identity + capabilities | Always |
| 1 | Configuration status | On request |
| 2 | Source locations | On request |
| 3 | Runtime health | On request |

## Quick Start (Python)

```bash
pip install -e ./python              # core only
pip install -e ./python[fastapi]     # with HTTP endpoint
pip install -e ./python[runtime]     # with psutil metrics
pip install -e ./python[dev]         # everything for development
```

```python
from cogito import Reflector

reflect = Reflector(
    name="my-service",
    description="My awesome service",
    version_from="git",           # or "1.0.0"
    source_root="src/my_service",
)

@reflect.capability(
    name="image_generation",
    description="Generate images with AI",
    tools=["generate_image"],
)
@reflect.config("API_KEY", sensitive=True)
@reflect.config("MODEL_NAME")
async def generate_image(prompt: str):
    ...
```

### HTTP Endpoint

```python
from fastapi import FastAPI
from cogito.endpoint import mount_cogito

app = FastAPI()
mount_cogito(app, reflect)
# GET /reflect         → Level 0
# GET /reflect/config  → Level 1
# GET /reflect/source  → Level 2
# GET /reflect/runtime → Level 3
# GET /reflect/full    → All levels
```

### Composition Manifest

```yaml
services:
  - name: my-service
    endpoint: http://localhost:8080/reflect
    type: internal
  - name: external-tool
    type: external
    static:
      identity:
        name: external-tool
        description: "Third-party tool"
      capabilities:
        - name: search
          description: "Full-text search"
```

```python
from cogito.manifest import compose
results = await compose("manifest.yaml")
```

## Schema

Protocol schemas are in `protocol/`:
- `cogito.schema.json` — Response schema (Level 0-3)
- `manifest.schema.json` — Composition manifest schema

## License

MIT
