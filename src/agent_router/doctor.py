"""``agent-router doctor --integration DIR``: is this install able to do its job, and if not, why.

One line per check, ``PASS`` / ``WARN`` / ``FAIL`` with a reason. ``FAIL`` means a part the
integration needs does not work (the command then exits 1); ``WARN`` means it works but degraded
or from a source worth knowing about (a stale plugin cache, a model that would be downloaded on
the first hook call). Nothing here names a particular plugin: the integration directory's
``descriptor.json`` and the resolved manifest (:mod:`agent_router.contracts.integration`)
supply every name. The checks run the same lookups the hooks run, with the same precedence:

* the router binary / trace interpreter resolve in the order of
  ``integrations/<name>/plugin/bin/_resolve.sh`` (env, checkout ``.venv``, ``PATH``), which a
  test holds equal to this module's :func:`resolve_bin` / :func:`resolve_python`;
* the summary schema location is :func:`agent_router.contracts.integration.schema_location`,
  the function the trace calls.
"""

from __future__ import annotations

import json
import logging
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
MIN_PYTHON = (3, 11)
MCP_TIMEOUT_S = 10.0
SUBPROCESS_TIMEOUT_S = 10.0
BIN_NAME = "agent-router"
PLUGIN_DIR = "plugin"
CACHE_WARNING = (
    "the plugin cache may be stale: Claude Code's Agent tool runs the installed copy; use "
    "--plugin-dir and {root_env} for a working tree"
)


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # PASS | WARN | FAIL
    detail: str

    def line(self) -> str:
        return f"{self.status:<4}  {self.name:<18}  {self.detail}"

    def record(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class Resolution:
    path: str | None
    branch: str  # env | checkout | path | system | none
    error: str = ""


# --- binary / interpreter resolution (mirrors bin/_resolve.sh) --------------------------------


def _is_exe(path: str | Path) -> bool:
    p = Path(path)
    return p.is_file() and os.access(p, os.X_OK)


def _on_path(name: str, env: Mapping[str, str]) -> str | None:
    found = shutil.which(name, path=env.get("PATH", ""))
    return found if found and _is_exe(found) else None


def checkout_root(integration: Path) -> Path:
    """The checkout an integration directory sits in (``<repo>/integrations/<name>``)."""
    return integration.resolve().parent.parent


def resolve_bin(repo: Path, env: Mapping[str, str]) -> Resolution:
    """The router executable the plugin's scripts would run: ``AGENT_ROUTER_BIN`` (final when
    set), else the checkout ``.venv``, else ``agent-router`` on PATH."""
    named = env.get("AGENT_ROUTER_BIN", "")
    if named:
        if _is_exe(named):
            return Resolution(named, "env")
        return Resolution(None, "none", f"AGENT_ROUTER_BIN={named} is not an executable file")
    venv = repo / ".venv" / "bin" / BIN_NAME
    if _is_exe(venv):
        return Resolution(str(venv), "checkout")
    found = _on_path(BIN_NAME, env)
    if found:
        return Resolution(found, "path")
    return Resolution(
        None,
        "none",
        f"{BIN_NAME} not found: set AGENT_ROUTER_BIN, run 'make install' in {repo}, "
        "or 'uv tool install' the fork",
    )


_EXEC_FORM = re.compile(r"""^'''exec'\s+['"]([^'"]+)['"]""")


def shebang_python(script: str) -> str | None:
    """The interpreter behind ``script``'s shebang when it is an absolute, executable python.

    Two forms: ``#!/abs/python``, and ``#!/bin/sh`` followed by the ``'''exec' '/abs/python'``
    line uv writes when the interpreter path is too long for a shebang."""
    try:
        with open(script, "rb") as fh:
            first = fh.readline(512).decode("utf-8", "replace").rstrip("\r\n")
            second = fh.readline(1024).decode("utf-8", "replace").rstrip("\r\n")
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    parts = first[2:].split()
    interp = parts[0] if parts else ""
    if not interp.startswith("/"):
        return None
    if Path(interp).name in ("sh", "bash", "dash"):
        found = _EXEC_FORM.match(second)
        interp = found.group(1) if found else ""
        if not interp.startswith("/"):
            return None
    if not Path(interp).name.startswith("python"):
        return None
    return interp if _is_exe(interp) else None


def resolve_python(repo: Path, env: Mapping[str, str]) -> Resolution:
    """The interpreter ``bin/trace`` would run: ``AGENT_ROUTER_PYTHON`` (final when set), the
    checkout ``.venv``, the shebang interpreter of ``agent-router`` on PATH, else ``python3``."""
    named = env.get("AGENT_ROUTER_PYTHON", "")
    if named:
        if _is_exe(named):
            return Resolution(named, "env")
        return Resolution(None, "none", f"AGENT_ROUTER_PYTHON={named} is not an executable file")
    venv = repo / ".venv" / "bin" / "python"
    if _is_exe(venv):
        return Resolution(str(venv), "checkout")
    tool = _on_path(BIN_NAME, env)
    if tool:
        interp = shebang_python(tool)
        if interp:
            return Resolution(interp, "path")
    system = _on_path("python3", env)
    if system:
        return Resolution(system, "system")
    return Resolution(None, "none", "no python interpreter found")


# --- the checks --------------------------------------------------------------------------------


class _Ctx:
    """What the checks share: the directory, the environment and what earlier checks loaded."""

    def __init__(self, integration: Path, env: Mapping[str, str]) -> None:
        self.dir = integration
        self.env = env
        self.repo = checkout_root(integration)
        self.plugin = integration / PLUGIN_DIR
        self.integ: Any = None
        self.resolved: Any = None
        self.catalog: Any = None
        self.state_root: Path | None = None


def _run(argv: list[str], env: Mapping[str, str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, capture_output=True, text=True, env=dict(env), timeout=timeout, check=False
    )


def _last_line(text: str) -> str:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def _check_binary(ctx: _Ctx) -> Check:
    res = resolve_bin(ctx.repo, ctx.env)
    if res.path is None:
        return Check("router binary", FAIL, res.error)
    try:
        proc = _run([res.path, "--version"], ctx.env, SUBPROCESS_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("router binary", FAIL, f"{res.path} does not run: {exc}")
    if proc.returncode != 0:
        why = _last_line(proc.stderr) or f"exit {proc.returncode}"
        return Check(
            "router binary",
            FAIL,
            f"{res.path} ({res.branch}) failed '--version' ({why}); is it an old install?",
        )
    extra = ""
    other = _on_path(BIN_NAME, ctx.env)
    if res.branch != "path" and other and Path(other).resolve() != Path(res.path).resolve():
        extra = f"; another {BIN_NAME} on PATH ({other}) is not used"
    return Check("router binary", PASS, f"{res.path} ({res.branch}): {proc.stdout.strip()}{extra}")


def _check_trace_python(ctx: _Ctx) -> Check:
    res = resolve_python(ctx.repo, ctx.env)
    if res.path is None:
        return Check("trace interpreter", FAIL, res.error)
    return Check("trace interpreter", PASS, f"{res.path} ({res.branch})")


def _check_python(ctx: _Ctx) -> Check:
    have = sys.version_info[:3]
    text = ".".join(str(n) for n in have)
    want = ".".join(str(n) for n in MIN_PYTHON)
    if have < MIN_PYTHON:
        return Check("python", FAIL, f"{text} is older than the {want} this package requires")
    return Check("python", PASS, f"{text} ({sys.executable})")


def _check_descriptor(ctx: _Ctx) -> Check:
    from agent_router.contracts.integration import IntegrationError, load_integration

    try:
        ctx.integ = load_integration(ctx.dir)
    except IntegrationError as exc:
        return Check("descriptor", FAIL, str(exc))
    i = ctx.integ
    return Check(
        "descriptor",
        PASS,
        f"integrates {i.expected_plugin!r} via plugin {i.own_plugin_name!r} ({ctx.dir})",
    )


def _need_integ(ctx: _Ctx, name: str) -> Check | None:
    if ctx.integ is None:
        return Check(name, WARN, "skipped: the descriptor did not load")
    return None


def _resolve_manifest(ctx: _Ctx) -> None:
    from agent_router.adapters.claude_code import state_root
    from agent_router.contracts.integration import resolve

    ctx.state_root = state_root(ctx.env)
    ctx.resolved = resolve(ctx.integ, env=ctx.env, state_root=ctx.state_root)


def _plugin_version(root: Path) -> str:
    try:
        v = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        return f"version {v['version']}" if isinstance(v.get("version"), str) else ""
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ""


def _check_plugin_root(ctx: _Ctx) -> Check:
    if (skip := _need_integ(ctx, "plugin root")) is not None:
        return skip
    try:
        _resolve_manifest(ctx)
    except Exception as exc:  # a broken pinned fallback is a build error: report it
        return Check("plugin root", FAIL, f"cannot resolve the manifest: {exc}")
    res, integ = ctx.resolved, ctx.integ
    if res.plugin_root is None:
        return Check(
            "plugin root",
            WARN,
            f"no {integ.expected_plugin} plugin found; set {integ.root_env} to a working tree "
            "(the pinned fallback manifest and schema are used)",
        )
    version = _plugin_version(res.plugin_root)
    shown = f"{res.plugin_root} ({version})" if version else str(res.plugin_root)
    from agent_router.contracts.manifest import CACHE_STALE_WARNING

    if CACHE_STALE_WARNING in res.warnings:  # found only in the plugin cache: may be stale
        return Check(
            "plugin root",
            WARN,
            f"{shown}, from the plugin cache, which may be older than the working tree; "
            f"set {integ.root_env} to the plugin you mean to run",
        )
    return Check("plugin root", PASS, shown)


def _check_manifest(ctx: _Ctx) -> Check:
    if ctx.resolved is None:
        return Check("manifest", WARN, "skipped: no manifest resolution")
    res, integ = ctx.resolved, ctx.integ
    man = res.manifest
    base = f"manifest_version {man.manifest_version}, agent {man.agent_type}"
    from agent_router.contracts.manifest import CACHE_STALE_WARNING

    notes = [w for w in res.warnings if w != CACHE_STALE_WARNING]
    if res.source in ("env", "recorded"):
        return Check("manifest", PASS, f"{base} (from {res.source})")
    if res.source == "cache":
        return Check(
            "manifest",
            WARN,
            f"{base} (from the plugin cache): " + CACHE_WARNING.format(root_env=integ.root_env),
        )
    why = "; ".join(notes) or "no manifest published"
    stale = (
        ["; " + CACHE_WARNING.format(root_env=integ.root_env)]
        if CACHE_STALE_WARNING in res.warnings
        else []
    )
    return Check("manifest", WARN, f"pinned fallback in use ({base}): {why}{''.join(stale)}")


def _check_schema(ctx: _Ctx) -> Check:
    if (skip := _need_integ(ctx, "summary schema")) is not None:
        return skip
    from agent_router.contracts.integration import schema_location
    from agent_router.contracts.summary_block import SchemaError, load_schema

    try:
        path, source = schema_location(ctx.integ, env=ctx.env, state_root=ctx.state_root or None)
    except Exception as exc:
        return Check("summary schema", FAIL, f"cannot locate the schema: {exc}")
    try:
        table = load_schema(path)
    except SchemaError as exc:
        return Check("summary schema", FAIL, f"{path} ({source}): {exc}")
    accepted = sorted(ctx.integ.accepted_schema_versions)
    if table.schema_version not in accepted:
        return Check(
            "summary schema",
            WARN,
            f"{path} ({source}) is version {table.schema_version}; the reader accepts {accepted}: "
            "blocks will be read but marked unverified",
        )
    emits = ctx.resolved.manifest.schema_version if ctx.resolved is not None else None
    if emits is not None and emits not in accepted:
        return Check(
            "summary schema",
            WARN,
            f"{path} ({source}) loads, but the manifest says the plugin emits version {emits}; "
            f"the reader accepts {accepted}",
        )
    note = ""
    if source == "pinned" and ctx.resolved is not None and ctx.resolved.plugin_root is not None:
        note = f"; the plugin root has no {ctx.resolved.manifest.schema}"
    return Check("summary schema", PASS, f"{path} ({source}), version {table.schema_version}{note}")


def _catalog_path(ctx: _Ctx) -> Path:
    named = ctx.env.get("AGENT_ROUTER_CATALOG", "").strip()
    return Path(named) if named else ctx.dir / "catalog.yaml"


def _check_catalog(ctx: _Ctx) -> Check:
    if (skip := _need_integ(ctx, "catalog")) is not None:
        return skip
    from agent_router.contracts.integration import variables
    from agent_router.core.catalog import CatalogError, load_catalog

    path = _catalog_path(ctx)
    manifest = (ctx.resolved or None) and ctx.resolved.manifest
    try:
        if manifest is None:
            manifest = ctx.integ.fallback()
        ctx.catalog = load_catalog(path, variables=variables(ctx.integ, manifest))
    except (OSError, CatalogError, ValueError) as exc:
        return Check("catalog", FAIL, f"{path}: {exc}")
    ids = {ctx.integ.delegate_entry, ctx.integ.calc_entry}
    missing = sorted(ids - {e.id for e in ctx.catalog.entries})
    if missing:
        return Check("catalog", FAIL, f"{path} loads but lacks the entries {missing}")
    return Check(
        "catalog",
        PASS,
        f"{path}: {len(ctx.catalog.entries)} entries, version {ctx.catalog.version}",
    )


def _check_calibration(ctx: _Ctx) -> Check:
    if (skip := _need_integ(ctx, "calibration")) is not None:
        return skip
    named = ctx.env.get("AGENT_ROUTER_CALIBRATION", "").strip()
    path = Path(named) if named else ctx.dir / "calibration.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Check("calibration", WARN, f"{path}: {exc}; the decider falls back to defaults")
    if not isinstance(data, dict) or not any(isinstance(v, dict) for v in data.values()):
        return Check("calibration", WARN, f"{path}: no calibration block; defaults apply")
    usable, notes = [], []
    version = ctx.catalog.version if ctx.catalog is not None else None
    for key, block in data.items():
        if not isinstance(block, dict):
            continue
        if block.get("feasible") is False:
            notes.append(f"{key} not feasible")
        elif version is not None and block.get("catalog_version") != version:
            notes.append(f"{key} fit for catalog {block.get('catalog_version')}, not {version}")
        else:
            usable.append(key)
    if not usable:
        return Check("calibration", WARN, f"{path}: " + "; ".join(notes) + "; defaults apply")
    suffix = f" (ignored: {'; '.join(notes)})" if notes else ""
    return Check("calibration", PASS, f"{path}: usable for {', '.join(usable)}{suffix}")


def _weights_cached_offline(env: Mapping[str, str]) -> tuple[bool, str]:
    """Can the embedding model load with the network off? Runs the real loader in a subprocess
    with ``HF_HUB_OFFLINE=1``, so a hit means the first hook call will not download."""
    code = "from agent_router.deciders.embedders import Model2VecEmbedder as M; M().load()"
    try:
        proc = _run([sys.executable, "-c", code], {**env, "HF_HUB_OFFLINE": "1"}, 60.0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, ""
    return False, _last_line(proc.stderr) or f"exit {proc.returncode}"


def _check_backend(ctx: _Ctx) -> Check:
    from agent_router.deciders.registry import BACKENDS, available_backends

    name = ctx.env.get("AGENT_ROUTER_BACKEND", "").strip() or "local"
    if name not in BACKENDS:
        return Check("decider backend", FAIL, f"unknown backend {name!r}; expected {BACKENDS}")
    if not available_backends().get(name, False):
        return Check(
            "decider backend", FAIL, f"{name!r} is not available here (missing package or API key)"
        )
    if name not in ("local", "cascade"):
        return Check("decider backend", PASS, f"{name} is available")
    from agent_router.deciders.embedders import HashingEmbedder
    from agent_router.deciders.local import LocalJevDecider

    native = ctx.catalog.native_examples if ctx.catalog is not None else ()
    version = ctx.catalog.version if ctx.catalog is not None else None
    logging.disable(logging.CRITICAL)  # calibration warnings are the calibration check's
    try:  # the classifier itself, on the offline embedder: construction, not the weights
        LocalJevDecider(embedder=HashingEmbedder(), native_examples=native, catalog_version=version)
    except Exception as exc:
        return Check("decider backend", FAIL, f"{name}: cannot construct the local decider: {exc}")
    finally:
        logging.disable(logging.NOTSET)
    choice = ctx.env.get("AGENT_ROUTER_EMBEDDER", "").strip().lower() or "model2vec"
    if choice == "hashing":
        return Check("decider backend", PASS, f"{name}, hashing embedder (no weights needed)")
    if choice != "model2vec":
        return Check("decider backend", FAIL, f"AGENT_ROUTER_EMBEDDER={choice!r}: not an embedder")
    ok, why = _weights_cached_offline(ctx.env)
    if ok:
        return Check("decider backend", PASS, f"{name}, model2vec weights available offline")
    return Check(
        "decider backend",
        WARN,
        f"{name}: embedding model weights not available offline ({why}); the first hook call "
        "will download them, or fail open to the uncalibrated hashing embedder",
    )


def _mcp_exchange(argv: list[str], env: Mapping[str, str], timeout: float) -> list[str] | str:
    """Start an MCP stdio server, initialize it and list its tools. The tool names, or a
    string saying what went wrong."""
    msgs = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-router-doctor", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(env),
        )
    except OSError as exc:
        return f"cannot start {argv[0]}: {exc}"
    try:
        assert proc.stdin is not None and proc.stdout is not None
        try:
            proc.stdin.write(("\n".join(json.dumps(m) for m in msgs) + "\n").encode())
            proc.stdin.flush()
        except OSError:
            pass  # it exited early: the read below reports it
        deadline = time.monotonic() + timeout
        buf = b""
        fd = proc.stdout.fileno()
        while time.monotonic() < deadline:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if ready:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                buf += chunk
                for line in buf.split(b"\n")[:-1]:
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(msg, dict) and msg.get("id") == 2:
                        tools = (msg.get("result") or {}).get("tools")
                        if isinstance(tools, list):
                            return [str(t.get("name")) for t in tools if isinstance(t, dict)]
                        return f"tools/list answered without tools: {str(msg)[:160]}"
            elif proc.poll() is not None:
                break
        err = b""
        if proc.poll() is not None and proc.stderr is not None:
            err = proc.stderr.read()
        if proc.poll() is not None:
            tail = _last_line(err.decode("utf-8", "replace"))
            return f"exited ({proc.returncode}) before listing tools: {tail}"
        return f"no tools/list answer within {timeout:g} s"
    finally:
        proc.kill()
        proc.wait()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()


def _check_mcp(ctx: _Ctx) -> Check:
    script = ctx.plugin / "bin" / "mcp"
    if not _is_exe(script):
        return Check("mcp server", FAIL, f"{script} is missing or not executable")
    result = _mcp_exchange([str(script)], ctx.env, MCP_TIMEOUT_S)
    if isinstance(result, str):
        return Check("mcp server", FAIL, f"{script}: {result}")
    if "calc" not in result:
        return Check("mcp server", FAIL, f"{script} started but lists {result}, not 'calc'")
    return Check("mcp server", PASS, f"{script} serves {', '.join(result)}")


def wiring_problems(plugin: Path, agent_type: str, calc_tool: str) -> list[str]:
    """What is wrong with the plugin's static host config: hooks.json commands that are not
    executable files, matchers that no longer name the manifest's agent / calculator, a trace
    script whose fast-path default is another agent, and a missing or non-executable MCP
    command."""
    problems: list[str] = []
    root_var = "${CLAUDE_PLUGIN_ROOT}"
    path = plugin / "hooks" / "hooks.json"
    try:
        hooks = json.loads(path.read_text(encoding="utf-8"))["hooks"]
        if not isinstance(hooks, dict):
            raise TypeError("'hooks' is not an object")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"cannot read {path}: {exc}"]
    commands: set[str] = set()
    for event, groups in hooks.items():
        for group in groups if isinstance(groups, list) else []:
            for hook in group.get("hooks", []):
                cmd = str(hook.get("command", ""))
                commands.add(cmd)
            matcher = group.get("matcher")
            if event in ("SubagentStart", "SubagentStop") and matcher != agent_type:
                problems.append(f"{event} matcher {matcher!r} is not the agent type {agent_type!r}")
            if event in ("PostToolUse", "PostToolUseFailure") and calc_tool not in str(
                matcher
            ).split("|"):
                problems.append(f"{event} matcher lacks the calculator tool {calc_tool}")
    try:
        mcp = json.loads((plugin / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
        commands.update(str(s.get("command", "")) for s in mcp.values())
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        problems.append(f"cannot read {plugin / '.mcp.json'}: {exc}")
    for cmd in sorted(commands):
        target = Path(cmd.replace(root_var, str(plugin)))
        if not _is_exe(target):
            problems.append(f"command {cmd} is not an executable file ({target})")
    trace = plugin / "bin" / "trace"
    try:
        defaults = re.findall(r"FP_AGENT_TYPE:-([^}\"]+)\}", trace.read_text(encoding="utf-8"))
    except OSError:
        defaults = []
    if defaults and defaults != [agent_type]:
        problems.append(f"bin/trace fast-path default {defaults} is not {agent_type!r}")
    return problems


def _check_wiring(ctx: _Ctx) -> Check:
    if ctx.integ is None or ctx.resolved is None:
        return Check("hooks wiring", WARN, "skipped: no manifest resolution")
    agent = ctx.resolved.manifest.agent_type
    problems = wiring_problems(ctx.plugin, agent, ctx.integ.calc_tool)
    if problems:
        return Check("hooks wiring", FAIL, "; ".join(problems))
    return Check("hooks wiring", PASS, f"matchers name {agent} and the calculator; commands exist")


def _check_state(ctx: _Ctx) -> Check:
    from agent_router.adapters.claude_code import state_root

    root = ctx.state_root or state_root(ctx.env)
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=root, prefix=".doctor-", delete=True) as fh:
            fh.write(b"x")
            fh.flush()
    except OSError as exc:
        return Check("state dir", FAIL, f"{root} is not writable: {exc}")
    return Check("state dir", PASS, f"{root} is writable")


def _has_fcntl() -> bool:
    try:
        import fcntl  # noqa: F401
    except ImportError:
        return False
    return True


def _check_fcntl(ctx: _Ctx) -> Check:
    if _has_fcntl():
        return Check("file locking", PASS, "fcntl is available")
    return Check(
        "file locking",
        WARN,
        "fcntl is unavailable on this platform: no lock, so session state writes are skipped "
        "under contention",
    )


def _check_timeout(ctx: _Ctx) -> Check:
    found = _on_path("timeout", ctx.env)
    if found:
        return Check("timeout binary", PASS, found)
    return Check(
        "timeout binary", WARN, "no 'timeout' on PATH: hooks run without a wall-clock guard"
    )


_CHECKS = (
    "_check_binary",
    "_check_trace_python",
    "_check_python",
    "_check_descriptor",
    "_check_plugin_root",
    "_check_manifest",
    "_check_schema",
    "_check_catalog",
    "_check_calibration",
    "_check_backend",
    "_check_mcp",
    "_check_wiring",
    "_check_state",
    "_check_fcntl",
    "_check_timeout",
)


def run_checks(integration_dir: str | Path, *, env: Mapping[str, str] = os.environ) -> list[Check]:
    """Run every check on the integration directory; never raises (an unexpected exception in
    a check is that check's FAIL)."""
    ctx = _Ctx(Path(integration_dir), env)
    out: list[Check] = []
    module = sys.modules[__name__]
    for fn_name in _CHECKS:  # looked up by name so a test can replace one check
        try:
            out.append(getattr(module, fn_name)(ctx))
        except Exception as exc:
            label = fn_name.removeprefix("_check_").replace("_", " ")
            out.append(Check(label, FAIL, f"internal error: {type(exc).__name__}: {exc}"))
    return out


def failed(checks: list[Check]) -> bool:
    return any(c.status == FAIL for c in checks)


def find_integration(arg: str) -> Path:
    """``arg`` as a directory, or a bare name resolved as ``<checkout>/integrations/<name>``
    when this package runs from a checkout."""
    direct = Path(arg)
    if (direct / "descriptor.json").is_file():
        return direct
    if os.sep not in arg and "/" not in arg:
        candidate = Path(__file__).resolve().parents[2] / "integrations" / arg
        if (candidate / "descriptor.json").is_file():
            return candidate
    return direct
