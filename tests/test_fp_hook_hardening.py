"""Phase 4 hook hardening: HOOK-01 (fail open), HOOK-02 (race-safe state), HOOK-03 (never block).

HOOK-01 runs the REAL ``plugin/bin/{hook,trace}`` scripts as subprocesses. HOOK-02 spawns
concurrent processes through ``claude_code.handle`` with a stub router (no model). HOOK-03 is a
static wiring test plus runtime tests through ``agent-router hook`` with a stub decider.
"""

from __future__ import annotations

import ast
import io
import json
import multiprocessing
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

from agent_router import cli
from agent_router.adapters import claude_code
from agent_router.core.catalog import Catalog, CatalogEntry
from agent_router.core.config import RouterConfig
from agent_router.core.router import Router
from agent_router.core.types import ChoiceResult, HookPoint

ROOT = Path(__file__).resolve().parents[1]
INTEG = ROOT / "integrations" / "first-principles"
PLUGIN = INTEG / "plugin"
BIN = PLUGIN / "bin"
FALLBACK = json.loads((INTEG / "manifest.fallback.json").read_text())
FP = FALLBACK["agent_type"]

PROMPT = {
    "hook_event_name": "UserPromptSubmit",
    "session_id": "sess",
    "prompt": "Analyse from first principles whether we should build or buy authentication.",
}
TRACE_PAYLOAD = {
    "hook_event_name": "SubagentStop",
    "session_id": "sess",
    "agent_type": FP,
    "agent_id": "a1",
    "last_assistant_message": "done",
}

_STRIP = (
    "AGENT_ROUTER_BIN",
    "AGENT_ROUTER_PYTHON",
    "AGENT_ROUTER_CATALOG",
    "AGENT_ROUTER_CALIBRATION",
    "AGENT_ROUTER_MODE",
    "AGENT_ROUTER_AUDIT",
    "AGENT_ROUTER_DISABLED",
    "AGENT_ROUTER_BACKEND",
    "AGENT_ROUTER_HOOK_TIMEOUT",
    "AGENT_ROUTER_NEVER_BLOCK_AGENTS",
    "AGENT_ROUTER_INTEGRATION",
    "FP_AGENT_TYPE",
)


def _env(state: Path, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _STRIP}
    env["AGENT_ROUTER_STATE_DIR"] = str(state)
    env["AGENT_ROUTER_EMBEDDER"] = "hashing"  # offline: no model download
    env.update(extra)
    return env


def _run(script: Path, stdin: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(script)], input=stdin, capture_output=True, text=True, env=env, timeout=60
    )


