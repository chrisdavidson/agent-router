"""The integration manifest: format, resolution, derivation, and no hard-coded identity.

MANIFEST-01..04, TRACE-03, CONDUCT-04 (the prompt skip pattern). The hook tests run the real
``plugin/bin/hook`` script.
"""

import ast
import copy
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from agent_router.contracts import integration as integ_mod
from agent_router.contracts import manifest as mf
from agent_router.core.catalog import CatalogError, load_catalog

ROOT = Path(__file__).resolve().parents[1]
INTEG = ROOT / "integrations" / "first-principles"
PLUGIN = INTEG / "plugin"
FALLBACK_FILE = INTEG / "manifest.fallback.json"
FALLBACK = json.loads(FALLBACK_FILE.read_text())
NAME = FALLBACK["plugin_name"]
AGENT = FALLBACK["agent_type"]


# -- helpers ------------------------------------------------------------------------------------


def make_root(base: Path, manifest: dict | None = None, *, schema: bool = True) -> Path:
    """A fake plugin root; ``manifest`` None = the plugin publishes none."""
    (base / "references").mkdir(parents=True, exist_ok=True)
    (base / ".claude-plugin").mkdir(exist_ok=True)
    (base / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": NAME}))
    if manifest is not None:
        (base / "references" / "integration.json").write_text(json.dumps(manifest))
    if schema:
        (base / "references" / "summary-schema.json").write_text("{}")
    return base


def variant(**changes) -> dict:
    m = copy.deepcopy(FALLBACK)
    for key, value in changes.items():
        m[key] = value
    return m


def resolve(tmp_path, *, env=None, recorded=None, cache=None):
    return mf.resolve_manifest(
        NAME,
        fallback=FALLBACK_FILE,
        env=env or {},
        root_env="FP_PLUGIN_ROOT",
        recorded_root_file=recorded,
        cache_dirs=[cache] if cache else [tmp_path / "no-cache"],
    )


# -- the format (MANIFEST-01) ------------------------------------------------------------------


def test_the_fallback_is_a_valid_manifest():
    m = mf.load_manifest(FALLBACK_FILE)
    assert (m.manifest_version, m.plugin_name, m.agent_type) == (1, NAME, AGENT)
    assert m.output_glob.startswith(m.output_dir + "/")
    assert m.launcher.startswith(m.command_prefix) and m.capabilities_used == ("exact-arithmetic",)


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({**FALLBACK, "added_later": {"x": 1}}))
    assert mf.load_manifest(path).agent_type == AGENT


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.update(manifest_version=2),
        lambda m: m.update(manifest_version="1"),
        lambda m: m.update(manifest_version=True),
        lambda m: m.pop("agent_type"),
        lambda m: m.update(agent_type=""),
        lambda m: m.update(output="x"),
        lambda m: m["output"].pop("glob"),
        lambda m: m["summary"].update(schema_version="1"),
        lambda m: m["summary"].update(schema="/etc/passwd"),
        lambda m: m.update(examples_dir="../elsewhere"),
        lambda m: m.update(capabilities_used="exact-arithmetic"),
    ],
)
def test_an_invalid_manifest_is_refused(tmp_path, mutate):
    data = copy.deepcopy(FALLBACK)
    mutate(data)
    path = tmp_path / "m.json"
    path.write_text(json.dumps(data))
    with pytest.raises(mf.ManifestError):
        mf.load_manifest(path)


@pytest.mark.parametrize("text", ["", "{", "[]", '"x"'])
def test_unreadable_manifests_are_refused(tmp_path, text):
    path = tmp_path / "m.json"
    path.write_text(text)
    with pytest.raises(mf.ManifestError):
        mf.load_manifest(path)
    with pytest.raises(mf.ManifestError):
        mf.load_manifest(tmp_path / "missing.json")


# -- resolution (MANIFEST-02) ------------------------------------------------------------------


