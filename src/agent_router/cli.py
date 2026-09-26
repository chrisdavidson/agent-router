"""``agent-router`` command line: route, eval, calibrate, demo, run.

Heavy or optional modules (the demo server, the live agent, model weights) are imported
inside the command that needs them, so ``route`` / ``eval`` work without them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from agent_router.core.types import HookPoint, RouterEvent

EMBEDDERS = ("model2vec", "hashing")


class CliError(Exception):
    """A user-facing error: printed to stderr, exit status 2."""


# --- helpers ---------------------------------------------------------------------------


def _set_embedder(name: str | None) -> None:
    if name:
        os.environ["AGENT_ROUTER_EMBEDDER"] = name


def _check_backend(name: str) -> None:
    from agent_router.deciders.registry import BACKENDS, available_backends

    if name not in BACKENDS:
        raise CliError(f"unknown backend {name!r}; expected one of {', '.join(BACKENDS)}")
    if not available_backends().get(name, False):
        raise CliError(f"backend {name!r} is not available here (missing package or API key)")


def _router(args: argparse.Namespace):
    from agent_router.core.catalog import load_catalog
    from agent_router.evaluate import make_router

    _check_backend(args.backend)
    _set_embedder(getattr(args, "embedder", None))
    catalog = load_catalog()
    return make_router(
        args.backend,
        catalog,
        threshold=getattr(args, "threshold", None),
        timeout=getattr(args, "timeout", None),
        mode=getattr(args, "mode", "advisory"),
    )


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


# --- route -------------------------------------------------------------------------------


def cmd_route(args: argparse.Namespace) -> int:
    point = HookPoint(args.point)
    tool_name = args.tool
    if point == HookPoint.SKILL and tool_name is None:
        tool_name = "Skill"
    router = _router(args)
    event = RouterEvent(
        point=point,
        session_id="cli",
        turn_id=1,
        text=args.text,
        tool_name=tool_name,
        tool_input=args.input,
    )
    d = router.route(event)
    res = d.result
    out = {
        "action": str(d.action),
        "choice": res.choice if res else None,
        "entry_id": d.entry_id,
        "probabilities": res.probabilities if res else {},
        "confidence": res.confidence if res else None,
        "reason": d.reason,
        "hint": d.hint,
        "options": list(d.options),
        "backend": res.backend if res else args.backend,
        "latency_ms": res.latency_ms if res else None,
        "threshold": router.config.threshold,
    }
    if args.json:
        _print_json(out)
        return 0
    print(f"action     {out['action']}  ({d.reason})")
    print(f"choice     {out['choice']}")
    if res:
        print(f"confidence {res.confidence:.3f}   backend {res.backend}   {res.latency_ms:.1f} ms")
        for oid, p in sorted(res.probabilities.items(), key=lambda kv: -kv[1]):
            print(f"  {oid:<18} {p:6.3f} {'#' * round(p * 40)}")
    if d.hint:
        print(f"hint       {d.hint}")
    return 0


# --- eval --------------------------------------------------------------------------------


def cmd_eval(args: argparse.Namespace) -> int:
    from agent_router.deciders.local import embedder_key
    from agent_router.evaluate import DEFAULT_EVAL_SET, load_cases, run_eval

    cases = load_cases(args.cases or DEFAULT_EVAL_SET, split=args.split)
    router = _router(args)
    report = run_eval(lambda: router, cases)
    if args.json:
        _print_json(
            {
                "backend": args.backend,
                "embedder": embedder_key(getattr(router.decider, "embedder", None)),
                "split": args.split,
                "threshold": router.config.threshold,
                **report.to_dict(),
            }
        )
        return 0
    print(f"backend {args.backend}  split {args.split}  threshold {router.config.threshold:.2f}")
    print(
        f"n {report.n}  accuracy {report.accuracy:.3f}  FPR {report.fpr:.3f}  "
        f"misroute {report.misroute_rate:.3f}  errors {report.errors}"
    )
    print("per entry (precision / recall / support):")
    for label, m in report.per_entry.items():
        print(f"  {label:<18} {m['precision']:.2f} / {m['recall']:.2f} / {int(m['support'])}")
    if report.confusions:
        print("confusions (expected -> predicted):")
        for (exp, pred), n in report.confusions.most_common():
            print(f"  {exp} -> {pred}: {n}")
    if args.verbose:
        for r in report.results:
            mark = "ok " if r.predicted == r.expected else "BAD"
            prob = f"{r.prob:.2f}" if r.prob is not None else "  - "
            print(f"  {mark} {r.id:<12} exp={r.expected:<17} got={r.predicted:<17} p={prob}")
    return 0


# --- calibrate -----------------------------------------------------------------------------


def cmd_calibrate(args: argparse.Namespace) -> int:
    from agent_router.core.catalog import load_catalog
    from agent_router.deciders.embedders import HashingEmbedder, Model2VecEmbedder
    from agent_router.evaluate import (
        DEFAULT_EVAL_SET,
        DEFAULT_GRID,
        QUICK_GRID,
        grid_search,
        load_cases,
        write_calibration,
    )

    catalog = load_catalog()
    cases = load_cases(args.cases or DEFAULT_EVAL_SET, split="cal")
    grid = QUICK_GRID if args.quick else DEFAULT_GRID
    names = EMBEDDERS if args.embedder == "all" else (args.embedder,)
    results = {}
    for name in names:
        if name == "hashing":
            emb: Any = HashingEmbedder()
        else:
            emb = Model2VecEmbedder()
            try:
                emb.load()
            except Exception as exc:  # network, package or file problems
                raise CliError(f"cannot load the model2vec embedder: {exc}") from exc
        res = grid_search(cases, grid, embedder=emb, catalog=catalog)
        results[name] = res
        p = res.params
        print(
            f"{name}: none_floor={p.none_floor} temperature={p.temperature} "
            f"not_for_penalty={p.not_for_penalty} threshold={res.threshold}\n"
            f"  cal accuracy={res.accuracy:.3f} FPR={res.fpr:.3f} FP={res.false_positives} "
            f"| {len(cases)}-case CV accuracy={res.cv_accuracy:.3f} FPR={res.cv_fpr:.3f} "
            f"fold agreement={res.cv_agreement:.2f} | saturated={res.saturated:.2f}"
        )
        if not res.feasible:
            print(f"  WARNING: {name}: not feasible (FP, saturation or CV FPR bound); not loaded")
        if res.edge_params:
            print(f"  WARNING: {name}: on the grid edge: {', '.join(res.edge_params)}")
    path = write_calibration(results, args.out)
    print(f"wrote {path}")
    return 0


# --- demo / run (optional modules) -------------------------------------------------------------


def cmd_demo(args: argparse.Namespace) -> int:
    try:
        import agent_router.demo.server as server
    except ModuleNotFoundError as exc:
        print(
            f"demo server is not available ({exc}); agent_router.demo.server is missing",
            file=sys.stderr,
        )
        return 1
    import uvicorn

    print(f"agent-router demo on http://{args.host}:{args.port}")
    app = server.create_app() if hasattr(server, "create_app") else server.app
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        from agent_router.agent import run_agent
    except ModuleNotFoundError as exc:
        print(
            f"live agent is not available ({exc}); agent_router.agent is missing", file=sys.stderr
        )
        return 1
    import asyncio
    import time

    router = _router(args)
    start = time.perf_counter()

    def on_event(event: Any) -> None:
        stamp = f"[{time.perf_counter() - start:6.2f}s]"
        if isinstance(event, dict):
            kind = event.get("type") or event.get("event") or "event"
            body = {k: v for k, v in event.items() if k not in ("type", "event")}
            print(f"{stamp} {kind:<10} {json.dumps(body, ensure_ascii=False, default=str)[:300]}")
        else:
            print(f"{stamp} {event}")

    workspace = Path(args.workspace).resolve()
    result = asyncio.run(run_agent(args.prompt, router, workspace, on_event))
    print(result)
    return 0


# --- parser ----------------------------------------------------------------------------------


def _json_obj(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--input must be JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("--input must be a JSON object")
    return value


def _add_backend(p: argparse.ArgumentParser) -> None:
    p.add_argument("--backend", default="local", help="decider backend (default: local)")
    p.add_argument("--embedder", choices=EMBEDDERS, help="local backend embedder")
    p.add_argument("--threshold", type=float, help="override the router threshold")
    p.add_argument("--timeout", type=float, help="hosted backend request timeout (s)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-router",
        description="Route agent steps to MIT catalog alternatives with a Jev-spec decider.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("route", help="route one step and show the decision")
    p.add_argument("text", help="prompt text (at tool/skill points: the turn's prompt)")
    p.add_argument("--point", choices=[h.value for h in HookPoint], default="prompt")
    p.add_argument("--tool", help="native tool about to run (Bash, Read, Glob, Skill, ...)")
    p.add_argument("--input", type=_json_obj, help="tool input as a JSON object")
    p.add_argument("--json", action="store_true", help="print JSON")
    _add_backend(p)
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("eval", help="score a backend on the labelled eval set")
    p.add_argument("--split", choices=["test", "cal", "all"], default="test")
    p.add_argument("--cases", help="eval set YAML (default: evals/eval_set.yaml)")
    p.add_argument("--json", action="store_true", help="print JSON")
    p.add_argument("-v", "--verbose", action="store_true", help="list every case")
    _add_backend(p)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("calibrate", help="grid-search local decider params on the cal split")
    p.add_argument("--embedder", choices=[*EMBEDDERS, "all"], default="all")
    p.add_argument("--cases", help="eval set YAML (default: evals/eval_set.yaml)")
    p.add_argument("--out", help="calibration JSON (default: the packaged calibration.json)")
    p.add_argument("--quick", action="store_true", help="small grid (smoke test)")
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser("demo", help="start the visual demo server")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("run", help="run the live agent and print its timeline")
    p.add_argument("prompt")
    p.add_argument("--mode", choices=["advisory", "enforce"], default="advisory")
    p.add_argument("--workspace", default=".")
    _add_backend(p)
    p.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except CliError as exc:
        print(f"agent-router: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