def _stub(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _assert_open(proc: subprocess.CompletedProcess) -> None:
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "{}\n", proc.stdout


# --- HOOK-01: the fail-open matrix through the real bin/ scripts ------------------------------

_GOOD = json.dumps(PROMPT)


def _unwritable_state(tmp: Path) -> Path:
    state = tmp / "ro"
    state.mkdir()
    state.chmod(0o500)
    return state


needs_perms = pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")


def _case_state_is_a_file(tmp):
    f = tmp / "state-file"
    f.write_text("x")
    return _GOOD, _env(f)


def _case_readonly_state(tmp):
    return _GOOD, _env(_unwritable_state(tmp))


def _case_unreadable_catalog(tmp):
    return _GOOD, _env(tmp / "s", AGENT_ROUTER_CATALOG=str(tmp / "missing.yaml"))


def _case_broken_catalog(tmp):
    bad = tmp / "bad.yaml"
    bad.write_text("entries: [unclosed")
    return _GOOD, _env(tmp / "s", AGENT_ROUTER_CATALOG=str(bad))


def _case_unreadable_calibration(tmp):
    cal = tmp / "cal.json"
    cal.write_text("{}")
    cal.chmod(0)
    return _GOOD, _env(tmp / "s", AGENT_ROUTER_CALIBRATION=str(cal))


def _case_garbage_calibration(tmp):
    cal = tmp / "cal.json"
    cal.write_text("not json")
    return _GOOD, _env(tmp / "s", AGENT_ROUTER_CALIBRATION=str(cal))


def _case_decider_exception(tmp):
    return _GOOD, _env(tmp / "s", AGENT_ROUTER_BACKEND="no-such-backend")


def _copied_integration(tmp: Path) -> Path:
    dest = tmp / "repo" / "integrations" / "first-principles"
    shutil.copytree(
        INTEG, dest, ignore=shutil.ignore_patterns("runs", "handoff", "__pycache__", "*.md")
    )
    return dest


def _case_broken_descriptor(tmp):
    dest = _copied_integration(tmp)
    (dest / "descriptor.json").write_text("{not json")
    return _GOOD, _env(tmp / "s", AGENT_ROUTER_BIN=str(ROOT / ".venv/bin/agent-router"))


def _case_broken_manifest(tmp):
    dest = _copied_integration(tmp)
    (dest / "manifest.fallback.json").write_text('{"manifest_version": 99}')
    return _GOOD, _env(tmp / "s", AGENT_ROUTER_BIN=str(ROOT / ".venv/bin/agent-router"))


def _stub_case(body: str, **extra: str):
    def case(tmp):
        stub = _stub(tmp / "stub", body)
        return _GOOD, _env(tmp / "s", AGENT_ROUTER_BIN=str(stub), **extra)

    return case


HOOK_CASES = {
    "malformed-stdin": lambda tmp: ("not json {", _env(tmp / "s")),
    "empty-stdin": lambda tmp: ("", _env(tmp / "s")),
    "json-array": lambda tmp: ("[1, 2, 3]", _env(tmp / "s")),
    "json-scalar": lambda tmp: ("42", _env(tmp / "s")),
    "state-dir-is-a-file": _case_state_is_a_file,
    "state-dir-readonly": pytest.param(_case_readonly_state, marks=needs_perms),
    "catalog-missing": _case_unreadable_catalog,
    "catalog-broken": _case_broken_catalog,
    "calibration-unreadable": pytest.param(_case_unreadable_calibration, marks=needs_perms),
    "calibration-garbage": _case_garbage_calibration,
    "decider-exception": _case_decider_exception,
    "descriptor-broken": _case_broken_descriptor,
    "manifest-broken": _case_broken_manifest,
    "binary-missing": lambda tmp: (_GOOD, _env(tmp / "s", AGENT_ROUTER_BIN=str(tmp / "nope"))),
    "binary-exit1-garbage": _stub_case("echo 'Traceback: boom'; exit 1"),
    "binary-exit1-valid-json": _stub_case("echo '{\"hookSpecificOutput\": {}}'; exit 1"),
    "binary-import-error": _stub_case("echo 'ImportError: no module' >&2; exit 1"),
    "binary-prints-nothing": _stub_case("exit 0"),
    "binary-prints-garbage": _stub_case("echo 'garbage'"),
    "binary-prints-brace-garbage": _stub_case("echo '{not json}'"),
    "binary-prints-array": _stub_case("echo '[1]'"),
    "binary-prints-string": _stub_case("echo '\"x\"'"),
    "binary-prints-two-objects": _stub_case("echo '{}'; echo '{\"a\": 1}'"),
    "binary-prints-truncated": _stub_case("printf '{\"a\": '"),
    "binary-killed": _stub_case("kill -9 $$"),
    "binary-hangs": _stub_case("sleep 30", AGENT_ROUTER_HOOK_TIMEOUT="1"),
    "binary-hangs-as-grandchild": _stub_case("sleep 30 & wait", AGENT_ROUTER_HOOK_TIMEOUT="1"),
}


@pytest.mark.parametrize("name", HOOK_CASES)
def test_hook_fails_open_through_the_real_script(name, tmp_path):
    case = HOOK_CASES[name]
    case = case.values[0] if hasattr(case, "values") else case  # pytest.param(...) wrapper
    stdin, env = case(tmp_path)
    t0 = time.monotonic()
    proc = _run(BIN / "hook", stdin, env)
    _assert_open(proc)
    assert time.monotonic() - t0 < 20


def test_hook_hang_is_cut_off_by_the_guard_not_the_host(tmp_path):
    stub = _stub(tmp_path / "stub", "sleep 30")
    env = _env(tmp_path / "s", AGENT_ROUTER_BIN=str(stub), AGENT_ROUTER_HOOK_TIMEOUT="1")
    t0 = time.monotonic()
    _assert_open(_run(BIN / "hook", _GOOD, env))
    assert time.monotonic() - t0 < 6  # 1 s guard + 1 s kill grace, far below hooks.json's 15 s


def test_hook_timeout_setting_that_is_not_a_number_falls_back_to_the_default(tmp_path):
    stub = _stub(tmp_path / "stub", "echo '{\"ok\": 1}'")
    env = _env(tmp_path / "s", AGENT_ROUTER_BIN=str(stub), AGENT_ROUTER_HOOK_TIMEOUT="soon")
    proc = _run(BIN / "hook", _GOOD, env)
    assert proc.returncode == 0 and json.loads(proc.stdout) == {"ok": 1}


def test_hook_passes_a_valid_object_and_stderr_through(tmp_path):
    """Positive control: the boundary is a filter, not a blanket {}."""
    hint = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "x"}}
    stub = _stub(tmp_path / "stub", f"echo 'diagnostic' >&2; echo '{json.dumps(hint)}'")
    proc = _run(BIN / "hook", _GOOD, _env(tmp_path / "s", AGENT_ROUTER_BIN=str(stub)))
    assert proc.returncode == 0 and json.loads(proc.stdout) == hint
    assert "diagnostic" in proc.stderr