def test_resolution_env(tmp_path):
    root = make_root(tmp_path / "r", variant(agent_type="acme:agent"))
    res = resolve(tmp_path, env={"FP_PLUGIN_ROOT": str(root)})
    assert (res.source, res.plugin_root, res.manifest.agent_type) == ("env", root, "acme:agent")
    assert res.warnings == ()


def test_resolution_recorded_root_file(tmp_path):
    root = make_root(tmp_path / "r", variant(agent_type="acme:agent"))
    rec = tmp_path / "state" / "integration" / f"{NAME}.root"
    rec.parent.mkdir(parents=True)
    rec.write_text(str(root) + "\n")
    res = resolve(tmp_path, recorded=rec)
    assert (res.source, res.plugin_root, res.manifest.agent_type) == (
        "recorded",
        root,
        "acme:agent",
    )


def test_resolution_cache_takes_the_newest_manifest(tmp_path):
    cache = tmp_path / "cache"
    old = make_root(cache / "market" / NAME / "1.0.0", variant(agent_type="acme:old"))
    new = make_root(cache / "market" / NAME / "2.0.0", variant(agent_type="acme:new"))
    os.utime(old / "references" / "integration.json", (1_000_000, 1_000_000))
    os.utime(new / "references" / "integration.json", (2_000_000, 2_000_000))
    res = resolve(tmp_path, cache=cache)
    assert (res.source, res.plugin_root, res.manifest.agent_type) == ("cache", new, "acme:new")
    assert mf.CACHE_STALE_WARNING in res.warnings  # the cache can be stale; the record says so
    os.utime(old / "references" / "integration.json", (3_000_000, 3_000_000))
    assert resolve(tmp_path, cache=cache).manifest.agent_type == "acme:old"


def test_resolution_falls_back_when_no_plugin_is_found(tmp_path):
    res = resolve(tmp_path)
    assert (res.source, res.plugin_root) == ("fallback", None)
    assert res.manifest == mf.load_manifest(FALLBACK_FILE)


def test_resolution_keeps_the_root_when_the_plugin_publishes_no_manifest(tmp_path):
    """Today's state: the plugin is installed, the manifest does not exist yet."""
    root = make_root(tmp_path / "r", None)
    res = resolve(tmp_path, env={"FP_PLUGIN_ROOT": str(root)})
    assert (res.source, res.plugin_root) == ("fallback+root", root)
    assert res.manifest.agent_type == AGENT and res.warnings
    cache = tmp_path / "cache"
    cached = make_root(cache / "market" / NAME / "9.20.0", None)
    res = resolve(tmp_path, cache=cache)
    assert (res.source, res.plugin_root) == ("fallback+root", cached)
    assert mf.CACHE_STALE_WARNING in res.warnings


def test_resolution_order_env_then_recorded_then_cache(tmp_path):
    env_root = make_root(tmp_path / "e", variant(agent_type="acme:env"))
    rec_root = make_root(tmp_path / "r", variant(agent_type="acme:rec"))
    cache = tmp_path / "cache"
    make_root(cache / "m" / NAME / "1", variant(agent_type="acme:cache"))
    rec = tmp_path / "root"
    rec.write_text(str(rec_root))
    env = {"FP_PLUGIN_ROOT": str(env_root)}
    assert resolve(tmp_path, env=env, recorded=rec, cache=cache).manifest.agent_type == "acme:env"
    assert resolve(tmp_path, recorded=rec, cache=cache).manifest.agent_type == "acme:rec"
    assert resolve(tmp_path, cache=cache).manifest.agent_type == "acme:cache"


def test_a_root_that_is_not_a_directory_is_skipped_with_a_warning(tmp_path):
    rec = tmp_path / "root"
    rec.write_text(str(tmp_path / "gone"))
    res = resolve(tmp_path, env={"FP_PLUGIN_ROOT": str(tmp_path / "nope")}, recorded=rec)
    assert res.source == "fallback" and res.plugin_root is None
    assert any("FP_PLUGIN_ROOT" in w for w in res.warnings)
    assert any("recorded plugin root" in w for w in res.warnings)


