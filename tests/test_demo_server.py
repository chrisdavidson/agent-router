"""Demo server API tests (FastAPI TestClient, hashing embedder, no network, no SDK)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_router.core.catalog import load_catalog
from agent_router.core.hints import render_hint
from agent_router.core.types import HookPoint
from agent_router.demo import server


@pytest.fixture(autouse=True)
def _hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ROUTER_EMBEDDER", "hashing")


@pytest.fixture
def audit_dir(tmp_path: Path) -> Path:
    d = tmp_path / "audit"
    d.mkdir()
    return d


@pytest.fixture
def client(audit_dir: Path) -> TestClient:
    return TestClient(server.create_app(audit_dir=audit_dir))


# -- catalog / backends -------------------------------------------------------


def test_catalog_lists_entries_none_and_config(client: TestClient) -> None:
    body = client.get("/api/catalog").json()
    ids = [e["id"] for e in body["entries"]]
    assert ids == [e.id for e in load_catalog().entries]
    first = body["entries"][0]
    assert {"id", "name", "project", "license", "what", "kind", "points", "replaces"} <= set(first)
    assert body["none"]["id"] == "none"
    assert 0.0 <= body["threshold"] <= 1.0
    assert body["mode"] in ("advisory", "enforce")
    assert body["version"]


def test_backends_follow_registry(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        server.registry, "available_backends", lambda: {"local": True, "extra": False}
    )
    body = client.get("/api/backends").json()
    assert body["default"] == "local"
    assert body["backends"] == [
        {"name": "local", "available": True},
        {"name": "extra", "available": False},
    ]


# -- route --------------------------------------------------------------------


def _route(client: TestClient, **payload):
    payload.setdefault("backend", "local")
    return client.post("/api/route", json=payload)


def test_route_prompt_returns_full_distribution(client: TestClient) -> None:
    res = _route(client, text="What is 17% of 2,340 exactly?", point="prompt")
    assert res.status_code == 200, res.text
    body = res.json()
    assert {"decision", "result", "options", "hint", "latency_ms", "state"} <= set(body)
    probs = body["result"]["probabilities"]
    option_ids = [o["id"] for o in body["options"]]
    assert option_ids[-1] == "none"
    assert set(probs) == set(option_ids)
    assert sum(probs.values()) == pytest.approx(1.0, abs=1e-6)
    assert body["result"]["choice"] in option_ids
    assert body["decision"]["action"] in ("suggest", "native", "enforce", "skipped")
    assert "reason" in body["decision"]
    assert body["latency_ms"] >= 0
    if body["decision"]["action"] == "suggest":
        assert body["hint"].startswith("[agent-router]")


def test_route_is_stateless_between_calls(client: TestClient) -> None:
    """Same input twice gives the same action (no 'already suggested this turn')."""
    a = _route(client, text="compute 2**200 exactly", point="prompt", threshold=0.0).json()
    b = _route(client, text="compute 2**200 exactly", point="prompt", threshold=0.0).json()
    assert a["decision"]["action"] == b["decision"]["action"] == "suggest"


class _StubDecider:
    name = "stub"

    def decide(self, state, options):
        from agent_router.core.types import ChoiceResult

        rest = (1.0 - 0.6) / (len(options) - 1)
        probs = {k: (0.6 if k == "exact-calc" else rest) for k in options}
        return ChoiceResult("exact-calc", probs, 0.4, backend="stub", latency_ms=1.0)


def test_route_below_threshold_is_native_but_keeps_entry(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server.registry, "make_decider", lambda name, catalog: _StubDecider())
    body = _route(client, text="compute 2**200 exactly", point="prompt", threshold=0.7).json()
    assert body["decision"]["action"] == "native"
    assert body["decision"]["entry_id"] == "exact-calc"  # pointed, but gated
    assert body["hint"] is None
    assert body["threshold"] == 0.7
    low = _route(client, text="compute 2**200 exactly", point="prompt", threshold=0.5).json()
    assert low["decision"]["action"] == "suggest"


def test_route_tool_enforce_denies(client: TestClient) -> None:
    body = _route(
        client,
        text="compute 2**200 exactly",
        point="tool",
        tool_name="Bash",
        tool_input={"command": 'python3 -c "print(2**200)"'},
        mode="enforce",
        threshold=0.0,
    ).json()
    assert body["decision"]["action"] in ("enforce", "native")
    if body["decision"]["action"] == "enforce":
        assert body["hint"].startswith("[agent-router] Blocked Bash")
    # Bash-eligible entries only, plus none
    option_ids = {o["id"] for o in body["options"]}
    assert "commit-writer" not in option_ids
    assert "none" in option_ids


def test_route_skill_defaults_tool_name(client: TestClient) -> None:
    body = _route(
        client,
        text="write a commit message for adding retry logic",
        point="skill",
        tool_input={"skill": "release-notes"},
    ).json()
    assert body["decision"]["action"] != "skipped"
    assert [o["id"] for o in body["options"]] == ["commit-writer", "none"]


def test_route_ineligible_tool_is_skipped_without_result(client: TestClient) -> None:
    body = _route(client, text="edit file", point="tool", tool_name="Edit").json()
    assert body["decision"]["action"] == "skipped"
    assert body["result"] is None
    assert [o["id"] for o in body["options"]] == ["none"]


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "x", "point": "nowhere"},
        {"text": "x", "point": "prompt", "mode": "loud"},
        {"text": "x", "point": "prompt", "threshold": 1.5},
        {"text": "x", "point": "prompt", "backend": "no-such-backend"},
        {"text": "x", "point": "tool"},
    ],
)
def test_route_rejects_bad_input(client: TestClient, payload: dict) -> None:
    res = client.post("/api/route", json={"backend": "local", **payload})
    assert 400 <= res.status_code < 500


def test_route_unavailable_backend_is_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server.registry, "available_backends", lambda: {"local": True, "jev": False}
    )
    res = _route(client, text="x", point="prompt", backend="jev")
    assert res.status_code == 400
    assert "jev" in res.json()["detail"]


def test_decider_is_cached_per_backend(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    real = server.registry.make_decider

    def counting(name, catalog):
        calls.append(name)
        return real(name, catalog)

    monkeypatch.setattr(server.registry, "make_decider", counting)
    _route(client, text="a", point="prompt")
    _route(client, text="b", point="prompt")
    assert calls == ["local"]


# -- audit ----------------------------------------------------------------------


def _write_audit(audit_dir: Path, name: str, records: list[dict], junk: bool = False) -> Path:
    path = audit_dir / f"{name}.jsonl"
    lines = [json.dumps(r) for r in records]
    if junk:
        lines.append('{"half written')
    path.write_text("\n".join(lines) + "\n")
    return path


def _rec(**kw) -> dict:
    base = {
        "ts": "2026-09-26T10:00:00+00:00",
        "session": "sdk-1",
        "turn": 1,
        "point": "prompt",
        "tool_name": None,
        "text": "What is 17% of 2,340 exactly?",
        "options": ["exact-calc", "none"],
        "probabilities": {"exact-calc": 0.9, "none": 0.1},
        "choice": "exact-calc",
        "confidence": 0.5,
        "action": "native",
        "reason": "x",
        "entry_id": None,
        "hint": None,
        "backend": "local",
        "latency_ms": 3.0,
        "catalog_version": "v",
        "thresholds": {"threshold": 0.5, "mode": "advisory"},
    }
    return base | kw


def test_audit_sessions_and_records(client: TestClient, audit_dir: Path) -> None:
    _write_audit(audit_dir, "s1", [_rec(), _rec(turn=2)], junk=True)
    sessions = client.get("/api/audit/sessions").json()["sessions"]
    assert [s["session"] for s in sessions] == ["s1"]
    assert sessions[0]["records"] == 2
    assert sessions[0]["first_text"] == "What is 17% of 2,340 exactly?"

    records = client.get("/api/audit/s1").json()["records"]
    assert [r["turn"] for r in records] == [1, 2]


def test_audit_restores_truncated_hint(client: TestClient, audit_dir: Path) -> None:
    entry = load_catalog().get("exact-calc")
    full = render_hint(entry, HookPoint.PROMPT, 0.9)
    assert len(full) > 300
    _write_audit(
        audit_dir,
        "s2",
        [_rec(action="suggest", entry_id="exact-calc", hint=full[:300])],
    )
    rec = client.get("/api/audit/s2").json()["records"][0]
    assert rec["hint"] == full
    assert rec["hint_restored"] is True


@pytest.mark.parametrize("name", ["..%2Fsecrets", "a b", "nope"])
def test_audit_unknown_or_bad_session_404(client: TestClient, name: str) -> None:
    assert client.get(f"/api/audit/{name}").status_code in (400, 404)


# -- live run (SSE, fake runner) ------------------------------------------------


def _sse_events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        ev, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data += line[6:]
        out.append((ev, json.loads(data) if data else {}))
    return out


def test_run_streams_events_and_writes_audit(audit_dir: Path) -> None:
    seen: dict = {}

    async def fake_runner(prompt, router, workspace, on_event):
        seen["workspace"] = workspace
        seen["mode"] = router.config.mode
        on_event({"type": "prompt", "ts": 1.0, "prompt": prompt})
        on_event({"type": "tool_use", "ts": 2.0, "id": "t1", "name": "Bash", "input": {}})
        from agent_router.core.types import HookPoint, RouterEvent

        router.route(RouterEvent(HookPoint.PROMPT, "sdk", 1, prompt))
        on_event({"type": "result", "ts": 3.0, "result": "42", "is_error": False})
        return "42"

    app = server.create_app(audit_dir=audit_dir, runner=fake_runner)
    with TestClient(app) as c:
        res = c.get("/api/run", params={"prompt": "hi there", "mode": "enforce"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(res.text)
    types = [e for e, _ in events]
    assert types[0] == "session"
    assert types[-1] == "done"
    assert "tool_use" in types and "result" in types
    session = events[0][1]["session"]
    assert seen["mode"] == "enforce"
    assert not seen["workspace"].exists()  # temp workspace cleaned up
    audit_file = audit_dir / f"{session}.jsonl"
    assert audit_file.exists()
    assert len(audit_file.read_text().splitlines()) == 1


def test_run_error_still_sends_done(audit_dir: Path) -> None:
    async def failing(prompt, router, workspace, on_event):
        on_event({"type": "error", "ts": 1.0, "message": "RuntimeError: boom"})
        raise RuntimeError("boom")

    app = server.create_app(audit_dir=audit_dir, runner=failing)
    with TestClient(app) as c:
        res = c.get("/api/run", params={"prompt": "hi"})
    types = [e for e, _ in _sse_events(res.text)]
    assert "error" in types
    assert types[-1] == "done"


def test_run_rejects_bad_mode(client: TestClient) -> None:
    assert client.get("/api/run", params={"prompt": "hi", "mode": "loud"}).status_code == 400


def test_index_served(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "agent-router" in res.text


def test_run_refuses_cross_site(audit_dir: Path) -> None:
    async def never(prompt, router, workspace, on_event):  # pragma: no cover
        raise AssertionError("must not run")

    c = TestClient(server.create_app(audit_dir=audit_dir, runner=never))
    res = c.get("/api/run", params={"prompt": "hi"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert res.status_code == 403