def test_hook_stub_receives_the_payload_on_stdin(tmp_path):
    seen = tmp_path / "seen"
    stub = _stub(tmp_path / "stub", f"cat > {seen}; echo '{{}}'")
    _assert_open(_run(BIN / "hook", _GOOD, _env(tmp_path / "s", AGENT_ROUTER_BIN=str(stub))))
    assert json.loads(seen.read_text()) == PROMPT


def _trace_stub_case(body: str, **extra: str):
    def case(tmp):
        stub = _stub(tmp / "stubpy", body)
        return json.dumps(TRACE_PAYLOAD), _env(tmp / "s", AGENT_ROUTER_PYTHON=str(stub), **extra)

    return case


def _trace_state_is_a_file(tmp):
    f = tmp / "state-file"
    f.write_text("x")
    return json.dumps(TRACE_PAYLOAD), _env(f)


TRACE_CASES = {
    "malformed-stdin": lambda tmp: (
        '{"agent_type": "first-principles:first-principles", not json',
        _env(tmp / "s"),
    ),
    "empty-stdin": lambda tmp: ("", _env(tmp / "s")),
    "json-array": lambda tmp: ("[1, 2]", _env(tmp / "s")),
    "state-dir-is-a-file": _trace_state_is_a_file,
    "interpreter-missing": lambda tmp: (
        json.dumps(TRACE_PAYLOAD),
        _env(tmp / "s", AGENT_ROUTER_PYTHON=str(tmp / "nope")),
    ),
    "interpreter-exit1-garbage": _trace_stub_case("echo 'Traceback'; exit 1"),
    "interpreter-prints-nothing": _trace_stub_case("exit 0"),
    "interpreter-prints-garbage": _trace_stub_case("echo 'oops'"),
    "interpreter-prints-array": _trace_stub_case("echo '[]'"),
    "interpreter-prints-a-non-empty-object": _trace_stub_case("echo '{\"a\": 1}'"),
    "interpreter-hangs": _trace_stub_case("sleep 30", AGENT_ROUTER_HOOK_TIMEOUT="1"),
    "interpreter-hangs-as-grandchild": _trace_stub_case(
        "sleep 30 & wait", AGENT_ROUTER_HOOK_TIMEOUT="1"
    ),
}


@pytest.mark.parametrize("name", TRACE_CASES)
def test_trace_fails_open_through_the_real_script(name, tmp_path):
    stdin, env = TRACE_CASES[name](tmp_path)
    _assert_open(_run(BIN / "trace", stdin, env))


def test_trace_parse_exception_in_the_real_trace_module(tmp_path):
    """A payload that makes trace.py raise (not just malformed JSON) still answers {}."""
    payload = {**TRACE_PAYLOAD, "tool_input": "x" * 10, "tool_response": 5, "agent_id": [1]}
    proc = _run(BIN / "trace", json.dumps(payload), _env(tmp_path / "s"))
    _assert_open(proc)


