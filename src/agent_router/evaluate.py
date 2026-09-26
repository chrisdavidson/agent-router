"""Labelled evaluation and calibration of routing decisions.

- ``load_cases`` reads ``evals/eval_set.yaml`` (``split: cal | test``).
- ``run_eval(router_factory, cases)`` routes every case through a real ``Router`` and scores
  the outcome: a SUGGEST / ENFORCE counts as predicting its entry; anything else (NATIVE,
  SKIPPED, below threshold, decider error) counts as ``none``.
- ``grid_search`` / ``calibrate`` tune the local decider's ``none_floor`` x ``temperature`` and
  the router threshold on the ``cal`` split: maximise accuracy subject to FPR <= 0.10, ties
  broken toward the conservative setting (lower FPR, higher threshold, higher none_floor).
- ``write_calibration`` merges results per embedder into ``calibration.json``.

Metrics: ``accuracy`` over all cases; ``fpr`` = expected-none cases routed to an entry /
expected-none cases; ``misroute_rate`` = positives routed to a *different* entry / positives;
``errors`` = decider failures (fail-open NATIVE, scored as ``none`` but counted separately).
"""

from __future__ import annotations

import itertools
import json
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

import yaml

from agent_router.core.audit import AuditLog
from agent_router.core.catalog import Catalog
from agent_router.core.config import RouterConfig
from agent_router.core.router import Router
from agent_router.core.types import NONE_ID, Action, Decision, HookPoint, RouterEvent
from agent_router.deciders.base import Decider
from agent_router.deciders.embedders import Embedder
from agent_router.deciders.local import (
    CALIBRATION_PATH,
    LocalJevDecider,
    LocalParams,
)

DEFAULT_EVAL_SET = Path(__file__).resolve().parents[2] / "evals" / "eval_set.yaml"
SPLITS = ("cal", "test")
MAX_FPR = 0.10
DECIDER_ERROR = "decider error"

DEFAULT_GRID: dict[str, list[float]] = {
    "none_floor": [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7],
    "temperature": [0.05, 0.07, 0.1, 0.15, 0.2, 0.3],
    "threshold": [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8],
    "alpha": [0.6, 0.7, 0.8, 0.9, 1.0],
    "not_for_penalty": [0.5, 1.0, 2.0, 4.0, 8.0],
}
QUICK_GRID: dict[str, list[float]] = {
    "none_floor": [0.3, 0.35, 0.45],
    "temperature": [0.05, 0.07],
    "threshold": [0.4, 0.5, 0.6],
}


# --- cases ----------------------------------------------------------------------


@dataclass(frozen=True)
class EvalCase:
    id: str
    text: str
    point: HookPoint
    expected: str
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    split: str = "test"
    decoy: bool = False

    def event(self, turn_id: int, session_id: str = "eval") -> RouterEvent:
        return RouterEvent(
            point=self.point,
            session_id=session_id,
            turn_id=turn_id,
            text=self.text,
            tool_name=self.tool_name,
            tool_input=self.tool_input,
        )


def load_cases(path: str | Path = DEFAULT_EVAL_SET, split: str | None = None) -> list[EvalCase]:
    """Cases from ``path``; ``split`` = ``cal`` | ``test`` | ``all`` / None (every case)."""
    if split not in (None, "all", *SPLITS):
        raise ValueError(f"split must be one of cal, test, all; got {split!r}")
    data = yaml.safe_load(Path(path).read_text())
    out = []
    for raw in data["cases"]:
        case = EvalCase(
            id=str(raw["id"]),
            text=str(raw.get("text") or ""),
            point=HookPoint(raw["point"]),
            expected=str(raw["expected"]),
            tool_name=raw.get("tool_name"),
            tool_input=raw.get("tool_input"),
            split=str(raw.get("split", "test")),
            decoy=bool(raw.get("decoy", False)),
        )
        if case.split not in SPLITS:
            raise ValueError(f"case {case.id}: split must be cal or test")
        if split in (None, "all") or case.split == split:
            out.append(case)
    return out


# --- scoring ----------------------------------------------------------------------


def predicted_label(decision: Decision) -> str:
    """The entry the agent would be nudged toward, or ``none``."""
    if decision.action in (Action.SUGGEST, Action.ENFORCE) and decision.entry_id:
        return decision.entry_id
    return NONE_ID


