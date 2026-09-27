"""Backend registry: which deciders can run here, and how to build one for a catalog."""

from __future__ import annotations

import importlib.util
import os

from agent_router.core.catalog import Catalog
from agent_router.deciders.base import Decider

BACKENDS = ("cascade", "local", "semantic-router", "jev", "logprob", "openrouter", "anyjev")


def available_backends() -> dict[str, bool]:
    """Availability without network calls: package importable / API key present."""
    jev = bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("TYPESAFE_API_KEY"))
    return {
        "cascade": jev,
        "local": True,
        "semantic-router": importlib.util.find_spec("semantic_router") is not None,
        "jev": jev,
        "logprob": importlib.util.find_spec("llama_cpp") is not None,
        "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
        "anyjev": importlib.util.find_spec("anyjev") is not None,
    }


def default_backend() -> str:
    """The default decision path: the local -> Jev cascade when Jev is reachable (an API key
    is set), else the offline local classifier."""
    return "cascade" if available_backends().get("cascade") else "local"


def _local(catalog: Catalog) -> Decider:
    from agent_router.deciders.local import LocalJevDecider

    return LocalJevDecider(native_examples=catalog.native_examples, catalog_version=catalog.version)


def make_decider(name: str, catalog: Catalog) -> Decider:
    if name == "cascade":
        from agent_router.deciders.cascade import CascadeDecider, load_cascade_calibration
        from agent_router.deciders.local import embedder_id
        from agent_router.deciders.typesafe import TypeSafeJevDecider

        primary = _local(catalog)
        cal = load_cascade_calibration(
            catalog_version=catalog.version,
            embedder=embedder_id(getattr(primary, "embedder", None)),
        )
        if cal is None:
            return CascadeDecider(primary, TypeSafeJevDecider())
        return CascadeDecider(
            primary, TypeSafeJevDecider(), cal["native_gate"], threshold=cal["threshold"]
        )
    if name == "local":
        return _local(catalog)
    if name == "semantic-router":
        from agent_router.deciders.semantic_router_backend import SemanticRouterDecider

        return SemanticRouterDecider(native_examples=catalog.native_examples)
    if name == "jev":
        from agent_router.deciders.typesafe import TypeSafeJevDecider

        return TypeSafeJevDecider()
    if name in ("logprob", "openrouter"):
        from agent_router.deciders.logprob import LogprobJevDecider

        return LogprobJevDecider(engine="llama_cpp" if name == "logprob" else "openai")
    if name == "anyjev":
        from agent_router.deciders.anyjev_backend import AnyJevDecider

        return AnyJevDecider()
    raise ValueError(f"unknown decider backend {name!r}; expected one of {BACKENDS}")