def test_trace_passes_stderr_through(tmp_path):
    stub = _stub(tmp_path / "stubpy", "echo 'diag' >&2; echo '{}'")
    proc = _run(BIN / "trace", json.dumps(TRACE_PAYLOAD), _env(tmp_path, AGENT_ROUTER_PYTHON=stub))
    assert proc.stdout == "{}\n" and "diag" in proc.stderr


def test_failopen_library_missing_still_answers_empty(tmp_path):
    """If _failopen.sh cannot be sourced the scripts print {} rather than die."""
    for script in ("hook", "trace"):
        bindir = tmp_path / script / "plugin" / "bin"
        bindir.mkdir(parents=True)
        shutil.copy(BIN / script, bindir / script)
        (tmp_path / script / "catalog.yaml").write_text("")
        env = _env(tmp_path / "s", AGENT_ROUTER_BIN="/bin/true", AGENT_ROUTER_PYTHON="/bin/true")
        _assert_open(_run(bindir / script, json.dumps(TRACE_PAYLOAD), env))


# --- HOOK-02: race-safe session state ---------------------------------------------------------

N = 8


def _entry(i: int) -> CatalogEntry:
    return CatalogEntry(
        id=f"e{i}",
        kind="agent",
        name=f"Entry {i}",
        project="p",
        license="MIT",
        url="https://example.invalid",
        what="w",
        target=f"target-{i}",
        points=(HookPoint.PROMPT,),
        replaces=("Agent",),
        agents=("main",),
    )


class _Pick:
    """Decider that takes ~100 ms (a routing call) and picks one fixed entry."""

    name = "slow-pick"

    def __init__(self, entry_id: str, delay: float = 0.1):
        self.entry_id, self.delay = entry_id, delay

    def decide(self, state, options):
        time.sleep(self.delay)
        probs = {k: (0.9 if k == self.entry_id else 0.1 / (len(options) - 1)) for k in options}
        return ChoiceResult(choice=self.entry_id, probabilities=probs, confidence=0.8)


def _worker(args):
    root, index, entry_index, barrier, queue = args
    catalog = Catalog(version="t", entries=tuple(_entry(i) for i in range(N)))

    def make(audit, seed):
        return Router(
            catalog,
            _Pick(f"e{entry_index}"),
            RouterConfig(audit_path=audit),
            suggested=seed,
        )

    payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "race",
        "prompt_id": "same-turn",
        "prompt": f"prompt number {index}",
    }
    barrier.wait(timeout=30)  # all processes snapshot the same (empty) state
    queue.put((index, claude_code.handle(payload, make, Path(root))))


def _race(root: Path, entry_of) -> list[dict]:
    ctx = multiprocessing.get_context("fork")
    barrier, queue = ctx.Barrier(N), ctx.Queue()
    procs = [
        ctx.Process(target=_worker, args=((str(root), i, entry_of(i), barrier, queue),))
        for i in range(N)
    ]
    for p in procs:
        p.start()
    outputs = [queue.get(timeout=60) for _ in procs]
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0
    return [out for _, out in sorted(outputs)]


def _state(root: Path) -> dict:
    return json.loads((root / "sessions" / "race.json").read_text())


def test_concurrent_distinct_suggestions_all_survive(tmp_path):
    """Every process's once-per-turn key and prompt is merged; none is lost to a last-writer."""
    outputs = _race(tmp_path, lambda i: i)
    assert all("additionalContext" in o["hookSpecificOutput"] for o in outputs)  # all distinct
    state = _state(tmp_path)
    assert {e for _, e in state["suggested"]} == {f"e{i}" for i in range(N)}
    assert len({t for t, _ in state["suggested"]}) == 1
    # prompts are capped at MAX_KEPT_PROMPTS; a lost update would leave exactly one
    assert len(state["prompts"]) == claude_code.MAX_KEPT_PROMPTS
    assert set(state["prompts"]) <= {f"prompt number {i}" for i in range(N)}
    assert state.get("duplicate_suggestions", 0) == 0
    assert not list((tmp_path / "sessions").glob("*.tmp"))


def test_concurrent_same_suggestion_is_emitted_at_most_once(tmp_path):
    """Invariant (lock held): per (turn, entry) exactly one process emits the hint and every
    other contender is suppressed and counted, so emitted + duplicate_suggestions == N."""
    outputs = _race(tmp_path, lambda i: 0)
    emitted = [o for o in outputs if o]
    assert len(emitted) == 1
    state = _state(tmp_path)
    assert state["duplicate_suggestions"] == N - 1
    assert len(emitted) + state["duplicate_suggestions"] == N
    assert [e for _, e in state["suggested"]] == ["e0"]