@dataclass(frozen=True)
class CaseResult:
    id: str
    expected: str
    predicted: str
    action: str
    reason: str
    prob: float | None = None
    decoy: bool = False
    error: bool = False
    latency_ms: float | None = None


@dataclass
class EvalReport:
    n: int
    accuracy: float
    fpr: float
    misroute_rate: float
    errors: int
    per_entry: dict[str, dict[str, float]]
    confusions: Counter[tuple[str, str]]
    results: list[CaseResult] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"n={self.n} accuracy={self.accuracy:.3f} FPR={self.fpr:.3f} "
            f"misroute={self.misroute_rate:.3f} errors={self.errors}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "accuracy": self.accuracy,
            "fpr": self.fpr,
            "misroute_rate": self.misroute_rate,
            "errors": self.errors,
            "per_entry": self.per_entry,
            "confusions": [
                {"expected": e, "predicted": p, "count": c}
                for (e, p), c in sorted(self.confusions.items())
            ],
            "cases": [asdict(r) for r in self.results],
        }


def score(results: Sequence[CaseResult]) -> EvalReport:
    n = len(results)
    correct = sum(r.predicted == r.expected for r in results)
    negatives = [r for r in results if r.expected == NONE_ID]
    positives = [r for r in results if r.expected != NONE_ID]
    fp = sum(r.predicted != NONE_ID for r in negatives)
    misroutes = sum(r.predicted not in (NONE_ID, r.expected) for r in positives)
    confusions: Counter[tuple[str, str]] = Counter(
        (r.expected, r.predicted) for r in results if r.predicted != r.expected
    )
    labels = sorted({r.expected for r in results} | {r.predicted for r in results})
    per_entry: dict[str, dict[str, float]] = {}
    for label in labels:
        tp = sum(r.expected == label and r.predicted == label for r in results)
        support = sum(r.expected == label for r in results)
        predicted = sum(r.predicted == label for r in results)
        per_entry[label] = {
            "support": support,
            "predicted": predicted,
            "precision": tp / predicted if predicted else 0.0,
            "recall": tp / support if support else 0.0,
        }
    return EvalReport(
        n=n,
        accuracy=correct / n if n else 0.0,
        fpr=fp / len(negatives) if negatives else 0.0,
        misroute_rate=misroutes / len(positives) if positives else 0.0,
        errors=sum(r.error for r in results),
        per_entry=per_entry,
        confusions=confusions,
        results=list(results),
    )


def _case_result(case: EvalCase, decision: Decision, predicted: str | None = None) -> CaseResult:
    res = decision.result
    prob = None
    if res is not None and res.choice in res.probabilities:
        prob = float(res.probabilities[res.choice])
    return CaseResult(
        id=case.id,
        expected=case.expected,
        predicted=predicted if predicted is not None else predicted_label(decision),
        action=str(decision.action),
        reason=decision.reason,
        prob=prob,
        decoy=case.decoy,
        error=decision.reason.startswith(DECIDER_ERROR),
        latency_ms=res.latency_ms if res is not None else None,
    )


def run_eval(router_factory: Callable[[], Router], cases: Iterable[EvalCase]) -> EvalReport:
    """Route every case through one router (a unique turn per case) and score it."""
    router = router_factory()
    results = [
        _case_result(case, router.route(case.event(turn_id=i)))
        for i, case in enumerate(cases, start=1)
    ]
    return score(results)


# --- routers ------------------------------------------------------------------------


def make_router(
    backend: str | Decider,
    catalog: Catalog,
    *,
    embedder: Embedder | None = None,
    threshold: float | None = None,
    timeout: float | None = None,
    mode: str = "advisory",
) -> Router:
    """A router with an in-memory audit (advisory by default) for evaluation and the CLI.

    ``threshold`` defaults to the decider's calibrated ``recommended_threshold`` when it has
    one, else ``RouterConfig``'s default. ``embedder`` applies to the local backend only.
    """
    if isinstance(backend, str):
        if backend == "local" and embedder is not None:
            decider: Decider = LocalJevDecider(
                embedder=embedder, native_examples=catalog.native_examples
            )
        else:
            from agent_router.deciders.registry import make_decider

            decider = make_decider(backend, catalog)
    else:
        decider = backend
    if timeout is not None and hasattr(decider, "timeout"):
        decider.timeout = timeout  # type: ignore[attr-defined]
    if threshold is None:
        threshold = getattr(decider, "recommended_threshold", None)
    if threshold is None:
        threshold = RouterConfig().threshold
    return Router(
        catalog,
        decider,
        RouterConfig(mode=mode, threshold=float(threshold)),  # type: ignore[arg-type]
        AuditLog(None),
    )