def test_the_resolver_names_no_environment_variable_itself(tmp_path):
    root = make_root(tmp_path / "r", variant(agent_type="acme:agent"))
    elsewhere = mf.resolve_manifest(
        NAME,
        fallback=FALLBACK_FILE,
        env={"MY_ROOT": str(root), "FP_PLUGIN_ROOT": str(tmp_path)},
        root_env="MY_ROOT",
        cache_dirs=[],
    )
    assert elsewhere.plugin_root == root


# -- degradation (MANIFEST-04) -------------------------------------------------------------------


@pytest.mark.parametrize(
    "case, why",
    [
        ("version", "not supported"),
        ("shape", "expected"),
        ("plugin", "plugin_name"),
        ("schema", "summary.schema"),
        ("json", "cannot read"),
    ],
)
def test_a_bad_manifest_degrades_to_the_fallback_with_a_warning(tmp_path, case, why):
    bad = {
        "version": variant(manifest_version=7),
        "shape": variant(agent_type=None),
        "plugin": variant(plugin_name="other"),
        "schema": variant(),
        "json": None,
    }[case]
    root = make_root(tmp_path / "r", bad, schema=case != "schema")
    if case == "json":
        (root / "references" / "integration.json").write_text("{not json")
    res = resolve(tmp_path, env={"FP_PLUGIN_ROOT": str(root)})
    assert (res.source, res.plugin_root) == ("fallback+root", root)
    assert res.manifest == mf.load_manifest(FALLBACK_FILE)
    assert any(why in w for w in res.warnings), res.warnings


# -- catalog variables (MANIFEST-03) --------------------------------------------------------------


def _catalog_file(tmp_path, **entry) -> Path:
    base = {
        "id": "a",
        "kind": "agent",
        "name": "A ${v.name}",
        "project": "p",
        "license": "MIT",
        "url": "u",
        "what": "w",
        "target": "${v.target}",
        "points": ["prompt"],
        "agents": ["${v.target}", "main"],
        "examples": ["echo ${HOME}"],
    }
    path = tmp_path / "c.yaml"
    import yaml

    path.write_text(yaml.safe_dump({"entries": [{**base, **entry}]}))
    return path


def test_catalog_variables_fill_strings_and_lists(tmp_path):
    cat = load_catalog(_catalog_file(tmp_path), variables={"v.name": "N", "v.target": "x:y"})
    (e,) = cat.entries
    assert (e.name, e.target, e.agents) == ("A N", "x:y", ("x:y", "main"))
    assert e.examples == ("echo ${HOME}",)  # exemplar text is never substituted


def test_an_unresolved_variable_is_a_catalog_error(tmp_path):
    with pytest.raises(CatalogError, match=r"unresolved variable \$\{v.target\}"):
        load_catalog(_catalog_file(tmp_path), variables={"v.name": "N"})


def test_without_variables_nothing_is_substituted(tmp_path):
    (e,) = load_catalog(_catalog_file(tmp_path)).entries
    assert e.target == "${v.target}"


def test_the_integration_catalog_is_filled_from_the_manifest(tmp_path):
    path = INTEG / "catalog.yaml"
    cat = load_catalog(path, variables=integ_mod.variables_for_catalog(path, {}))
    assert cat.get("first-principles-agent").target == AGENT
    calc = cat.get("exact-calc")
    assert calc.agents == (AGENT,)
    assert calc.target == "mcp__plugin_agent-router-fp_agent_router__calc"


def test_renaming_the_agent_type_retargets_the_catalog(tmp_path):
    root = make_root(tmp_path / "r", variant(agent_type="acme:solver", plugin_name=NAME))
    env = {"FP_PLUGIN_ROOT": str(root), "AGENT_ROUTER_PLUGIN_CACHE": ""}
    path = INTEG / "catalog.yaml"
    cat = load_catalog(path, variables=integ_mod.variables_for_catalog(path, env))
    assert cat.get("first-principles-agent").target == "acme:solver"
    assert cat.get("exact-calc").agents == ("acme:solver",)
    from agent_router.core.types import HookPoint

    assert [e.id for e in cat.eligible(HookPoint.TOOL, "Bash", "acme:solver")] == ["exact-calc"]
    assert cat.eligible(HookPoint.TOOL, "Bash", AGENT) == []


