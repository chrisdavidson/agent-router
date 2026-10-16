"""Phase 5 (INSTALL-01..03): the router is found outside a checkout, and `doctor` explains itself.

INSTALL-01 drives the real ``plugin/bin/{hook,trace,mcp,_resolve.sh}`` with stub binaries in tmp
dirs and a controlled PATH. INSTALL-02 runs ``agent-router doctor`` over a healthy copy of the
integration, then breaks one item per check.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from agent_router import cli, doctor

ROOT = Path(__file__).resolve().parents[1]
INTEG = ROOT / "integrations" / "first-principles"
BIN = INTEG / "plugin" / "bin"
FALLBACK = json.loads((INTEG / "manifest.fallback.json").read_text())
NAME, AGENT = FALLBACK["plugin_name"], FALLBACK["agent_type"]
REAL_BIN = Path(sys.executable).parent / "agent-router"
BASH = shutil.which("bash") or "/bin/bash"

# --- INSTALL-01: resolution order, through the real scripts -------------------------------------


def _exe(path: Path, body: str, shebang: str = f"#!{BASH}") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{shebang}\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class Layout:
    """A tmp checkout holding the real plugin scripts, plus a PATH built from stub dirs."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.repo = tmp / "repo"
        self.bin = self.repo / "integrations" / "first-principles" / "plugin" / "bin"
        shutil.copytree(BIN, self.bin)
        self.integ = self.bin.parent.parent
        self.tools = tmp / "tools"  # the only system programs a sealed PATH offers
        self.tools.mkdir()
        for tool in ("dirname", "cat", "timeout"):
            (self.tools / tool).symlink_to(shutil.which(tool))
        self.pathdir = tmp / "pathdir"
        self.pathdir.mkdir()

    def venv_bin(self, body: str = "echo venv-bin") -> Path:
        return _exe(self.repo / ".venv" / "bin" / "agent-router", body)

    def venv_python(self) -> Path:
        return _exe(self.repo / ".venv" / "bin" / "python", "echo '{}'")

    def path_tool(self, body: str = "echo path-bin", shebang: str = f"#!{BASH}") -> Path:
        return _exe(self.pathdir / "agent-router", body, shebang)

    def env(self, *, system_python: bool = False, **extra: str) -> dict[str, str]:
        parts = [str(self.pathdir), str(self.tools)]
        if system_python:
            sysdir = self.tmp / "sys"
            sysdir.mkdir(exist_ok=True)
            if not (sysdir / "python3").exists():
                (sysdir / "python3").symlink_to(sys.executable)
            parts.append(str(sysdir))
        return {"PATH": os.pathsep.join(parts), "HOME": str(self.tmp), **extra}

    def resolve(self, env: dict[str, str]) -> tuple[str, str, str, str]:
        out = subprocess.run(
            [BASH, str(self.bin / "_resolve.sh")], capture_output=True, text=True, env=env
        ).stdout.splitlines()
        b, p = out[0].split(" ", 2), out[1].split(" ", 2) + [""]
        return b[1], b[2] if len(b) > 2 else "", p[1], p[2]


@pytest.fixture
def lay(tmp_path) -> Layout:
    return Layout(tmp_path)


def test_bin_env_beats_checkout_and_path(lay):
    env_bin = _exe(lay.tmp / "mine", "echo mine")
    lay.venv_bin()
    lay.path_tool()
    branch, path, _, _ = lay.resolve(lay.env(AGENT_ROUTER_BIN=str(env_bin)))
    assert (branch, path) == ("env", str(env_bin))


def test_an_unusable_env_override_is_final(lay):
    lay.venv_bin()
    lay.path_tool()
    branch, why, _, _ = lay.resolve(lay.env(AGENT_ROUTER_BIN=str(lay.tmp / "nope")))
    assert branch == "none" and "AGENT_ROUTER_BIN" in why


def test_bin_checkout_beats_a_stale_path_install(lay):
    venv = lay.venv_bin()
    lay.path_tool()
    branch, path, _, _ = lay.resolve(lay.env())
    assert (branch, path) == ("checkout", str(venv))


def test_bin_falls_back_to_path_without_a_checkout_venv(lay):
    tool = lay.path_tool()
    branch, path, _, _ = lay.resolve(lay.env())
    assert (branch, path) == ("path", str(tool))


