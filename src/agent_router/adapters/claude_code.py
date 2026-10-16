"""Claude Code command-hook adapter: hook JSON on stdin -> hook JSON on stdout.

``agent-router hook`` runs this once per hook call, in a fresh process, so the per-session
state the SDK adapter keeps in memory (recent prompts, the once-per-turn hint set) lives in
a small JSON file per session instead. Pure JSON in and out: no SDK import.

Input (verified on Claude Code 2.1.283): every payload has ``hook_event_name`` and
``session_id``, plus ``prompt_id`` (one per user prompt; subagent calls carry their parent
turn's). ``UserPromptSubmit`` adds ``prompt``; ``PreToolUse`` adds ``tool_name`` and
``tool_input``, and, for a call made inside a subagent, ``agent_type``.

Mapping:

- ``UserPromptSubmit`` -> ``point=prompt``, ``text`` = the prompt.
- ``PreToolUse`` -> ``point=tool`` (``skill`` for ``Skill``). On the main thread ``text`` is
  the turn's prompt; inside a subagent it is empty: the subagent works on its own task, not
  the user's words, so only the pending call is routed.
- ``turn_id`` = CRC32 of ``prompt_id`` (the prompt count when a host omits it).
- SUGGEST -> ``additionalContext``; ENFORCE -> ``permissionDecision: deny``; else ``{}``.

State and audit default to ``$AGENT_ROUTER_STATE_DIR``, else
``$XDG_STATE_HOME/agent-router``, else ``~/.local/state/agent-router``:
``sessions/<session>.json`` and ``audit/<session>.jsonl`` (``AGENT_ROUTER_AUDIT`` wins).
Every failure fails open: the caller prints ``{}``.

Concurrency: hook processes of one session overlap (the routing call takes ~0.45 s), so the
state file is written read-modify-write under an ``fcntl`` lock on ``<session>.json.lock``,
held only for the reload-merge-write and never across routing. Routing runs on a snapshot; at
commit the state is reloaded and merged (prompts appended, once-per-turn keys unioned,
``integration`` kept from the first writer). A SUGGEST whose (turn, entry) another process
recorded while this one was routing is suppressed (``{}``) and counted in
``duplicate_suggestions``, so with the lock held at most one process per (turn, entry) emits the
hint. A lock that cannot be taken within ``LOCK_WAIT_S`` (or no ``fcntl``) skips the write and
leaves the output as routed: fail open, state for that call is lost.

Never block (D-02): an agent type in ``AGENT_ROUTER_NEVER_BLOCK_AGENTS`` (plus the integrated
plugin's agent type, passed in by the CLI) is never denied. The router downgrades its ENFORCE to
an advisory hint (audit ``downgraded: true``), and ``to_output`` repeats the guard so a router
that did not (a custom factory) still cannot emit ``permissionDecision: deny`` for it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import zlib
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # non-POSIX: state writes are skipped (fail open), see state_lock
    fcntl = None  # type: ignore[assignment]

from agent_router.core.router import MAX_RECENT, Router
from agent_router.core.types import Action, Decision, HookPoint, RouterEvent

log = logging.getLogger(__name__)

POINTS = {"UserPromptSubmit": HookPoint.PROMPT, "PreToolUse": HookPoint.TOOL}
SKILL_TOOL = "Skill"
MAX_KEPT_PROMPTS = MAX_RECENT + 1
_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")

LOCK_WAIT_S = 2.0
"""Longest a hook waits for the session's state lock before skipping its write."""
LOCK_POLL_S = 0.01

RouterFactory = Callable[[Path | None, set[tuple[str, int, str]]], Router]
"""Builds the router for one hook call from (audit path or None, suggested-key seed)."""