def test_derived_skip_patterns():
    integ = integ_mod.load_integration(INTEG)
    manifest = mf.load_manifest(FALLBACK_FILE)
    skip_input, skip_prompt = integ_mod.skip_patterns(integ, manifest)
    assert re.search(skip_input, 'cat >> ".first-principles/a.md"')
    assert re.search(skip_input, "cd /w/.first-principles && python3 x")
    assert not re.search(skip_input, "ls /w/src")
    for prompt in (
        "/first-principles:first-principles-analysis Is it?",
        "  /agent-router-fp:analyze Is it?",
    ):
        assert re.search(skip_prompt, prompt)
    for prompt in ("Is it good? /first-principles: later", "/first-principlesX:go", "analyse it"):
        assert not re.search(skip_prompt, prompt)


def test_skip_patterns_escape_what_the_manifest_says():
    integ = integ_mod.load_integration(INTEG)
    odd = mf.parse_manifest(
        variant(command_prefix="/a.b+:", output={"dir": ".o(x)", "glob": ".o(x)/*.md"})
    )
    skip_input, skip_prompt = integ_mod.skip_patterns(integ, odd)
    assert re.search(skip_input, "cat .o(x)/f") and not re.search(skip_input, "cat .oox/f")
    assert re.search(skip_prompt, "/a.b+:go") and not re.search(skip_prompt, "/aXb+:go")


# -- the hook, end to end (CONDUCT-04) -----------------------------------------------------------


def _run_hook(payload, state: Path, **env) -> dict:
    full = {
        **os.environ,
        "AGENT_ROUTER_STATE_DIR": str(state),
        "AGENT_ROUTER_EMBEDDER": "hashing",
        **env,
    }
    for var in ("AGENT_ROUTER_SKIP_INPUT", "AGENT_ROUTER_SKIP_PROMPT"):
        full.pop(var, None)
        full.update({k: v for k, v in env.items() if k == var})
    out = subprocess.run(
        [str(PLUGIN / "bin" / "hook")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full,
        timeout=60,
        check=True,
    )
    return json.loads(out.stdout)


def _audit(state: Path, session="s") -> list[dict]:
    path = state / "audit" / f"{session}.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines()]


@pytest.mark.parametrize(
    "prompt",
    [
        "/first-principles:first-principles-analysis Is a four-day week better?",
        "/agent-router-fp:analyze Is a four-day week better?",
    ],
)
def test_prompts_from_either_plugin_get_no_delegation_note(tmp_path, prompt):
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s", "prompt": prompt}
    assert _run_hook(payload, tmp_path) == {}
    (rec,) = _audit(tmp_path)
    assert (rec["action"], rec["reason"]) == ("skipped", "skip pattern")


def test_a_report_write_is_skipped_by_the_derived_pattern(tmp_path):
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "s",
        "prompt_id": "p",
        "agent_type": AGENT,
        "tool_name": "Bash",
        "tool_input": {"command": "cat >> .first-principles/a.md <<'X'\n12 x 1500\nX"},
    }
    assert _run_hook(payload, tmp_path) == {}
    assert _audit(tmp_path)[0]["reason"] == "skip pattern"


def test_an_explicit_skip_pattern_beats_the_derived_one(tmp_path):
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "s",
        "prompt": "/first-principles:first-principles-analysis Is a four-day week better?",
    }
    _run_hook(payload, tmp_path, AGENT_ROUTER_SKIP_PROMPT="^never-matches$")
    assert _audit(tmp_path)[0]["reason"] != "skip pattern"