def test_without_the_lock_updates_are_lost(tmp_path, monkeypatch):
    """Must-fail control: disabling the lock reproduces the lost update the lock prevents."""
    from contextlib import contextmanager

    @contextmanager
    def no_lock(path, wait=None):
        yield True  # claims the lock without taking it

    monkeypatch.setattr(claude_code, "state_lock", no_lock)
    _race(tmp_path, lambda i: i)
    state = _state(tmp_path)
    assert {e for _, e in state["suggested"]} != {f"e{i}" for i in range(N)} or len(
        state["prompts"]
    ) < claude_code.MAX_KEPT_PROMPTS


def test_lock_timeout_skips_the_write_and_keeps_the_output(tmp_path, monkeypatch):
    import fcntl

    monkeypatch.setattr(claude_code, "LOCK_WAIT_S", 0.2)
    path = tmp_path / "sessions" / "race.json"
    path.parent.mkdir(parents=True)
    holder = (path.parent / "race.json.lock").open("a+")
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        catalog = Catalog(version="t", entries=(_entry(0),))
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "race",
            "prompt_id": "t",
            "prompt": "hello",
        }
        t0 = time.monotonic()
        out = claude_code.handle(
            payload,
            lambda audit, seed: Router(
                catalog, _Pick("e0", 0), RouterConfig(audit_path=audit), suggested=seed
            ),
            tmp_path,
        )
        assert time.monotonic() - t0 < 5
    finally:
        holder.close()
    assert "additionalContext" in out["hookSpecificOutput"]  # fail open: output as routed
    assert not path.exists()  # ...and the write was skipped


def test_no_fcntl_skips_the_write(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_code, "fcntl", None)
    with claude_code.state_lock(tmp_path / "s.json") as locked:
        assert locked is False


def test_state_keys_written_by_others_are_preserved(tmp_path):
    """Unknown keys on disk (and the first writer's integration record) survive a merge."""
    path = tmp_path / "sessions" / "race.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"integration": {"source": "first"}, "extra": 7}))
    catalog = Catalog(version="t", entries=(_entry(0),))
    claude_code.handle(
        {"hook_event_name": "UserPromptSubmit", "session_id": "race", "prompt": "p"},
        lambda a, s: Router(catalog, _Pick("e0", 0), RouterConfig(audit_path=a), suggested=s),
        tmp_path,
        integration={"source": "second"},
    )
    state = json.loads(path.read_text())
    assert state["integration"] == {"source": "first"} and state["extra"] == 7


# --- HOOK-03: never block (D-02) --------------------------------------------------------------


def _wiring_violations(hooks_json: dict) -> list[str]:
    """Commands wired where they could block the first-principles agent, other than the router
    hook at UserPromptSubmit/PreToolUse and the record-only trace."""
    bad = []
    for event, groups in hooks_json["hooks"].items():
        for group in groups:
            for h in group["hooks"]:
                cmd = Path(h.get("command", "")).name
                if h.get("type") != "command" or cmd not in ("hook", "trace"):
                    bad.append(f"{event}: unexpected hook {h}")
                elif cmd == "hook" and event not in ("UserPromptSubmit", "PreToolUse"):
                    bad.append(f"{event}: router hook wired to a blocking-capable event")
    return bad