def test_a_non_executable_venv_entry_is_skipped(lay):
    lay.venv_bin().chmod(0o644)
    tool = lay.path_tool()
    assert lay.resolve(lay.env())[:2] == ("path", str(tool))


def test_bin_unresolvable(lay):
    branch, why, _, _ = lay.resolve(lay.env())
    assert branch == "none" and "agent-router not found" in why


def test_python_env_then_checkout_then_path_shebang_then_python3(lay):
    py = _exe(lay.tmp / "python-a", "echo")
    lay.path_tool(shebang=f"#!{py}")
    env = lay.env(system_python=True)
    assert lay.resolve(env)[2:] == ("path", str(py))  # the PATH install's own interpreter
    venv_py = lay.venv_python()
    assert lay.resolve(env)[2:] == ("checkout", str(venv_py))
    other = _exe(lay.tmp / "other", "echo")
    assert lay.resolve({**env, "AGENT_ROUTER_PYTHON": str(other)})[2:] == ("env", str(other))
    assert lay.resolve({**env, "AGENT_ROUTER_PYTHON": str(lay.tmp / "gone")})[2] == "none"


def _uv_exec_tool(lay: Layout, interpreter: Path) -> None:
    """The two-line form uv writes when the interpreter path is too long for a shebang."""
    q = "'" * 3
    body = f"""{q}exec' '{interpreter}' "$0" "$@"\n' {q}"""
    lay.path_tool(body, shebang="#!/bin/sh")


def test_python_behind_uvs_long_path_exec_form(lay):
    py = _exe(lay.tmp / "python-uv", "echo")
    _uv_exec_tool(lay, py)
    assert lay.resolve(lay.env(system_python=True))[2:] == ("path", str(py))
    assert doctor.shebang_python(str(lay.pathdir / "agent-router")) == str(py)
    _uv_exec_tool(lay, lay.tmp / "missing" / "python")  # a dead interpreter: python3 instead
    assert lay.resolve(lay.env(system_python=True))[2] == "system"
    assert doctor.shebang_python(str(lay.pathdir / "agent-router")) is None


@pytest.mark.parametrize(
    "shebang",
    [
        "#!{tmp}/missing/python",  # points at an interpreter that is not there
        "#!/usr/bin/env python3",  # not an absolute interpreter path
        "#!{tmp}/notpython",  # absolute and executable, but not a python
        "no shebang at all",
    ],
)
def test_python_bad_shebang_falls_back_to_python3(lay, shebang):
    _exe(lay.tmp / "notpython", "echo")
    lay.path_tool(shebang=shebang.format(tmp=lay.tmp))
    sysdir = lay.tmp / "sys"
    branch, path = lay.resolve(lay.env(system_python=True))[2:]
    assert (branch, path) == ("system", str(sysdir / "python3"))


def test_python_unresolvable_without_python3(lay):
    lay.path_tool(shebang=f"#!{lay.tmp}/missing/python")
    assert lay.resolve(lay.env())[2] == "none"


# the same scenarios through doctor's Python replica of the order

SCENARIOS = {
    "nothing": lambda lay: lay.env(),
    "path-only": lambda lay: (lay.path_tool(), lay.env())[1],
    "checkout-and-path": lambda lay: (
        lay.venv_bin(),
        lay.venv_python(),
        lay.path_tool(),
        lay.env(),
    )[3],
    "env-bin": lambda lay: (lay.path_tool(), lay.env(AGENT_ROUTER_BIN=str(lay.path_tool())))[1],
    "env-bin-bad": lambda lay: (lay.venv_bin(), lay.env(AGENT_ROUTER_BIN="/nonexistent/x"))[1],
    "env-python-bad": lambda lay: (lay.venv_python(), lay.env(AGENT_ROUTER_PYTHON="/nope"))[1],
    "shebang-ok": lambda lay: (
        lay.path_tool(shebang="#!" + str(_exe(lay.tmp / "python-x", "echo"))),
        lay.env(system_python=True),
    )[1],
    "shebang-missing": lambda lay: (
        lay.path_tool(shebang=f"#!{lay.tmp}/missing/python"),
        lay.env(system_python=True),
    )[1],
}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_doctor_replicates_the_shell_resolution_order(lay, scenario):
    env = SCENARIOS[scenario](lay)
    shell_bin = lay.resolve(env)[:2]
    shell_py = lay.resolve(env)[2:]
    rb = doctor.resolve_bin(lay.repo, env)
    rp = doctor.resolve_python(lay.repo, env)
    assert shell_bin[0] == rb.branch and (shell_bin[1] == rb.path or rb.path is None)
    assert shell_py[0] == rp.branch and (shell_py[1] == rp.path or rp.path is None)