def test_the_skip_patterns_follow_a_renamed_manifest(tmp_path):
    root = make_root(
        tmp_path / "root",
        variant(
            agent_type="acme:solver",
            command_prefix="/acme:",
            output={"dir": ".acme-out", "glob": ".acme-out/report-*.md"},
        ),
    )
    env = {"FP_PLUGIN_ROOT": str(root)}
    write = {
        "hook_event_name": "PreToolUse",
        "session_id": "w",
        "prompt_id": "p",
        "agent_type": "acme:solver",
        "tool_name": "Bash",
        "tool_input": {"command": "cat >> .acme-out/report-1.md <<'X'\nx\nX"},
    }
    _run_hook(write, tmp_path / "state", **env)
    assert _audit(tmp_path / "state", "w")[0]["reason"] == "skip pattern"
    old = {**write, "session_id": "o", "tool_input": {"command": "cat >> .first-principles/a.md"}}
    _run_hook(old, tmp_path / "state", **env)
    assert _audit(tmp_path / "state", "o")[0]["reason"] != "skip pattern"
    prompt = {"hook_event_name": "UserPromptSubmit", "session_id": "q", "prompt": "/acme:go now"}
    _run_hook(prompt, tmp_path / "state", **env)
    assert _audit(tmp_path / "state", "q")[0]["reason"] == "skip pattern"


def test_the_resolution_is_recorded_once_in_the_session_state(tmp_path):
    root = make_root(tmp_path / "root", None)
    env = {"FP_PLUGIN_ROOT": str(root)}
    for prompt in ("first", "second"):
        payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s", "prompt": prompt}
        _run_hook(payload, tmp_path / "state", **env)
    state = json.loads((tmp_path / "state" / "sessions" / "s.json").read_text())
    assert state["integration"]["source"] == "fallback+root"
    assert state["integration"]["plugin_root"] == str(root)
    assert state["integration"]["manifest_version"] == 1 and state["integration"]["warnings"]
    assert len(state["prompts"]) == 2  # the record does not disturb the rest of the state


def test_without_any_plugin_the_hook_still_works_from_the_fallback(tmp_path):
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s", "prompt": "hello there"}
    _run_hook(payload, tmp_path)
    state = json.loads((tmp_path / "sessions" / "s.json").read_text())
    assert (
        state["integration"]["source"] == "fallback" and state["integration"]["plugin_root"] is None
    )


# -- the trace follows the manifest ---------------------------------------------------------------


