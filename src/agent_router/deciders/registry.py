"""Backend registry: which deciders can run here, and how to build one for a catalog."""

from __future__ import annotations

import importlib.util
import os

from agent_router.core.catalog import Catalog
from agent_router.deciders.base import Decider

BACKENDS = ("local", "semantic-router", "jev")


def available_backends() -> dict[str, bool]:
    """Availability without network calls: package importable / API key present."""
    return {
        "local": True,
        "semantic-router": importlib.util.find_spec("semantic_router") is not None,
        "jev": bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("TYPESAFE_API_KEY")),
    }


def make_decider(name: str, catalog: Catalog) -> Decider:
    if name == "local":
        from agent_router.deciders.local import LocalJevDecider

        return LocalJevDecider(native_examples=catalog.native_examples)
    if name == "semantic-router":
        from agent_router.deciders.semantic_router_backend import SemanticRouterDecider

        return SemanticRouterDecider(native_examples=catalog.native_examples)
    if name == "jev":
        from agent_router.deciders.typesafe import TypeSafeJevDecider

        return TypeSafeJevDecider()
    raise ValueError(f"unknown decider backend {name!r}; expected one of {BACKENDS}")