# --- calibration --------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationResult:
    params: LocalParams
    threshold: float
    accuracy: float
    fpr: float
    misroute_rate: float
    feasible: bool  # a grid point met FPR <= max_fpr
    n_cases: int

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self.params),
            "threshold": self.threshold,
            "cal_accuracy": round(self.accuracy, 4),
            "cal_fpr": round(self.fpr, 4),
            "cal_misroute_rate": round(self.misroute_rate, 4),
            "feasible": self.feasible,
            "n_cases": self.n_cases,
        }


def grid_search(
    cases: Sequence[EvalCase],
    grid: dict[str, Sequence[float]] | None = None,
    *,
    embedder: Embedder,
    catalog: Catalog,
    base: LocalParams | None = None,
    max_fpr: float = MAX_FPR,
) -> CalibrationResult:
    """Grid-search ``LocalParams`` x router threshold on ``cases``.

    ``grid`` maps ``threshold`` and any ``LocalParams`` field (at least ``none_floor`` and
    ``temperature``; optionally ``alpha``, ``not_for_penalty``) to candidate values. Each
    params combination is routed once at threshold 0; every threshold is then applied to
    p(choice) exactly as the router's threshold rule does.
    """
    grid = grid if grid is not None else DEFAULT_GRID
    base = base if base is not None else LocalParams()
    keys = [f.name for f in fields(LocalParams) if f.name in grid]
    decider = LocalJevDecider(
        embedder=embedder, params=base, native_examples=catalog.native_examples
    )
    best: tuple[tuple, CalibrationResult] | None = None
    for combo in itertools.product(*(grid[k] for k in keys)):
        decider.params = replace(base, **{k: float(v) for k, v in zip(keys, combo, strict=True)})
        floor, temp = decider.params.none_floor, decider.params.temperature
        router = make_router(decider, catalog, threshold=0.0)
        routed = [(c, router.route(c.event(turn_id=i))) for i, c in enumerate(cases, start=1)]
        for thr in grid["threshold"]:
            results = []
            for case, dec in routed:
                label = predicted_label(dec)
                if label != NONE_ID and _prob(dec) < thr:
                    label = NONE_ID
                results.append(_case_result(case, dec, predicted=label))
            rep = score(results)
            feasible = rep.fpr <= max_fpr
            # feasible points by accuracy; if none is feasible, the minimum-FPR point.
            # Ties go to the conservative setting: higher threshold, higher none_floor.
            head = (1, rep.accuracy, -rep.fpr) if feasible else (0, -rep.fpr, rep.accuracy)
            key = (*head, float(thr), floor, -temp, decider.params.not_for_penalty)
            if best is None or key > best[0]:
                best = (
                    key,
                    CalibrationResult(
                        params=decider.params,
                        threshold=float(thr),
                        accuracy=rep.accuracy,
                        fpr=rep.fpr,
                        misroute_rate=rep.misroute_rate,
                        feasible=feasible,
                        n_cases=rep.n,
                    ),
                )
    if best is None:
        raise ValueError("empty calibration grid")
    return best[1]


def _prob(decision: Decision) -> float:
    res = decision.result
    if res is None or decision.entry_id is None:
        return 0.0
    return float(res.probabilities.get(decision.entry_id, 0.0))


def calibrate(
    cases: Sequence[EvalCase],
    grid: dict[str, Sequence[float]] | None = None,
    *,
    embedder: Embedder,
    catalog: Catalog,
) -> tuple[LocalParams, float]:
    res = grid_search(cases, grid, embedder=embedder, catalog=catalog)
    return res.params, res.threshold


def write_calibration(
    results: dict[str, CalibrationResult], path: str | Path = CALIBRATION_PATH
) -> Path:
    """Merge ``{embedder_key: result}`` into the calibration JSON at ``path``."""
    path = Path(path)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text())
        except ValueError:
            data = {}
    for key, res in results.items():
        data[key] = res.to_dict()
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path