def state_root(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("AGENT_ROUTER_STATE_DIR", "").strip():
        return Path(env["AGENT_ROUTER_STATE_DIR"].strip())
    base = env.get("XDG_STATE_HOME", "").strip() or str(Path.home() / ".local" / "state")
    return Path(base) / "agent-router"


def _safe_name(session: str) -> str:
    return _UNSAFE.sub("_", session)[:128] or "unknown"


safe_name = _safe_name  # public: the conductor's hand-off hook reads the same session file


def load_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def save_state(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        log.exception("cannot save hook state %s", path)


@contextmanager
def state_lock(path: Path, wait: float | None = None) -> Iterator[bool]:
    """Hold an exclusive lock on ``<path>.lock``; yields whether it was taken.

    Polls non-blockingly for up to ``wait`` seconds (default ``LOCK_WAIT_S``), so a stuck holder
    costs a hook at most that long. Yields False (never raises) on timeout, an unusable lock
    file, or a platform without ``fcntl``: the caller then skips its write.
    """
    wait = LOCK_WAIT_S if wait is None else wait
    if fcntl is None:
        log.warning("no fcntl: skipping session state write")
        yield False
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = path.with_name(path.name + ".lock").open("a+")
    except OSError:
        log.exception("cannot open state lock for %s", path)
        yield False
        return
    got = False
    try:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                got = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    log.warning("state lock busy for %.1fs: %s", wait, path)
                    break
                time.sleep(LOCK_POLL_S)
        yield got
    finally:
        if got:
            fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def never_block_agents(extra: Iterable[str] = ()) -> frozenset[str]:
    """Agent types that are never denied: ``AGENT_ROUTER_NEVER_BLOCK_AGENTS`` plus ``extra``."""
    raw = os.environ.get("AGENT_ROUTER_NEVER_BLOCK_AGENTS", "")
    return frozenset(a.strip() for a in [*raw.split(","), *extra] if a and a.strip())


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def turn_id(payload: dict[str, Any], prompt_count: int) -> int:
    prompt_id = payload.get("prompt_id")
    if isinstance(prompt_id, str) and prompt_id:
        return zlib.crc32(prompt_id.encode("utf-8"))
    return prompt_count


def to_event(payload: dict[str, Any], state: dict[str, Any]) -> RouterEvent | None:
    """The router event for one hook payload (updates ``state``), or None to ignore it."""
    point = POINTS.get(str(payload.get("hook_event_name") or ""))
    if point is None:
        return None
    session = str(payload.get("session_id") or "")
    prompts = [p for p in state.get("prompts", []) if isinstance(p, str)]
    agent_type = payload.get("agent_type")
    agent_type = agent_type if isinstance(agent_type, str) and agent_type else None
    if point == HookPoint.PROMPT:
        prompt = str(payload.get("prompt") or "")
        event = RouterEvent(
            point=point,
            session_id=session,
            turn_id=turn_id(payload, len(prompts) + 1),
            text=prompt,
            recent=tuple(prompts[-MAX_RECENT:]),
        )
        state["prompts"] = [*prompts, prompt][-MAX_KEPT_PROMPTS:]
        return event
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        return None
    tool_input = payload.get("tool_input")
    main = agent_type is None
    return RouterEvent(
        point=HookPoint.SKILL if tool_name == SKILL_TOOL else HookPoint.TOOL,
        session_id=session,
        turn_id=turn_id(payload, len(prompts)),
        text=(prompts[-1] if prompts else "") if main else "",
        tool_name=tool_name,
        tool_input=tool_input if isinstance(tool_input, dict) else {},
        recent=tuple(prompts[:-1][-MAX_RECENT:]) if main else (),
        agent_type=agent_type,
        tool_use_id=_str_or_none(payload.get("tool_use_id")),
        agent_id=_str_or_none(payload.get("agent_id")),
    )


def to_output(decision: Decision, hook_event: str, *, never_block: bool = False) -> dict[str, Any]:
    """The hook output. ``never_block`` turns an ENFORCE into advisory context (never a deny)."""
    if not decision.hint:
        return {}
    if decision.action == Action.ENFORCE and never_block:
        return {
            "hookSpecificOutput": {"hookEventName": hook_event, "additionalContext": decision.hint}
        }
    if decision.action == Action.ENFORCE and hook_event == "PreToolUse":
        spec = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": decision.hint,
        }
        return {"hookSpecificOutput": spec}
    if decision.action == Action.SUGGEST:
        return {
            "hookSpecificOutput": {"hookEventName": hook_event, "additionalContext": decision.hint}
        }
    return {}


def _turn_keys(raw: Any, turn: int) -> set[tuple[int, str]]:
    return {
        (int(k[0]), str(k[1]))
        for k in (raw if isinstance(raw, list) else [])
        if isinstance(k, (list, tuple))
        and len(k) == 2
        and isinstance(k[0], int)
        and isinstance(k[1], str)
        and k[0] == turn
    }


def _commit_state(
    path: Path,
    event: RouterEvent,
    decision: Decision,
    router_keys: set[tuple[str, int, str]],
    snapshot_keys: set[tuple[int, str]],
    added_prompt: str | None,
    integration: dict[str, Any] | None,
) -> bool:
    """Reload, merge and write the session state under the lock; True when this call's SUGGEST
    lost a race (another process recorded the same (turn, entry) while this one routed)."""
    with state_lock(path) as locked:
        if not locked:
            return False
        state = load_state(path)
        disk_keys = _turn_keys(state.get("suggested"), event.turn_id)
        mine = {(t, e) for s, t, e in router_keys if s == event.session_id and t == event.turn_id}
        duplicate = (
            decision.action == Action.SUGGEST
            and decision.entry_id is not None
            and (event.turn_id, decision.entry_id) in disk_keys - snapshot_keys
        )
        if added_prompt is not None:
            prompts = [p for p in state.get("prompts", []) if isinstance(p, str)]
            state["prompts"] = [*prompts, added_prompt][-MAX_KEPT_PROMPTS:]
        if integration is not None and "integration" not in state:
            state["integration"] = integration
        state["suggested"] = sorted([t, e] for t, e in disk_keys | mine)
        if duplicate:
            count = state.get("duplicate_suggestions")
            state["duplicate_suggestions"] = (count if isinstance(count, int) else 0) + 1
        save_state(path, state)
        return duplicate


def handle(
    payload: dict[str, Any],
    make_router: RouterFactory,
    root: Path | None = None,
    integration: dict[str, Any] | None = None,
    never_block: Iterable[str] = (),
) -> dict:
    """Route one hook payload; returns the hook output (``{}`` when nothing applies).

    ``integration`` is how the integrated plugin's manifest was resolved for this call
    (source, plugin root, manifest version, warnings). It is stored in the session state once,
    by the first call that commits. ``never_block`` are agent types that must never be denied
    (added to ``AGENT_ROUTER_NEVER_BLOCK_AGENTS``).
    """
    root = root if root is not None else state_root()
    session = _safe_name(str(payload.get("session_id") or ""))
    state_path = root / "sessions" / f"{session}.json"
    state = load_state(state_path)  # snapshot: routing runs on it, outside any lock
    event = to_event(payload, state)
    if event is None:
        return {}
    added_prompt = state["prompts"][-1] if event.point == HookPoint.PROMPT else None
    snapshot_keys = _turn_keys(state.get("suggested"), event.turn_id)
    seed = {
        (event.session_id, int(t), str(e))
        for t, e in state.get("suggested", [])
        if isinstance(t, int) and isinstance(e, str)
    }
    audit_env = os.environ.get("AGENT_ROUTER_AUDIT", "").strip()
    audit = Path(audit_env) if audit_env else root / "audit" / f"{session}.jsonl"
    if not audit_env:
        audit.parent.mkdir(parents=True, exist_ok=True)
    router = make_router(audit, seed)
    decision = router.route(event)
    duplicate = _commit_state(
        state_path, event, decision, router.suggested(), snapshot_keys, added_prompt, integration
    )
    if duplicate:  # another process already said it this turn
        return {}
    protected = never_block_agents(never_block)
    return to_output(
        decision,
        str(payload.get("hook_event_name")),
        never_block=event.agent_type is not None and event.agent_type in protected,
    )
