"""Demo server: Playground (route one step), Live agent (SSE timeline) and audit Replay.

``create_app(audit_dir)`` builds the FastAPI app; ``main(port)`` serves it on 127.0.0.1.

API
---
``GET  /api/catalog``            catalog entries, the ``none`` option, default threshold/mode
``GET  /api/backends``           ``available_backends()`` as a list (read per request)
``POST /api/route``              ``{text, point, tool_name?, tool_input?, backend, mode?,
                                 threshold?}`` -> ``{decision, result, options, hint,
                                 latency_ms, state, threshold, mode, backend}``; stateless
``GET  /api/run``                ``?prompt=&mode=&backend=`` -> ``text/event-stream`` of the
                                 timeline events (see ``adapters.claude_sdk``), framed by
                                 ``session`` (first) and ``done`` (last)
``GET  /api/audit/sessions``     audit JSONL files, newest first
``GET  /api/audit/{session}``    one session's records (bad lines skipped)

Deciders are built once per backend name and serialised with a lock; every route call
runs in the threadpool so network-backed deciders never block the event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import shutil
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import anyio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from agent_router.core.audit import AuditLog
from agent_router.core.catalog import Catalog, CatalogEntry, load_catalog
from agent_router.core.config import MODES, RouterConfig
from agent_router.core.hints import render_deny, render_hint
from agent_router.core.router import NONE_OPTION, Router, build_state
from agent_router.core.types import NONE_ID, ChoiceResult, HookPoint, OptionSpec, RouterEvent
from agent_router.deciders import registry

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AUDIT_DIR = Path(".agent-router/audit")
SAMPLE_AUDIT_DIR = REPO_ROOT / "audit"
DEFAULT_BACKEND = "local"
PLAYGROUND_SESSION = "playground"
SKILL_TOOL = "Skill"
_SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

Listener = Callable[[dict[str, Any]], None]
Runner = Callable[[str, Router, Path, Listener], Awaitable[Any]]


class RouteRequest(BaseModel):
    text: str = Field(default="", max_length=20_000)
    point: str = "prompt"
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    backend: str = DEFAULT_BACKEND
    mode: str | None = None
    threshold: float | None = None


class _LockedDecider:
    """Serialises ``decide`` on one shared decider (caches inside are not thread-safe)."""

    def __init__(self, decider: Any) -> None:
        self._decider = decider
        self._lock = threading.Lock()
        self.name = getattr(decider, "name", "")

    def decide(self, state: str, options: dict[str, OptionSpec]) -> ChoiceResult:
        with self._lock:
            return self._decider.decide(state, options)


def _entry_json(e: CatalogEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "kind": e.kind,
        "name": e.name,
        "project": e.project,
        "license": e.license,
        "url": e.url,
        "what": e.what,
        "target": e.target,
        "points": [str(p) for p in e.points],
        "replaces": list(e.replaces),
        "not_for": list(e.not_for),
        "examples": list(e.examples),
    }


NONE_JSON = {
    "id": NONE_ID,
    "kind": "none",
    "name": "Native path",
    "project": "the agent's own tools",
    "what": NONE_OPTION.what,
}


def _option_json(e: CatalogEntry) -> dict[str, Any]:
    return {
        k: v for k, v in _entry_json(e).items() if k in ("id", "kind", "name", "project", "what")
    }


def _default_runner() -> Runner:
    from agent_router.agent import run_agent

    return run_agent


def _prepare_workspace() -> Path:
    from agent_router.agent import prepare_workspace

    return prepare_workspace()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:  # a line still being written during a live run
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def create_app(
    audit_dir: Path | None = None,
    *,
    runner: Runner | None = None,
    catalog: Catalog | None = None,
) -> FastAPI:
    """The demo app. ``runner`` defaults to ``agent_router.agent.run_agent`` (tests inject one)."""
    audit_root = Path(audit_dir) if audit_dir is not None else DEFAULT_AUDIT_DIR
    # With the default location, the committed sample session is offered for replay too.
    read_dirs = [audit_root] + ([SAMPLE_AUDIT_DIR] if audit_dir is None else [])
    cat = catalog if catalog is not None else load_catalog()
    base_config = RouterConfig.from_env()
    deciders: dict[str, _LockedDecider] = {}
    deciders_lock = threading.Lock()

    app = FastAPI(title="agent-router demo")

    # -- helpers --------------------------------------------------------------

    def check_backend(name: str) -> None:
        available = registry.available_backends()
        if name not in available:
            raise HTTPException(400, f"unknown backend {name!r}; known: {sorted(available)}")
        if not available[name]:
            raise HTTPException(
                400, f"backend {name!r} is not available here (missing package or API key)"
            )

    def decider_for(name: str) -> _LockedDecider:
        with deciders_lock:
            if name not in deciders:
                deciders[name] = _LockedDecider(registry.make_decider(name, cat))
            return deciders[name]

    def config_for(mode: str | None, threshold: float | None) -> RouterConfig:
        mode = mode if mode is not None else base_config.mode
        if mode not in MODES:
            raise HTTPException(400, f"mode must be one of {MODES}")
        thr = threshold if threshold is not None else base_config.threshold
        if not 0.0 <= thr <= 1.0:
            raise HTTPException(400, "threshold must be in [0, 1]")
        return RouterConfig(mode=mode, threshold=thr)  # type: ignore[arg-type]

    def point_of(raw: str) -> HookPoint:
        try:
            return HookPoint(raw)
        except ValueError:
            raise HTTPException(
                400, f"point must be one of {[str(p) for p in HookPoint]}"
            ) from None

    def find_session(name: str) -> Path:
        if not _SESSION_RE.match(name):
            raise HTTPException(400, "invalid session name")
        for d in read_dirs:
            path = d / f"{name}.jsonl"
            if path.is_file():
                return path
        raise HTTPException(404, f"no audit session {name!r}")

    def restore_hint(rec: dict[str, Any]) -> dict[str, Any]:
        """The audit keeps 300 chars of the hint; re-render the full templated text."""
        rec = dict(rec)
        rec["hint_restored"] = False
        hint, entry_id = rec.get("hint"), rec.get("entry_id")
        entry = cat.get(entry_id) if isinstance(entry_id, str) else None
        if not hint or entry is None:
            return rec
        try:
            point = HookPoint(rec.get("point"))
        except ValueError:
            return rec
        if rec.get("action") == "enforce":
            full = render_deny(entry, str(rec.get("tool_name") or ""))
        else:
            prob = float((rec.get("probabilities") or {}).get(entry.id, 0.0))
            full = render_hint(entry, point, prob)
        if full != hint and full.startswith(hint):
            rec["hint"] = full
            rec["hint_restored"] = True
        return rec

    # -- routes ---------------------------------------------------------------

    @app.get("/api/catalog")
    def get_catalog() -> dict[str, Any]:
        return {
            "version": cat.version,
            "entries": [_entry_json(e) for e in cat.entries],
            "none": NONE_JSON,
            "native_examples": list(cat.native_examples),
            "threshold": base_config.threshold,
            "mode": base_config.mode,
        }

    @app.get("/api/backends")
    def get_backends() -> dict[str, Any]:
        available = registry.available_backends()
        return {
            "backends": [{"name": k, "available": bool(v)} for k, v in available.items()],
            "default": DEFAULT_BACKEND,
        }

    @app.post("/api/route")
    def post_route(req: RouteRequest) -> dict[str, Any]:
        # sync def: FastAPI runs it in the threadpool, so jev/openrouter never block the loop
        point = point_of(req.point)
        config = config_for(req.mode, req.threshold)
        tool_name = req.tool_name or None
        if point == HookPoint.SKILL and not tool_name:
            tool_name = SKILL_TOOL
        if point == HookPoint.TOOL and not tool_name:
            raise HTTPException(400, "tool_name is required at the tool hook point")
        check_backend(req.backend)
        try:
            decider = decider_for(req.backend)
        except Exception as exc:
            raise HTTPException(503, f"could not start backend {req.backend!r}: {exc}") from exc
        event = RouterEvent(
            point=point,
            session_id=PLAYGROUND_SESSION,
            turn_id=1,
            text=req.text,
            tool_name=tool_name if point != HookPoint.PROMPT else None,
            tool_input=req.tool_input if point != HookPoint.PROMPT else None,
        )
        router = Router(cat, decider, config, AuditLog(None))  # fresh: no dedupe across calls
        start = time.perf_counter()
        decision = router.route(event)
        latency = (time.perf_counter() - start) * 1000.0
        eligible = cat.eligible(point, event.tool_name)
        res = decision.result
        return {
            "decision": {
                "action": str(decision.action),
                "reason": decision.reason,
                "entry_id": decision.entry_id,
            },
            "result": None
            if res is None
            else {
                "choice": res.choice,
                "probabilities": {k: float(v) for k, v in res.probabilities.items()},
                "confidence": float(res.confidence),
                "backend": res.backend,
                "latency_ms": float(res.latency_ms),
            },
            "options": [_option_json(e) for e in eligible] + [NONE_JSON],
            "hint": decision.hint,
            "latency_ms": latency,
            "state": build_state(event),
            "point": str(point),
            "tool_name": event.tool_name,
            "threshold": config.threshold,
            "mode": config.mode,
            "backend": req.backend,
        }

    @app.get("/api/run")
    async def get_run(
        request: Request, prompt: str, mode: str = "advisory", backend: str = DEFAULT_BACKEND
    ) -> StreamingResponse:
        # A GET that starts an agent with Bash: refuse requests other sites trigger.
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "cross-site requests may not start the agent")
        if not prompt.strip():
            raise HTTPException(400, "prompt is empty")
        config = config_for(mode, None)
        check_backend(backend)
        try:
            decider = await run_in_threadpool(decider_for, backend)
        except Exception as exc:
            raise HTTPException(503, f"could not start backend {backend!r}: {exc}") from exc
        session = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
        audit_path = audit_root / f"{session}.jsonl"
        router = Router(cat, decider, config, AuditLog(audit_path))
        run = runner if runner is not None else _default_runner()
        return StreamingResponse(
            _stream(run, prompt, router, session, config, backend),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/audit/sessions")
    def get_sessions() -> dict[str, Any]:
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for d in read_dirs:
            if not d.is_dir():
                continue
            for path in d.glob("*.jsonl"):
                if path.stem in seen or not _SESSION_RE.match(path.stem):
                    continue
                seen.add(path.stem)
                try:
                    records = _read_jsonl(path)
                except OSError:
                    continue
                first = records[0] if records else {}
                rows.append(
                    {
                        "session": path.stem,
                        "records": len(records),
                        "mtime": path.stat().st_mtime,
                        "first_text": first.get("text"),
                        "mode": (first.get("thresholds") or {}).get("mode"),
                        "backend": first.get("backend"),
                        "sample": d != audit_root,
                    }
                )
        rows.sort(key=lambda r: r["mtime"], reverse=True)
        return {"sessions": rows}

    @app.get("/api/audit/{session}")
    def get_session(session: str) -> dict[str, Any]:
        path = find_session(session)
        return {"session": session, "records": [restore_hint(r) for r in _read_jsonl(path)]}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def _stream(
    run: Runner,
    prompt: str,
    router: Router,
    session: str,
    config: RouterConfig,
    backend: str,
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def on_event(event: dict[str, Any]) -> None:
        # safe from the loop thread and from worker threads alike
        loop.call_soon_threadsafe(queue.put_nowait, event)

    workspace = await run_in_threadpool(_prepare_workspace)

    async def drive() -> None:
        try:
            await run(prompt, router, workspace, on_event)
        except Exception as exc:  # run_agent emits ``error`` then re-raises
            log.warning("demo run %s failed: %s", session, exc)
            on_event({"type": "error", "ts": time.time(), "message": f"{type(exc).__name__}"})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    yield _sse(
        "session",
        {
            "session": session,
            "mode": config.mode,
            "threshold": config.threshold,
            "backend": backend,
            "ts": time.time(),
        },
    )
    task = asyncio.create_task(drive())
    errored = False
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            kind = str(event.get("type", "message"))
            if kind == "error":
                if errored:
                    continue  # the runner's own error event already went out
                errored = True
            yield _sse(kind, event)
        yield _sse("done", {"session": session, "ts": time.time()})
    finally:
        try:
            if not task.done():
                task.cancel()
                with anyio.CancelScope(shield=True):  # we may be cancelled (disconnect)
                    await asyncio.wait([task], timeout=5)
        finally:
            shutil.rmtree(workspace.parent, ignore_errors=True)


def main(port: int = 8765) -> None:
    """Serve the demo on http://127.0.0.1:<port> (loopback only)."""
    import uvicorn

    print(f"agent-router demo: http://127.0.0.1:{port}")
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
