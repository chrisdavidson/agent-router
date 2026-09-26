import json
import subprocess
import sys

import pytest

from agent_router import cli


@pytest.fixture(autouse=True)
def hashing(monkeypatch):
    monkeypatch.setenv("AGENT_ROUTER_EMBEDDER", "hashing")


def test_route_json_prompt(capsys):
    rc = cli.main(
        ["route", "compute 3**80 exactly", "--backend", "local", "--embedder", "hashing", "--json"]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["choice"] in {"exact-calc", "none"}
    assert out["action"] in {"suggest", "native"}
    assert set(out["probabilities"]) >= {"exact-calc", "none"}
    assert "threshold" in out and "backend" in out


def test_route_json_tool_point(capsys):
    rc = cli.main(
        [
            "route",
            "run the tests",
            "--point",
            "tool",
            "--tool",
            "Bash",
            "--input",
            '{"command": "pytest -q"}',
            "--embedder",
            "hashing",
            "--json",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "choice" in out
    assert set(out["options"]) == {
        "exact-calc",
        "json-query",
        "html-to-markdown",
        "repo-stats",
        "none",
    }


def test_route_skipped_has_null_choice(capsys):
    rc = cli.main(
        ["route", "x", "--point", "tool", "--tool", "Edit", "--embedder", "hashing", "--json"]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "skipped"
    assert out["choice"] is None


def test_route_text_output(capsys):
    assert cli.main(["route", "git status", "--embedder", "hashing"]) == 0
    assert "action" in capsys.readouterr().out


def test_route_bad_input_json(capsys):
    with pytest.raises(SystemExit):
        cli.main(["route", "x", "--point", "tool", "--tool", "Bash", "--input", "{bad"])


def test_unknown_backend_errors(capsys):
    assert cli.main(["route", "x", "--backend", "nope", "--embedder", "hashing"]) == 2
    assert "unknown backend" in capsys.readouterr().err


def test_unavailable_backend_errors(capsys, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert cli.main(["eval", "--backend", "jev"]) == 2
    assert "not available" in capsys.readouterr().err


def test_eval_json(capsys):
    rc = cli.main(["eval", "--backend", "local", "--embedder", "hashing", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["split"] == "test"
    assert {"accuracy", "fpr", "misroute_rate", "per_entry", "confusions", "cases"} <= set(out)
    assert out["n"] == len([c for c in out["cases"]])


def test_eval_text(capsys):
    assert cli.main(["eval", "--embedder", "hashing", "--split", "cal"]) == 0
    out = capsys.readouterr().out
    assert "accuracy" in out and "FPR" in out


def test_calibrate_writes_file(tmp_path, capsys):
    out = tmp_path / "cal.json"
    rc = cli.main(["calibrate", "--embedder", "hashing", "--out", str(out), "--quick"])
    assert rc == 0
    data = json.loads(out.read_text())
    assert "hashing" in data and "threshold" in data["hashing"]


def test_demo_and_run_missing_modules_are_reported(capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "agent_router.demo.server", None)
    monkeypatch.setitem(sys.modules, "agent_router.agent", None)
    assert cli.main(["demo", "--port", "8799"]) == 1
    assert "demo" in capsys.readouterr().err.lower()
    assert cli.main(["run", "hello"]) == 1
    assert "agent" in capsys.readouterr().err.lower()


def test_cli_import_is_light():
    code = (
        "import sys, agent_router.cli; "
        "heavy = ('claude_agent_sdk', 'fastapi', 'uvicorn', 'model2vec'); "
        "bad = [m for m in heavy if m in sys.modules]; "
        "print(bad)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_help_lists_subcommands(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    for sub in ("route", "eval", "calibrate", "demo", "run"):
        assert sub in out


# -- default backend, cascade, shell flags --------------------------------------------------


class _Always:
    def __init__(self, name, choice="none"):
        self.name = name
        self.choice = choice

    def decide(self, state, options):
        from agent_router.core.types import ChoiceResult

        probs = {o: (1.0 if o == self.choice else 0.0) for o in options}
        return ChoiceResult(self.choice, probs, 1.0, backend=self.name, latency_ms=1.0)


def _fake_cascade(monkeypatch):
    from agent_router.deciders import registry
    from agent_router.deciders.cascade import CascadeDecider

    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test")

    def make(name, catalog):
        if name == "cascade":  # local unsure -> escalates to a fake jev
            return CascadeDecider(_Always("local", "exact-calc"), _Always("jev", "exact-calc"))
        return _Always(name)

    monkeypatch.setattr(registry, "make_decider", make)


def test_backend_defaults_to_local_without_jev_key(capsys):
    assert cli.main(["route", "compute 3**80 exactly", "--embedder", "hashing", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["backend"] == "local"


def test_backend_defaults_to_cascade_with_jev_key(capsys, monkeypatch):
    _fake_cascade(monkeypatch)
    assert cli.main(["route", "compute 3**80 exactly", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["backend"] == "cascade:jev"
    assert [s["role"] for s in out["stages"]] == ["primary", "confirm"]
    assert cli.main(["route", "compute 3**80 exactly"]) == 0
    assert "escalated to jev" in capsys.readouterr().out


def test_eval_reports_escalation_for_cascade(capsys, monkeypatch):
    _fake_cascade(monkeypatch)
    assert cli.main(["eval", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["backend"] == "cascade"
    assert out["routing"]["escalation_rate"] == 1.0
    assert cli.main(["eval"]) == 0
    assert "escalation" in capsys.readouterr().out


def test_calibrate_cascade_writes_block(tmp_path, capsys, monkeypatch):
    _fake_cascade(monkeypatch)
    out = tmp_path / "cal.json"
    assert cli.main(["calibrate-cascade", "--out", str(out)]) == 0
    block = json.loads(out.read_text())["cascade"]
    assert block["native_gate"] == 1.0  # local always sure of none: never needs jev
    assert "native_gate" in capsys.readouterr().out


def test_calibrate_cascade_needs_jev(capsys):
    assert cli.main(["calibrate-cascade"]) == 2
    assert "not available" in capsys.readouterr().err


def test_demo_has_allow_shell_and_no_host(monkeypatch):
    import agent_router.demo.server as server

    seen = {}
    monkeypatch.setattr(server, "main", lambda **kw: seen.update(kw))
    assert cli.main(["demo", "--port", "8799"]) == 0
    assert seen == {"port": 8799, "allow_shell": False}
    assert cli.main(["demo", "--allow-shell"]) == 0
    assert seen["allow_shell"] is True
    with pytest.raises(SystemExit):
        cli.main(["demo", "--host", "0.0.0.0"])


def test_run_passes_allow_shell(monkeypatch, capsys):
    import agent_router.agent as agent

    seen = {}

    async def fake_run(prompt, router, workspace, on_event, **kw):
        seen.update(kw, backend=router.decider.name)
        return "ok"

    monkeypatch.setattr(agent, "run_agent", fake_run)
    assert cli.main(["run", "hi", "--embedder", "hashing"]) == 0
    assert seen == {"allow_shell": False, "backend": "local"}
    assert cli.main(["run", "hi", "--embedder", "hashing", "--allow-shell"]) == 0
    assert seen["allow_shell"] is True
