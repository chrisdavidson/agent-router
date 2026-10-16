"""HOOK-04 baseline: wall-clock latency of the first-principles ``bin/hook`` as a subprocess.

Deselected by default (marker ``bench``); run with ``make bench``.  The test fails when a
payload's measured p95 exceeds 2x the committed baseline p95 in
tests/fixtures/fp/latency-baseline.json.  ``UPDATE_BASELINE=1`` rewrites that file on this host.
Timings are host-dependent: the baseline records the host it came from.
"""

import json
import os
import platform
import statistics
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.bench

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "integrations" / "first-principles" / "plugin" / "bin" / "hook"
BASELINE = ROOT / "tests" / "fixtures" / "fp" / "latency-baseline.json"
N = 20
WARMUP = 2
FACTOR = 2.0
AGENT = "first-principles:first-principles"


def _prompt(session: str) -> dict:
    return {
        "hook_event_name": "UserPromptSubmit",
        "session_id": session,
        "cwd": "/tmp",
        "prompt": "Analyse from first principles whether we should build or buy "
        "authentication, and estimate the cost.",
    }


def _bash_in_agent(session: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": session,
        "cwd": "/tmp",
        "agent_type": AGENT,
        "agent_id": "bench-agent",
        "tool_name": "Bash",
        "tool_use_id": f"toolu_{uuid.uuid4().hex[:12]}",
        "tool_input": {"command": "python3 -c 'print(17 * 2340 / 100)'"},
    }


PAYLOADS = {"user_prompt_routed": _prompt, "pretooluse_bash_in_fp_agent": _bash_in_agent}


def _p(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def _measure(make, state_dir: Path) -> list[float]:
    env = {**os.environ, "AGENT_ROUTER_STATE_DIR": str(state_dir)}
    for var in ("AGENT_ROUTER_AUDIT", "AGENT_ROUTER_DISABLED", "AGENT_ROUTER_BACKEND"):
        env.pop(var, None)  # the hook's default (local) backend
    times = []
    for i in range(WARMUP + N):
        body = json.dumps(make(f"bench-{uuid.uuid4().hex[:8]}"))  # fresh session: full path
        t0 = time.perf_counter()
        proc = subprocess.run(
            [str(HOOK)], input=body, capture_output=True, text=True, env=env, timeout=60
        )
        dt = (time.perf_counter() - t0) * 1000
        assert proc.returncode == 0 and proc.stdout.strip(), proc.stderr
        json.loads(proc.stdout)
        if i >= WARMUP:
            times.append(dt)
    return times


def _summary(times: list[float]) -> dict:
    return {
        "p50": round(statistics.median(times), 1),
        "p95": round(_p(times, 0.95), 1),
        "n": len(times),
    }


@pytest.mark.skipif(not HOOK.is_file(), reason="plugin hook missing")
def test_hook_latency_within_2x_of_baseline(tmp_path):
    if not (ROOT / ".venv" / "bin" / "agent-router").exists() and not os.environ.get(
        "AGENT_ROUTER_BIN"
    ):
        pytest.skip("no agent-router binary for bin/hook")
    measured = {name: _summary(_measure(make, tmp_path / name)) for name, make in PAYLOADS.items()}
    print("\nhook latency (ms):", json.dumps(measured))
    if os.environ.get("UPDATE_BASELINE"):
        record = {
            **measured,
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "host": f"{platform.system()} {platform.release()} {platform.machine()}, "
            f"python {platform.python_version()}; wall-clock of `bin/hook` subprocess, "
            f"{WARMUP} warm-up runs discarded, local decider backend",
        }
        BASELINE.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    for name, got in measured.items():
        limit = FACTOR * baseline[name]["p95"]
        assert got["p95"] <= limit, f"{name}: p95 {got['p95']} ms > {FACTOR}x baseline ({limit} ms)"