HOOK_PAYLOAD = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "s", "prompt": "x"})
TRACE_PAYLOAD = json.dumps(
    {"hook_event_name": "SubagentStop", "session_id": "s", "agent_type": AGENT, "agent_id": "a"}
)


def _run(script: Path, stdin: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BASH, str(script)], input=stdin, capture_output=True, text=True, env=env, timeout=30
    )


def test_hook_runs_the_binary_it_resolves(lay):
    lay.path_tool('echo \'{"from": "path"}\'')
    proc = _run(lay.bin / "hook", HOOK_PAYLOAD, lay.env(system_python=True))
    assert (proc.returncode, json.loads(proc.stdout)) == (0, {"from": "path"})
    lay.venv_bin('echo \'{"from": "checkout"}\'')
    proc = _run(lay.bin / "hook", HOOK_PAYLOAD, lay.env(system_python=True))
    assert json.loads(proc.stdout) == {"from": "checkout"}
    mine = _exe(lay.tmp / "mine", 'echo \'{"from": "env"}\'')
    proc = _run(
        lay.bin / "hook", HOOK_PAYLOAD, lay.env(system_python=True, AGENT_ROUTER_BIN=str(mine))
    )
    assert json.loads(proc.stdout) == {"from": "env"}


def test_hook_fails_open_when_nothing_resolves(lay):
    proc = _run(lay.bin / "hook", HOOK_PAYLOAD, lay.env())
    assert (proc.returncode, proc.stdout) == (0, "{}\n")


def test_mcp_execs_the_resolved_binary_with_its_arguments(lay):
    lay.path_tool('echo "ran $*"')
    proc = _run(lay.bin / "mcp", "", lay.env())
    assert (proc.returncode, proc.stdout.strip()) == (
        0,
        "ran mcp --tools calc,calc_script,route,verify_summary,doctor",
    )


def test_mcp_exits_non_zero_with_a_message_when_nothing_resolves(lay):
    proc = _run(lay.bin / "mcp", "", lay.env())
    assert proc.returncode != 0 and "agent-router not found" in proc.stderr
    proc = _run(lay.bin / "mcp", "", lay.env(AGENT_ROUTER_BIN=str(lay.tmp / "gone")))
    assert proc.returncode != 0 and "AGENT_ROUTER_BIN" in proc.stderr


def test_trace_uses_the_interpreter_behind_the_path_install(lay):
    marker = lay.tmp / "marker"
    py = _exe(lay.tmp / "python-x", f'echo "$@" > {marker}; echo "{{}}"')
    lay.path_tool(shebang=f"#!{py}")
    proc = _run(lay.bin / "trace", TRACE_PAYLOAD, lay.env())
    assert (proc.returncode, proc.stdout) == (0, "{}\n")
    assert marker.read_text().strip().endswith("trace.py")


def test_trace_with_a_dead_shebang_falls_to_python3_and_still_answers(lay):
    lay.path_tool(shebang=f"#!{lay.tmp}/missing/python")
    proc = _run(lay.bin / "trace", TRACE_PAYLOAD, lay.env(system_python=True))
    assert (proc.returncode, proc.stdout) == (0, "{}\n")


def test_trace_fails_open_when_no_interpreter_resolves(lay):
    proc = _run(lay.bin / "trace", TRACE_PAYLOAD, lay.env())
    assert (proc.returncode, proc.stdout) == (0, "{}\n")


def test_the_scripts_resolve_through_the_one_helper():
    for name in ("hook", "trace", "mcp"):
        text = (BIN / name).read_text()
        assert "_resolve.sh" in text and ".venv" not in text.replace("checkout .venv", "")


# --- --version ------------------------------------------------------------------------------------


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("agent-router ") and out.split()[1][0].isdigit()


# --- INSTALL-02: doctor ---------------------------------------------------------------------------