def _load_trace(name="fp_trace_manifest"):
    spec = importlib.util.spec_from_file_location(name, INTEG / "trace.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_trace_derives_its_identity_from_the_manifest(tmp_path, monkeypatch):
    root = make_root(
        tmp_path / "root",
        variant(
            agent_type="acme:solver",
            output={"dir": ".acme-out", "glob": ".acme-out/report-*.md"},
            summary={**FALLBACK["summary"], "heading": "## Machine summary"},
        ),
    )
    monkeypatch.setenv("FP_PLUGIN_ROOT", str(root))
    tr = _load_trace()
    assert tr.AGENT == "acme:solver" and tr.SUMMARY_HEADING == "## Machine summary"
    assert tr.INTEGRATION["source"] == "env" and tr.INTEGRATION["plugin_root"] == str(root)
    assert tr.REPORT_PATH.search("cat >> /w/.acme-out/report-1.md")
    assert not tr.REPORT_PATH.search("cat >> /w/.first-principles/analysis-1.md")
    assert tr.REPORT_DIR.search("cd .acme-out && ls") and tr.APPEND.search(">> x/.acme-out/")
    state = tmp_path / "state"
    work = tmp_path / "work"
    (work / ".acme-out").mkdir(parents=True)
    (work / ".acme-out" / "report-1.md").write_text("# R\n\n## 1. Problem Essence\n")
    base = {"session_id": "s", "agent_type": "acme:solver", "cwd": str(work), "agent_id": "a"}
    tr.handle({**base, "hook_event_name": "SubagentStart"}, state)
    end = tr.handle({**base, "hook_event_name": "SubagentStop"}, state)
    assert end["analysis"].endswith("report-1.md")
    assert end["integration"]["source"] == "env"
    # the old agent type is no longer this plugin's agent
    assert (
        tr.handle({**base, "agent_type": AGENT, "hook_event_name": "SubagentStart"}, state) is None
    )


def test_the_trace_run_end_records_how_the_manifest_was_found(tmp_path):
    tr = _load_trace("fp_trace_manifest_default")
    state = tmp_path / "state"
    base = {"session_id": "s", "agent_type": AGENT, "cwd": str(tmp_path), "agent_id": "a"}
    tr.handle({**base, "hook_event_name": "SubagentStart"}, state)
    end = tr.handle({**base, "hook_event_name": "SubagentStop"}, state)
    assert end["integration"] == {
        "source": "fallback",
        "plugin_root": None,
        "manifest_version": 1,
        "warnings": ["no plugin root found: using the pinned fallback"],
    }


def test_the_schema_comes_from_the_manifests_path_under_the_root(tmp_path, monkeypatch):
    tr = _load_trace("fp_trace_manifest_schema")
    root = make_root(tmp_path / "r", None, schema=False)
    monkeypatch.setenv("FP_PLUGIN_ROOT", str(root))
    monkeypatch.delenv("AGENT_ROUTER_FP_SCHEMA", raising=False)
    assert tr.schema_location()[1] == "pinned"  # the root has no schema file
    make_root(root, None)
    assert tr.schema_location() == (root / "references" / "summary-schema.json", "plugin_root")


# -- no hard-coded identity (MANIFEST-03) ------------------------------------------------------

BANNED = ("first-principles", "first_principles", "agent-router-fp")
"""Case-sensitive substrings that name the integrated plugin or its router-side plugin."""

# Code that must carry no such literal (a string literal in code, or an uncommented line of
# script/YAML). Comments and docstrings are allowed: they explain, they do not decide.
CHECKED = (
    PLUGIN / "bin" / "hook",
    INTEG / "catalog.yaml",
    INTEG / "trace.py",
    INTEG / "run_examples.py",
    INTEG / "battery.py",
    INTEG / "calibrate.py",
    *sorted((ROOT / "src" / "agent_router").rglob("*.py")),
)

# Allowed literals, each with its reason. A line of catalog.yaml matching one of these keys is
# attribution metadata (who publishes the entry), and the entry ids are the router's own handles,
# named in descriptor.json. bin/trace and hooks.json are held to the manifest by the test below.
ALLOWED_YAML_KEYS = re.compile(r"^\s*-?\s*(id|project|url):")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def find_literals(path: Path, text: str | None = None) -> list[str]:
    """Banned literals in code (not comments, not docstrings) of ``path``; strings found."""
    text = path.read_text() if text is None else text
    found: list[str] = []
    if path.suffix == ".py":
        tree = ast.parse(text)
        skip = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in skip
                and any(b in node.value for b in BANNED)
            ):
                found.append(f"{path.name}:{node.lineno}: {node.value[:60]!r}")
        return found
    for n, line in enumerate(text.splitlines(), 1):
        code = re.sub(r"(^|\s)#.*$", "", line)
        if path.suffix == ".yaml" and ALLOWED_YAML_KEYS.match(code):
            continue
        if any(b in code for b in BANNED):
            found.append(f"{path.name}:{n}: {code.strip()[:60]!r}")
    return found


def test_the_integration_code_names_no_plugin_literal():
    found = [f for path in CHECKED for f in find_literals(path)]
    assert found == []


def test_the_literal_scan_can_fail():
    """Must-fail controls: a literal put back into each kind of file is found."""
    hook = (PLUGIN / "bin" / "hook").read_text()
    assert find_literals(PLUGIN / "bin" / "hook", hook + '\nexport X="/first-principles:"\n')
    assert find_literals(INTEG / "catalog.yaml", "target: first-principles:first-principles\n")
    assert find_literals(INTEG / "catalog.yaml", "agents: [agent-router-fp]\n")
    assert find_literals(INTEG / "trace.py", 'AGENT = "first-principles:first-principles"\n')
    assert find_literals(INTEG / "trace.py", 'p = re.compile(r"\\.first-principles/")\n')
    assert find_literals(INTEG / "run_examples.py", 'x = f"{a}/first_principles"\n')
    # comments, docstrings and the allowed catalog metadata are not literals
    assert not find_literals(
        INTEG / "trace.py", '"""A first-principles run."""\n# first-principles\n'
    )
    assert not find_literals(PLUGIN / "bin" / "hook", "echo ok  # first-principles\n")
    assert not find_literals(INTEG / "catalog.yaml", "  - id: first-principles-agent\n")
    assert not find_literals(INTEG / "catalog.yaml", "    project: first-principles-skill\n")
    assert find_literals(INTEG / "catalog.yaml", "    name: first-principles-agent\n")


