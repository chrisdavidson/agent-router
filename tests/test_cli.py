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