def make_tree(base: Path, *, manifest: bool = False, schema: bool = True) -> tuple[Path, dict]:
    """A copy of the integration under ``base/repo/integrations/`` and an environment that
    makes every check healthy (a fake plugin root, offline embedder, real router binary)."""
    integ = base / "repo" / "integrations" / "first-principles"
    shutil.copytree(
        INTEG, integ, ignore=shutil.ignore_patterns("runs", "handoff", "__pycache__", "*.md")
    )
    root = base / "fp-root"
    (root / "references").mkdir(parents=True)
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": NAME, "version": "9"}))
    if schema:
        shutil.copy(INTEG / "contract" / "summary-schema.json", root / "references")
    if manifest:
        (root / "references" / "integration.json").write_text(json.dumps(FALLBACK))
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(base),
        "AGENT_ROUTER_BIN": str(REAL_BIN),
        "AGENT_ROUTER_PYTHON": sys.executable,
        "AGENT_ROUTER_STATE_DIR": str(base / "state"),
        "AGENT_ROUTER_EMBEDDER": "hashing",
        "AGENT_ROUTER_PLUGIN_CACHE": "",
        "FP_PLUGIN_ROOT": str(root),
    }
    return integ, env


def by_name(checks) -> dict[str, doctor.Check]:
    assert len({c.name for c in checks}) == len(checks)
    return {c.name: c for c in checks}


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    integ, env = make_tree(tmp_path_factory.mktemp("healthy"))
    return by_name(doctor.run_checks(integ, env=env))


@pytest.fixture
def fast(monkeypatch):
    """Replace the MCP round trip (a second-scale subprocess) for the checks that do not test it."""
    monkeypatch.setattr(
        doctor, "_check_mcp", lambda ctx: doctor.Check("mcp server", doctor.PASS, "stubbed")
    )


def expect(baseline, checks, **changed):
    """Exactly the named checks changed status against the healthy baseline; the rest did not."""
    got = by_name(checks)
    assert set(got) == set(baseline)
    for name, check in got.items():
        key = name.replace(" ", "_")
        want = changed.get(key, baseline[name].status)
        assert check.status == want, f"{name}: {check.status} {check.detail}"
    return got


def test_healthy_tree_has_no_failure_and_reaches_the_real_mcp_server(baseline):
    assert not [c for c in baseline.values() if c.status == doctor.FAIL], baseline
    assert baseline["mcp server"].status == doctor.PASS and "calc" in baseline["mcp server"].detail
    assert baseline["router binary"].detail.endswith(f"agent-router {cli._version()}")
    assert baseline["summary schema"].detail.count("plugin_root") == 1
    assert baseline["manifest"].status == doctor.WARN  # the plugin publishes none: pinned copy


def test_a_published_manifest_is_a_pass(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path, manifest=True)
    got = expect(baseline, doctor.run_checks(integ, env=env), manifest=doctor.PASS)
    assert "manifest_version 1" in got["manifest"].detail and "env" in got["manifest"].detail


def test_a_recorded_root_is_a_pass(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path, manifest=True)
    rec = Path(env["AGENT_ROUTER_STATE_DIR"]) / "integration" / f"{NAME}.root"
    rec.parent.mkdir(parents=True)
    rec.write_text(env.pop("FP_PLUGIN_ROOT"))
    expect(baseline, doctor.run_checks(integ, env=env), manifest=doctor.PASS)


def test_a_plugin_cache_manifest_warns_about_staleness(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path, manifest=True)
    env.pop("FP_PLUGIN_ROOT")
    cached = tmp_path / "cache" / "market" / NAME / "1.0"
    shutil.copytree(tmp_path / "fp-root", cached)
    env["AGENT_ROUTER_PLUGIN_CACHE"] = str(tmp_path / "cache")
    got = expect(
        baseline, doctor.run_checks(integ, env=env), plugin_root=doctor.WARN, manifest=doctor.WARN
    )
    assert "plugin cache" in got["plugin root"].detail
    assert "may be stale" in got["manifest"].detail and "FP_PLUGIN_ROOT" in got["manifest"].detail
    assert "--plugin-dir" in got["manifest"].detail