def test_the_checked_set_covers_what_the_plan_names():
    names = {p.name for p in CHECKED}
    assert {
        "hook",
        "catalog.yaml",
        "trace.py",
        "run_examples.py",
        "battery.py",
        "calibrate.py",
    } <= names
    assert any(p.name == "manifest.py" for p in CHECKED) and len(CHECKED) > 30


def test_the_descriptor_matches_the_catalog_and_the_plugin():
    integ = integ_mod.load_integration(INTEG)
    path = INTEG / "catalog.yaml"
    cat = load_catalog(path, variables=integ_mod.variables(integ, integ.fallback()))
    assert cat.get(integ.delegate_entry).kind == "agent"
    assert cat.get(integ.calc_entry).kind == "tool"
    assert integ.expected_plugin == mf.load_manifest(FALLBACK_FILE).plugin_name
    assert cat.get(integ.calc_entry).target == integ.calc_tool


def test_the_static_host_config_agrees_with_the_fallback_manifest():
    """The literals that cannot be derived (the host reads hooks.json; bin/trace answers before
    Python starts) equal the fallback manifest's agent_type, the calculator matcher equals
    self.calc_tool."""
    integ = integ_mod.load_integration(INTEG)
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    for event in ("SubagentStart", "SubagentStop"):
        assert [g["matcher"] for g in hooks[event]] == [AGENT]
    for event in ("PostToolUse", "PostToolUseFailure"):
        (group,) = hooks[event]
        assert integ.calc_tool in group["matcher"].split("|")
    script = (PLUGIN / "bin" / "trace").read_text()
    (default,) = re.findall(r'FP_AGENT_TYPE:-([^}"]+)\}', script)
    assert default == AGENT
    assert script.count(AGENT) == 1  # the one default, nowhere else


def test_the_trace_fast_path_follows_fp_agent_type(tmp_path):
    calls = []

    def run(agent_in_payload, **env):
        state = tmp_path / f"state{len(calls)}"
        calls.append(state)
        payload = {
            "hook_event_name": "SubagentStart",
            "session_id": "s",
            "agent_id": "a",
            "agent_type": agent_in_payload,
            "cwd": str(tmp_path),
        }
        subprocess.run(
            [str(PLUGIN / "bin" / "trace")],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env={**os.environ, "AGENT_ROUTER_STATE_DIR": str(state), **env},
            check=True,
        )
        files = list((state / "trace").glob("*.jsonl"))
        return bool(files)

    root = make_root(tmp_path / "root", variant(agent_type="acme:solver"))
    renamed = {"FP_PLUGIN_ROOT": str(root)}  # trace.py itself follows the manifest
    assert not run("acme:solver")
    assert not run("acme:solver", **renamed)  # the shell fast path still has the old default
    assert run("acme:solver", FP_AGENT_TYPE="acme:solver", **renamed)
    assert not run("acme:solver", FP_AGENT_TYPE=AGENT, **renamed)


# -- the worked examples (TRACE-03) ---------------------------------------------------------------


def _example(title):
    return f"# {title}\n\n**Scenario.** Should we build or buy {title}?\n\n## 1. Problem\n"


def _fake_plugin_with_examples(base: Path, manifest: dict | None) -> Path:
    root = make_root(base, manifest)
    (root / FALLBACK["examples_dir"]).mkdir(parents=True, exist_ok=True)
    for name in ("alpha", "beta"):
        (root / FALLBACK["examples_dir"] / f"{name}.md").write_text(_example(name))
    return root