def _emission_paths(source: str) -> list[str]:
    """String constants / dict keys through which a hook could emit a deny or a block."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in ("permissionDecision", "permissionDecisionReason", "deny")
        ):
            found.append(f"{node.value!r} at line {node.lineno}")
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            for k, v in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(k, ast.Constant)
                    and k.value == "decision"
                    and isinstance(v, ast.Constant)
                    and v.value == "block"
                ) or (
                    isinstance(k, ast.Constant) and k.value == "continue" and "stopReason" in keys
                ):
                    found.append(f"block output at line {node.lineno}")
    return found


def test_only_the_router_hook_and_the_record_only_trace_are_wired():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
    assert _wiring_violations(hooks) == []
    # the must-fail control: the same check reddens when the router hook is wired to SubagentStop
    bad = json.loads(json.dumps(hooks))
    bad["hooks"]["SubagentStop"][0]["hooks"].append(
        {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/bin/hook"}
    )
    assert _wiring_violations(bad)
    bad = json.loads(json.dumps(hooks))
    bad["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": "/x/other"}]}]
    assert _wiring_violations(bad)


def test_trace_and_contracts_have_no_deny_or_block_emission_path():
    sources = [INTEG / "trace.py", *sorted((ROOT / "src/agent_router/contracts").glob("*.py"))]
    assert len(sources) >= 4
    for src in sources:
        assert _emission_paths(src.read_text()) == [], src
    # the scanner can fail: it flags each way of emitting a deny or a block
    assert _emission_paths('out = {"decision": "block", "reason": "x"}')
    assert _emission_paths('out = {"hookSpecificOutput": {"permissionDecision": "deny"}}')
    assert _emission_paths('out = {"continue": False, "stopReason": "x"}')


@pytest.mark.parametrize(
    "event", ["SubagentStop", "SubagentStart", "PostToolUse", "PostToolUseFailure"]
)
def test_trace_answers_empty_for_every_record_only_event(event, tmp_path):
    payload = {
        "hook_event_name": event,
        "session_id": "s",
        "agent_type": FP,
        "agent_id": "a",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "tool_response": {"stdout": "x"},
        "last_assistant_message": "done",
        "stop_hook_active": True,
    }
    _assert_open(_run(BIN / "trace", json.dumps(payload), _env(tmp_path)))
    # a handoff (main session starts the agent) is traced too, and is also record-only
    handoff = {
        "hook_event_name": "PreToolUse",
        "session_id": "s",
        "tool_name": "Agent",
        "tool_input": {"subagent_type": FP, "prompt": "q"},
    }
    _assert_open(_run(BIN / "trace", json.dumps(handoff), _env(tmp_path)))


# runtime: `agent-router hook` called directly (bypassing bin/hook's forced advisory mode)

CALC = {"command": 'python3 -c "print(17*23)"'}
OTHER = "someplugin:other-agent"


class _Always:
    """A decider that always picks the first real option with high confidence."""

    name = "always"

    def decide(self, state, options):
        choice = next(k for k in options if k != "none")
        probs = {k: (0.99 if k == choice else 0.01 / (len(options) - 1)) for k in options}
        return ChoiceResult(choice=choice, probabilities=probs, confidence=0.99)


@pytest.fixture
def enforce_env(monkeypatch, tmp_path):
    from agent_router import evaluate

    real = evaluate.make_router
    monkeypatch.setattr(
        evaluate, "make_router", lambda backend, catalog, **kw: real(_Always(), catalog, **kw)
    )
    for var in _STRIP:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AGENT_ROUTER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AGENT_ROUTER_MODE", "enforce")
    monkeypatch.setenv("AGENT_ROUTER_BACKEND", "local")
    monkeypatch.setenv("AGENT_ROUTER_SKIP_INPUT", "x^")  # never matches
    return tmp_path


def _direct(monkeypatch, capsys, payload: dict, *argv: str) -> dict:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert cli.main(["hook", *argv]) == 0
    return json.loads(capsys.readouterr().out)


def _pre_tool(agent_type: str, n: int = 1) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": f"s{n}",
        "prompt_id": "p",
        "agent_type": agent_type,
        "tool_name": "Bash",
        "tool_input": CALC,
    }


def _decision(out: dict) -> str | None:
    return out.get("hookSpecificOutput", {}).get("permissionDecision")


def _plain_catalog(tmp: Path, agents: list[str]) -> str:
    path = tmp / "catalog.yaml"
    path.write_text(
        "version: t\nentries:\n"
        "  - id: exact-calc\n    kind: tool\n    name: Exact calculator\n"
        "    project: p\n    license: MIT\n    url: https://example.invalid\n"
        "    target: mcp__x__calc\n    points: [tool]\n    replaces: [Bash]\n"
        f"    agents: {json.dumps(agents)}\n    fits: calc_expression\n"
        "    what: Exact arithmetic.\n"
    )
    return str(path)


def test_enforce_never_denies_the_integrated_agent(enforce_env, monkeypatch, capsys):
    """(a) enforce mode, real integration catalog and manifest, FP agent: advisory at most."""
    monkeypatch.setenv("AGENT_ROUTER_INTEGRATION", str(INTEG))
    monkeypatch.setenv("AGENT_ROUTER_CATALOG", str(INTEG / "catalog.yaml"))
    out = _direct(monkeypatch, capsys, _pre_tool(FP))
    assert _decision(out) is None
    assert "Exact calculator" in out["hookSpecificOutput"]["additionalContext"]
    audit = [
        json.loads(line)
        for line in (enforce_env / "state" / "audit" / "s1.jsonl").read_text().splitlines()
    ]
    assert audit[-1]["action"] == "suggest" and audit[-1]["downgraded"] is True
    assert audit[-1]["thresholds"]["mode"] == "enforce"


def test_never_block_is_scoped_not_a_global_off_switch(enforce_env, monkeypatch, capsys):
    """(b) the same enforce run denies an agent that is not protected."""
    catalog = _plain_catalog(enforce_env, [OTHER])
    out = _direct(monkeypatch, capsys, _pre_tool(OTHER), "--catalog", catalog)
    assert _decision(out) == "deny"
    # protecting a different agent does not protect this one
    monkeypatch.setenv("AGENT_ROUTER_NEVER_BLOCK_AGENTS", f"{FP}, nobody:else")
    out = _direct(monkeypatch, capsys, _pre_tool(OTHER, 2), "--catalog", catalog)
    assert _decision(out) == "deny"


def test_env_list_protects_an_agent(enforce_env, monkeypatch, capsys):
    catalog = _plain_catalog(enforce_env, [OTHER])
    monkeypatch.setenv("AGENT_ROUTER_NEVER_BLOCK_AGENTS", f"nobody:else, {OTHER}")
    out = _direct(monkeypatch, capsys, _pre_tool(OTHER), "--catalog", catalog)
    assert _decision(out) is None and "additionalContext" in out["hookSpecificOutput"]


def test_downgrade_is_the_only_thing_standing_between_fp_and_a_deny(
    enforce_env, monkeypatch, capsys
):
    """Must-fail control: with the downgrade disabled the same payload as (a) is denied."""
    monkeypatch.setenv("AGENT_ROUTER_INTEGRATION", str(INTEG))
    monkeypatch.setenv("AGENT_ROUTER_CATALOG", str(INTEG / "catalog.yaml"))
    monkeypatch.setattr(cli, "_never_block", lambda args: frozenset())
    out = _direct(monkeypatch, capsys, _pre_tool(FP))
    assert _decision(out) == "deny"


def test_to_output_guard_alone_never_denies_a_protected_agent():
    """Defence in depth: a router that did not downgrade still cannot make the adapter deny."""
    from agent_router.core.types import Action, Decision

    enforce = Decision(Action.ENFORCE, "r", entry_id="e", hint="use the calculator")
    assert (
        claude_code.to_output(enforce, "PreToolUse")["hookSpecificOutput"]["permissionDecision"]
        == "deny"
    )
    safe = claude_code.to_output(enforce, "PreToolUse", never_block=True)
    assert "permissionDecision" not in safe["hookSpecificOutput"]
    assert safe["hookSpecificOutput"]["additionalContext"] == "use the calculator"


def test_handle_downgrades_a_router_that_enforces(tmp_path):
    """handle() applies the guard even when a custom router factory ENFORCEs."""
    entry = CatalogEntry(
        id="c",
        kind="tool",
        name="Calc",
        project="p",
        license="MIT",
        url="https://example.invalid",
        what="w",
        target="t",
        points=(HookPoint.TOOL,),
        replaces=("Bash",),
        agents=(OTHER,),
    )
    catalog = Catalog(version="t", entries=(entry,))

    def make(audit, seed):  # no never_block_agents in this config: only the adapter guards
        return Router(catalog, _Always(), RouterConfig(mode="enforce", audit_path=audit))

    payload = _pre_tool(OTHER)
    denied = claude_code.handle(payload, make, tmp_path / "a")
    assert _decision(denied) == "deny"
    held = claude_code.handle(payload, make, tmp_path / "b", never_block=[OTHER])
    assert _decision(held) is None and "additionalContext" in held["hookSpecificOutput"]