def test_no_plugin_at_all_falls_back_with_warnings(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    env.pop("FP_PLUGIN_ROOT")
    got = expect(
        baseline, doctor.run_checks(integ, env=env), plugin_root=doctor.WARN, manifest=doctor.WARN
    )
    assert "FP_PLUGIN_ROOT" in got["plugin root"].detail
    assert "pinned" in got["summary schema"].detail


def test_binary_missing_is_a_failure(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    env["AGENT_ROUTER_BIN"] = str(tmp_path / "gone")
    got = expect(baseline, doctor.run_checks(integ, env=env), router_binary=doctor.FAIL)
    assert "AGENT_ROUTER_BIN" in got["router binary"].detail


def test_a_binary_without_version_support_is_a_failure(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    env["AGENT_ROUTER_BIN"] = str(_exe(tmp_path / "old", "echo 'unrecognized' >&2; exit 2"))
    got = expect(baseline, doctor.run_checks(integ, env=env), router_binary=doctor.FAIL)
    assert "old install" in got["router binary"].detail


def test_path_install_is_found_and_names_its_branch(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    env.pop("AGENT_ROUTER_BIN")
    stubs = tmp_path / "stubs"
    _exe(stubs / "agent-router", "echo 'agent-router 9.9.9'")
    env["PATH"] = f"{stubs}{os.pathsep}{env['PATH']}"
    got = expect(baseline, doctor.run_checks(integ, env=env))
    assert "(path)" in got["router binary"].detail and "9.9.9" in got["router binary"].detail


def test_a_checkout_venv_outranks_a_path_install(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    env.pop("AGENT_ROUTER_BIN")
    venv = _exe(tmp_path / "repo" / ".venv" / "bin" / "agent-router", "echo 'agent-router 1.1.1'")
    _exe(tmp_path / "stubs" / "agent-router", "echo 'agent-router 9.9.9'")
    env["PATH"] = f"{tmp_path / 'stubs'}{os.pathsep}{env['PATH']}"
    got = expect(baseline, doctor.run_checks(integ, env=env))
    detail = got["router binary"].detail
    assert str(venv) in detail and "(checkout)" in detail and "is not used" in detail


def test_trace_interpreter_missing_is_a_failure(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    env["AGENT_ROUTER_PYTHON"] = str(tmp_path / "gone")
    expect(baseline, doctor.run_checks(integ, env=env), trace_interpreter=doctor.FAIL)


def test_old_python_is_a_failure(fast, monkeypatch, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    monkeypatch.setattr(doctor, "MIN_PYTHON", (99, 0))
    expect(baseline, doctor.run_checks(integ, env=env), python=doctor.FAIL)


def test_broken_descriptor_fails_and_skips_what_needs_it(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    (integ / "descriptor.json").write_text("{not json")
    got = by_name(doctor.run_checks(integ, env=env))
    assert got["descriptor"].status == doctor.FAIL
    for name in ("plugin root", "manifest", "summary schema", "catalog", "calibration"):
        assert got[name].status == doctor.WARN and "skipped" in got[name].detail
    for name in ("router binary", "state dir", "timeout binary", "python"):
        assert got[name].status == doctor.PASS


@pytest.mark.parametrize(
    "content, want, why",
    [
        (None, doctor.FAIL, "cannot read"),
        ("garbage", doctor.FAIL, "not valid JSON"),
        (json.dumps({"schema_version": 7, "fields": {}}), doctor.WARN, "accepts [1]"),
    ],
)
def test_summary_schema_problems(fast, tmp_path, baseline, content, want, why):
    integ, env = make_tree(tmp_path)
    env["AGENT_ROUTER_FP_SCHEMA"] = str(tmp_path / "s.json")
    if content is not None:
        (tmp_path / "s.json").write_text(content)
    got = expect(baseline, doctor.run_checks(integ, env=env), summary_schema=want)
    assert why in got["summary schema"].detail


def test_a_manifest_emitting_an_unaccepted_schema_version_warns(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path, manifest=True)
    root = Path(env["FP_PLUGIN_ROOT"])
    data = json.loads((root / "references" / "integration.json").read_text())
    data["summary"]["schema_version"] = 2
    (root / "references" / "integration.json").write_text(json.dumps(data))
    got = expect(
        baseline,
        doctor.run_checks(integ, env=env),
        manifest=doctor.PASS,
        summary_schema=doctor.WARN,
    )
    assert "emits version 2" in got["summary schema"].detail


def test_catalog_problems_are_failures(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    (integ / "catalog.yaml").write_text("entries: [unclosed")
    got = by_name(doctor.run_checks(integ, env=env))
    assert got["catalog"].status == doctor.FAIL
    assert got["router binary"].status == doctor.PASS and got["hooks wiring"].status == doctor.PASS


def test_a_catalog_missing_the_descriptors_entries_fails(fast, tmp_path, baseline):
    import yaml

    integ, env = make_tree(tmp_path)
    cat = yaml.safe_load((integ / "catalog.yaml").read_text())
    cat["entries"] = [e for e in cat["entries"] if e["id"] != "exact-calc"]
    (integ / "catalog.yaml").write_text(yaml.safe_dump(cat))
    got = expect(baseline, doctor.run_checks(integ, env=env), catalog=doctor.FAIL)
    assert "exact-calc" in got["catalog"].detail


def test_calibration_problems_warn(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    (integ / "calibration.json").write_text("not json")
    expect(baseline, doctor.run_checks(integ, env=env), calibration=doctor.WARN)
    data = json.loads((INTEG / "calibration.json").read_text())
    for block in data.values():
        block["catalog_version"] = "other"
    (integ / "calibration.json").write_text(json.dumps(data))
    got = expect(baseline, doctor.run_checks(integ, env=env), calibration=doctor.WARN)
    assert "not fp-" in got["calibration"].detail


def test_unknown_backend_fails(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    env["AGENT_ROUTER_BACKEND"] = "no-such-backend"
    expect(baseline, doctor.run_checks(integ, env=env), decider_backend=doctor.FAIL)


@pytest.mark.parametrize("cached, want", [(True, doctor.PASS), (False, doctor.WARN)])
def test_missing_model_weights_warn(fast, monkeypatch, tmp_path, baseline, cached, want):
    integ, env = make_tree(tmp_path)
    env["AGENT_ROUTER_EMBEDDER"] = "model2vec"
    monkeypatch.setattr(doctor, "_weights_cached_offline", lambda e: (cached, "no network"))
    got = expect(baseline, doctor.run_checks(integ, env=env), decider_backend=want)
    if not cached:
        assert "first hook call" in got["decider backend"].detail


def test_the_offline_weights_probe_fails_on_an_empty_cache(tmp_path):
    ok, why = doctor._weights_cached_offline(
        {**os.environ, "HF_HOME": str(tmp_path / "hf"), "HF_HUB_CACHE": str(tmp_path / "hf")}
    )
    assert ok is False and why


def test_the_mcp_check_fails_when_the_server_does_not_start(tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    _exe(integ / "plugin" / "bin" / "mcp", "echo boom >&2; exit 3")
    got = expect(baseline, doctor.run_checks(integ, env=env), mcp_server=doctor.FAIL)
    assert "boom" in got["mcp server"].detail or "exited" in got["mcp server"].detail


def _fake_server(path: Path, tools: list[str] | None) -> Path:
    """A stdio MCP stub: answers initialize and tools/list with ``tools`` (None: never answers)."""
    body = (
        "import json, sys, time\n"
        f"tools = {tools!r}\n"
        "def send(i, result):\n"
        "    print(json.dumps({'jsonrpc': '2.0', 'id': i, 'result': result}), flush=True)\n"
        "for line in sys.stdin:\n"
        "    m = json.loads(line)\n"
        "    if m.get('method') == 'initialize':\n"
        "        send(m['id'], {'protocolVersion': '2024-11-05', 'capabilities': {},\n"
        "                       'serverInfo': {'name': 'x', 'version': '0'}})\n"
        "    elif m.get('method') == 'tools/list' and tools is not None:\n"
        "        send(m['id'], {'tools': [{'name': t} for t in tools]})\n"
        "time.sleep(30)\n"
    )
    return _exe(path, body, f"#!{sys.executable}")


def test_mcp_exchange_reads_tool_names_and_times_out(tmp_path):
    ok = _fake_server(tmp_path / "ok", ["calc", "other"])
    assert doctor._mcp_exchange([str(ok)], os.environ, 5) == ["calc", "other"]
    silent = _fake_server(tmp_path / "silent", None)
    assert "no tools/list answer within 1 s" in doctor._mcp_exchange([str(silent)], os.environ, 1)


def test_the_mcp_check_wants_the_calc_tool(tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    _exe(integ / "plugin" / "bin" / "mcp", f"exec {_fake_server(tmp_path / 'srv', ['other'])}")
    got = expect(baseline, doctor.run_checks(integ, env=env), mcp_server=doctor.FAIL)
    assert "'calc'" in got["mcp server"].detail


def test_wiring_problems_are_failures(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    (integ / "plugin" / "bin" / "hook").chmod(0o644)
    got = expect(baseline, doctor.run_checks(integ, env=env), hooks_wiring=doctor.FAIL)
    assert "bin/hook" in got["hooks wiring"].detail


def test_a_renamed_agent_type_breaks_the_static_matchers(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path, manifest=True)
    root = Path(env["FP_PLUGIN_ROOT"])
    data = json.loads((root / "references" / "integration.json").read_text())
    data["agent_type"] = "acme:solver"
    (root / "references" / "integration.json").write_text(json.dumps(data))
    got = expect(
        baseline, doctor.run_checks(integ, env=env), manifest=doctor.PASS, hooks_wiring=doctor.FAIL
    )
    assert "acme:solver" in got["hooks wiring"].detail


def test_a_calculator_matcher_that_drifted_fails(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    path = integ / "plugin" / "hooks" / "hooks.json"
    path.write_text(path.read_text().replace("mcp__plugin_agent-router-fp_agent_router__calc", "x"))
    got = expect(baseline, doctor.run_checks(integ, env=env), hooks_wiring=doctor.FAIL)
    assert "calculator" in got["hooks wiring"].detail


def test_unwritable_state_dir_fails(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    env["AGENT_ROUTER_STATE_DIR"] = str(blocker / "state")
    expect(baseline, doctor.run_checks(integ, env=env), state_dir=doctor.FAIL)


def test_state_dir_check_leaves_nothing_behind(fast, tmp_path):
    integ, env = make_tree(tmp_path)
    doctor.run_checks(integ, env=env)
    assert list(Path(env["AGENT_ROUTER_STATE_DIR"]).iterdir()) == []


def test_missing_fcntl_warns(fast, monkeypatch, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    monkeypatch.setattr(doctor, "_has_fcntl", lambda: False)
    got = expect(baseline, doctor.run_checks(integ, env=env), file_locking=doctor.WARN)
    assert "skipped" in got["file locking"].detail


def test_missing_timeout_warns(fast, tmp_path, baseline):
    integ, env = make_tree(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    env["PATH"] = str(empty)
    got = expect(baseline, doctor.run_checks(integ, env=env), timeout_binary=doctor.WARN)
    assert "wall-clock" in got["timeout binary"].detail


def test_an_exception_inside_a_check_is_that_checks_failure(monkeypatch, tmp_path):
    integ, env = make_tree(tmp_path)

    def boom(ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(doctor, "_check_timeout", boom)
    monkeypatch.setattr(
        doctor, "_check_mcp", lambda ctx: doctor.Check("mcp server", doctor.PASS, "stubbed")
    )
    got = by_name(doctor.run_checks(integ, env=env))
    assert got["timeout"].status == doctor.FAIL and "boom" in got["timeout"].detail
    assert got["state dir"].status == doctor.PASS


# --- the command ----------------------------------------------------------------------------------


def test_cli_prints_one_line_per_check_and_exits_0_without_failures(
    fast, tmp_path, monkeypatch, capsys
):
    integ, env = make_tree(tmp_path)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert cli.main(["doctor", "--integration", str(integ)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == len(doctor._CHECKS)
    assert all(ln.split()[0] in {"PASS", "WARN", "FAIL"} for ln in lines)
    assert lines[0].startswith("PASS  router binary")


def test_cli_exits_1_on_a_failure_and_not_on_warnings(fast, tmp_path, monkeypatch, capsys):
    integ, env = make_tree(tmp_path)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PATH", str(tmp_path))  # a WARN (no timeout) only
    assert cli.main(["doctor", "--integration", str(integ)]) == 0
    assert "WARN  timeout binary" in capsys.readouterr().out
    monkeypatch.setenv("AGENT_ROUTER_BIN", str(tmp_path / "gone"))
    assert cli.main(["doctor", "--integration", str(integ), "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert {c["name"]: c["status"] for c in out["checks"]}["router binary"] == "FAIL"


def test_a_bare_name_resolves_to_the_checkouts_integrations_dir(tmp_path):
    assert doctor.find_integration("first-principles") == INTEG
    assert doctor.find_integration(str(INTEG)) == INTEG
    assert doctor.find_integration("nonesuch") == Path("nonesuch")