def _run_examples(*argv, env=None):
    return subprocess.run(
        [sys.executable, str(INTEG / "run_examples.py"), *argv],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), **(env or {})},
        timeout=60,
    )


def test_run_examples_dry_run_lists_the_examples_under_the_plugin_root(tmp_path):
    root = _fake_plugin_with_examples(tmp_path / "plugin", None)
    out = _run_examples("--plugin-root", str(root), "--dry-run")
    assert out.returncode == 0, out.stderr
    assert "=== alpha" in out.stdout and "=== beta" in out.stdout
    assert FALLBACK["launcher"] + " Should we build or buy alpha?" in out.stdout


def test_run_examples_reads_the_examples_dir_from_the_manifest(tmp_path):
    root = _fake_plugin_with_examples(
        tmp_path / "plugin", variant(examples_dir="docs/cases", launcher="/acme:go")
    )
    (root / "docs" / "cases").mkdir(parents=True)
    (root / "docs" / "cases" / "gamma.md").write_text(_example("gamma"))
    out = _run_examples("--plugin-root", str(root), "--dry-run")
    assert out.returncode == 0, out.stderr
    assert "=== gamma" in out.stdout and "alpha" not in out.stdout
    assert "/acme:go Should we build or buy gamma?" in out.stdout


def test_run_examples_resolves_the_root_from_the_environment(tmp_path):
    root = _fake_plugin_with_examples(tmp_path / "plugin", None)
    out = _run_examples("--dry-run", "--only", "beta", env={"FP_PLUGIN_ROOT": str(root)})
    assert out.returncode == 0, out.stderr
    assert "=== beta" in out.stdout and "alpha" not in out.stdout


def test_run_examples_fp_repo_is_a_deprecated_alias(tmp_path):
    _fake_plugin_with_examples(tmp_path / "repo" / NAME, None)
    out = _run_examples("--fp-repo", str(tmp_path / "repo"), "--dry-run")
    assert out.returncode == 0, out.stderr
    assert "deprecated" in out.stderr and "=== alpha" in out.stdout


def test_run_examples_without_a_root_says_so(tmp_path):
    out = _run_examples("--dry-run", env={"FP_PLUGIN_ROOT": ""})
    assert out.returncode == 2 and "no plugin root" in out.stderr
    out = _run_examples("--plugin-root", str(tmp_path / "gone"), "--dry-run")
    assert out.returncode == 2 and "not a directory" in out.stderr


# -- the fallback against the real plugin ---------------------------------------------------------


def _real_plugin_root() -> Path | None:
    for cand in (
        os.environ.get("FP_PLUGIN_ROOT", ""),
        str(Path.home() / "Projects" / "first-principles-skill" / NAME),
    ):
        if cand and (Path(cand) / ".claude-plugin" / "plugin.json").is_file():
            return Path(cand)
    return None


def test_the_fallback_matches_the_installed_plugin():
    root = _real_plugin_root()
    if root is None:
        pytest.skip("no first-principles plugin tree here")
    m = mf.load_manifest(FALLBACK_FILE)
    assert (
        json.loads((root / ".claude-plugin" / "plugin.json").read_text())["name"] == m.plugin_name
    )
    agent = re.search(r"^name: (\S+)$", (root / "agents" / "first-principles.md").read_text(), re.M)
    assert agent and m.agent_type == f"{m.plugin_name}:{agent.group(1)}"
    assert m.launcher == m.command_prefix + "first-principles-analysis"
    assert (root / "skills" / "first-principles-analysis" / "SKILL.md").is_file()
    schema = json.loads((root / m.schema).read_text())
    assert schema["schema_version"] == m.schema_version and schema["block"]["heading"] == m.heading
    assert list((root / m.examples_dir).glob("*.md"))
    assert m.output_dir in (root / "agents" / "first-principles.md").read_text()
    published = root / mf.MANIFEST_RELPATH
    if published.is_file():  # once the publisher ships one, it must agree with the pin
        assert mf.load_manifest(published) == m
