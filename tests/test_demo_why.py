"""The Trace tab's "why": the agent's own transcript joined to the trace by tool_use_id."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent_router.demo import server, why

CALC = "mcp__plugin_agent-router-fp_agent_router__calc_script"
PROMPT = (
    "Problem statement: price an LLC.\n"
    f"Exact arithmetic is available: mcp__x__calc for one expression and {CALC} for a script."
)


def _a(ts: str, *blocks: dict) -> dict:
    return {"type": "assistant", "timestamp": ts, "message": {"content": list(blocks)}}


def _result(ts: str, tid: str, text: str) -> dict:
    return {
        "type": "user",
        "timestamp": ts,
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tid,
                    "content": [{"type": "text", "text": text}],
                }
            ]
        },
    }


def _use(tid: str, name: str, **args) -> dict:
    return {"type": "tool_use", "id": tid, "name": name, "input": args}


TRANSCRIPT = [
    {"type": "user", "timestamp": "2026-10-16T10:00:00.000Z", "message": {"content": PROMPT}},
    _a("2026-10-16T10:00:05.000Z", {"type": "text", "text": "I'll start with the fee schedule."}),
    _a(
        "2026-10-16T10:00:06.000Z",
        _use("t1", "Bash", command="curl -s fees", description="Fetch the PA fee schedule"),
    ),
    _result("2026-10-16T10:00:08.000Z", "t1", "ok"),
    _a(
        "2026-10-16T10:04:34.000Z",
        {"type": "text", "text": "Research is done. Now I'll check the cost arithmetic."},
    ),
    _a(
        "2026-10-16T10:04:40.000Z",
        {"type": "thinking", "thinking": "Sum the state fees per option."},
    ),
    _a("2026-10-16T10:04:41.000Z", _use("t2", CALC, script="a = 125 + 7\nprint(a)\nprint(2852)")),
    _result("2026-10-16T10:04:42.000Z", "t2", '{"result":"a = 132\\n2852 = 2852"}'),
    _a(
        "2026-10-16T10:04:59.000Z",
        {"type": "text", "text": "Arithmetic checked. Now I'll write the package."},
    ),
    _a(
        "2026-10-16T10:05:25.000Z",
        _use(
            "t3",
            "Bash",
            command="cat > costs.md <<'EOF'\nFormation: $132; year one $2,852\nEOF",
            description="Write the cost sheet",
        ),
    ),
    _a("2026-10-16T10:05:30.000Z", _use("t4", "Bash", command="echo 1320 13200")),
]


def test_explain_joins_each_call_to_what_the_agent_said_and_did_with_it() -> None:
    w = why.explain(TRANSCRIPT)
    assert w["prompt"].startswith("Problem statement")
    assert [n["text"][:8] for n in w["narrations"]] == ["I'll sta", "Research", "Arithmet"]
    calc = w["calls"]["t2"]
    assert calc["said"]["text"].startswith("Research is done")
    assert calc["thinking"] == "Sum the state fees per option."
    assert calc["said_after"]["text"].startswith("Arithmetic checked")
    assert CALC in calc["offered_by"]  # the prompt line that names the tool
    # its numbers turn up in the later write, with or without a thousands separator; 1320 is not 132
    assert calc["used_in"] == [{"tool_use_id": "t3", "numbers": ["132", "2852"]}]
    assert w["calls"]["t1"]["purpose"] == "Fetch the PA fee schedule"
    assert w["calls"]["t1"]["thinking"] is None
    assert w["calls"]["t4"]["thinking"] is None  # reasoning belongs to the turn that made the call


def test_find_transcript_only_opens_the_runs_own_agent_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cc"))
    sub = tmp_path / "cc" / "projects" / "-home-me-proj" / "sess-1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-abc.jsonl").write_text("{}\n")
    assert why.find_transcript("sess-1", "abc") == sub / "agent-abc.jsonl"  # found under projects/
    main = tmp_path / "cc" / "projects" / "-home-me-proj" / "sess-1.jsonl"
    assert why.find_transcript("sess-1", "abc", [str(main)]) == sub / "agent-abc.jsonl"
    other = tmp_path / "secret.jsonl"
    other.write_text("{}\n")
    assert why.find_transcript("sess-1", "zzz", [str(other)]) is None  # a hint is never read as-is
    assert why.find_transcript("sess-1", "../etc") is None


def test_why_endpoint_reads_the_transcript_beside_the_recorded_path(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "nowhere"))
    proj = tmp_path / "projects" / "p"
    sub = proj / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-a1.jsonl").write_text("\n".join(json.dumps(x) for x in TRANSCRIPT) + "\n")
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    recs = [
        {
            "ts": "2026-10-16T10:00:00+00:00",
            "session": "s1",
            "agent_id": "a1",
            "kind": "run_start",
            "transcript_path": str(proj / "s1.jsonl"),
        },
        {
            "ts": "2026-10-16T09:00:00+00:00",
            "session": "s1",
            "agent_id": "gone",
            "kind": "run_start",
        },
    ]
    (trace_dir / "s1.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    c = TestClient(
        server.create_app(audit_dir=tmp_path / "audit", trace_dir=trace_dir),
        base_url="http://127.0.0.1:8765",
    )
    body = c.get("/api/trace/s1/why").json()
    run = body["runs"]["a1"]
    assert run["transcript"].endswith("agent-a1.jsonl")
    assert run["calls"]["t2"]["said"]["text"].startswith("Research is done")
    assert body["runs"]["gone"] == {"transcript": None}  # no transcript: the tab says so
    assert c.get("/api/trace/nope/why").status_code == 404


def test_why_endpoint_falls_back_to_what_the_trace_kept(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "nowhere"))
    kept = why.compact(why.explain(TRANSCRIPT))
    assert why.expand(kept)["calls"]["t2"]["said"]["text"].startswith("Research is done")
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    recs = [
        {"ts": "2026-10-16T10:00:00+00:00", "session": "s1", "agent_id": "a1", "kind": "run_start"},
        {
            "ts": "2026-10-16T10:06:00+00:00",
            "session": "s1",
            "agent_id": "a1",
            "kind": "run_end",
            "why": kept,
        },
    ]
    (trace_dir / "s1.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    c = TestClient(
        server.create_app(audit_dir=tmp_path / "audit", trace_dir=trace_dir),
        base_url="http://127.0.0.1:8765",
    )
    run = c.get("/api/trace/s1/why").json()["runs"]["a1"]
    assert run["transcript"] is None and run["kept"] is True
    calc = run["calls"]["t2"]
    assert calc["said_after"]["text"].startswith("Arithmetic checked")
    assert CALC in calc["offered_by"] and calc["used_in"][0]["tool_use_id"] == "t3"
