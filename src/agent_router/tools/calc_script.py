"""The exact calculator's script form: a small, exact Python subset (agent-router, MIT).

``run`` walks a script's syntax tree, never ``eval``/``exec``. It keeps the calculator's rules
(numbers are exact ``Fraction``s; ``log``, ``sqrt`` of a non-square, ``pi``, ... are approximate
to 50 digits and shown as ``≈``) and adds what the first-principles agents' arithmetic scripts
used, measured over their recorded runs: ``for`` over ``range``, lists, tuples and dicts,
``while``, ``if``/``elif``/``else``, comparisons and ``and``/``or``, lists, tuples, dicts and
their indexing and slicing, comprehensions, tuple unpacking, non-recursive ``def`` and ``lambda``,
f-strings with format specs (``{x:,.2f}``, ``{r:.1%}``), and the builtins in ``_BUILTINS``.

What it never does: import anything but ``math`` (and ``Fraction`` from ``fractions``), read or
write files, touch the network, reach an attribute other than ``math.<name>`` and a few container
methods (``items``, ``keys``, ``values``, ``get``, ``append``, ``extend``, ``join``), or recurse.
A step budget stops a loop that runs too long. Every failure is a ``ValueError`` naming the line.

Output: one line per ``print`` and per top-level bare expression. A number argument is shown as
``<source> = <value>`` (``x * 3 = 6``, ``r = 7/2 (≈ 3.5)``, ``L = ≈ 0.69``); a string, f-string
or label is printed as Python would; the arguments of one ``print`` are joined with ``", "``
unless ``sep`` is given.
"""

from __future__ import annotations

import ast
import contextlib
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from typing import Any

from agent_router.tools import calc

MAX_SCRIPT_CHARS = calc.MAX_SCRIPT_CHARS
MAX_STATEMENTS = calc.MAX_STATEMENTS  # top-level statements
MAX_NAMES = calc.MAX_NAMES  # names at the top level
MAX_STEPS = 200_000  # statements run, loop turns, comprehension items and calls, all together
MAX_LENGTH = 100_000  # items in one list, tuple, dict or range; characters in one string
MAX_OUTPUT_CHARS = 200_000
MAX_DEPTH = calc.MAX_DEPTH
MAX_SECONDS = 10.0  # wall-clock budget for one script (the router's fit check sets its own)
# Beyond this many bits an approximate number is rounded to _TRIM_DIGITS significant digits:
# it is already only good to 50 digits, and a loop would otherwise grow it without bound.
_TRIM_BITS = 1_000
_TRIM_DIGITS = 60
_LONG_FRACTION_BITS = 133  # numerator and denominator together past ~40 digits

_CONSTRUCTS = {
    "AsyncFor": "async for loop",
    "AsyncFunctionDef": "async function definition",
    "AsyncWith": "with statement",
    "ClassDef": "class definition",
    "With": "with statement",
    "Try": "try statement",
    "TryStar": "try statement",
    "Delete": "del statement",
    "Global": "global statement",
    "Nonlocal": "nonlocal statement",
    "Assert": "assert statement",
    "Raise": "raise statement",
    "AnnAssign": "annotated assignment",
    "Match": "match statement",
}
_EXPR_CONSTRUCTS = {
    "SetComp": "set comprehension",
    "Set": "set",
    "NamedExpr": "walrus assignment",
    "Starred": "star unpacking",
    "Await": "await",
    "Yield": "yield",
    "YieldFrom": "yield",
}
_METHODS = frozenset(
    {"items", "keys", "values", "get", "append", "extend", "join", "count", "index", "copy"}
)


class _Infinity:
    """``float('inf')`` / ``float('-inf')``: compares beyond every number; no arithmetic. Agents
    use it as the open top of a tax bracket (``min(income, top)``)."""

    def __init__(self, sign: int) -> None:
        self.sign = sign

    def _key(self, other: Any) -> int:
        if isinstance(other, _Infinity):
            return self.sign - other.sign
        if isinstance(other, Fraction | int):
            return self.sign
        return NotImplemented  # type: ignore[return-value]

    def __lt__(self, other: Any) -> bool:
        k = self._key(other)
        return k if k is NotImplemented else k < 0

    def __le__(self, other: Any) -> bool:
        k = self._key(other)
        return k if k is NotImplemented else k <= 0

    def __gt__(self, other: Any) -> bool:
        k = self._key(other)
        return k if k is NotImplemented else k > 0

    def __ge__(self, other: Any) -> bool:
        k = self._key(other)
        return k if k is NotImplemented else k >= 0

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, _Infinity) and other.sign == self.sign

    def __hash__(self) -> int:
        return hash(("inf", self.sign))

    def __repr__(self) -> str:
        return "inf" if self.sign > 0 else "-inf"


class _Return(Exception):
    def __init__(self, value: Any, inexact: bool) -> None:
        self.value, self.inexact = value, inexact


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class _State(calc._Inexact):
    """Whether the value being computed is approximate (any part of it was)."""

    def __init__(self, flag: bool = False) -> None:
        self.flag = flag


@dataclass
class _Scope:
    vars: dict[str, tuple[Any, bool]] = field(default_factory=dict)
    parent: _Scope | None = None

    def find(self, name: str) -> tuple[Any, bool] | None:
        scope: _Scope | None = self
        while scope is not None:
            if name in scope.vars:
                return scope.vars[name]
            scope = scope.parent
        return None


@dataclass(eq=False)
class _Function:
    name: str
    params: list[str]
    defaults: dict[str, tuple[Any, bool]]
    body: list[ast.stmt] | ast.expr  # a lambda's body is one expression
    scope: _Scope
    varargs: str | None = None  # *args
    varkw: str | None = None  # **kwargs


@dataclass(eq=False)
class _Builtin:
    name: str
    fn: Callable[..., Any]


def _where(node: ast.AST, msg: str) -> ValueError:
    return ValueError(f"line {getattr(node, 'lineno', '?')}: {msg}")


def _located(node: ast.AST, exc: ValueError) -> ValueError:
    msg = str(exc)
    return exc if msg.startswith("line ") else _where(node, msg)


def _is_num(v: Any) -> bool:
    return isinstance(v, Fraction | bool)


def _num(v: Any, what: str = "a number") -> Fraction:
    if isinstance(v, bool):
        return Fraction(int(v))
    if isinstance(v, Fraction):
        return v
    raise ValueError(f"expected {what}, got {_type(v)}")


def _int(v: Any, what: str) -> int:
    x = _num(v, what)
    if x.denominator != 1:
        raise ValueError(f"{what} must be a whole number")
    return x.numerator


def _type(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, Fraction):
        return "number"
    if v is None:
        return "None"
    if isinstance(v, _Function | _Builtin):
        return "function"
    return type(v).__name__


def _trim(x: Fraction) -> Fraction:
    if calc._bits(x) <= _TRIM_BITS:
        return x
    with localcontext() as ctx:
        ctx.prec = _TRIM_DIGITS
        return Fraction(Decimal(x.numerator) / Decimal(x.denominator))


def _sized(v: Any) -> Any:
    if isinstance(v, list | tuple | dict | str | range) and len(v) > MAX_LENGTH:
        raise ValueError(f"too many items (limit {MAX_LENGTH})")
    return v


# --- showing values ---------------------------------------------------------------------------


def _plain(x: Fraction) -> str:
    """A number as ``str()`` / an f-string field without a spec would show it."""
    calc._check_digits(x)
    return str(x.numerator) if x.denominator == 1 else calc._decimal(x)


def _text(v: Any) -> str:
    """``str(v)``: what ``print`` shows for a value inside a container or an f-string."""
    if isinstance(v, bool) or v is None or isinstance(v, _Infinity):
        return str(v)
    if isinstance(v, Fraction):
        return _plain(v)
    if isinstance(v, str):
        return v
    return _repr(v)


def _repr(v: Any) -> str:
    if isinstance(v, str):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(_repr(x) for x in v) + "]"
    if isinstance(v, tuple):
        inner = ", ".join(_repr(x) for x in v)
        return f"({inner},)" if len(v) == 1 else f"({inner})"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_repr(k)}: {_repr(x)}" for k, x in v.items()) + "}"
    if isinstance(v, range):
        return f"range({v.start}, {v.stop}" + (f", {v.step})" if v.step != 1 else ")")
    if isinstance(v, _Function | _Builtin):
        return f"<function {v.name}>"
    if isinstance(v, _Infinity):
        return repr(v)
    return _text(v)


def _shown(v: Any, inexact: bool) -> str:
    """A value as the right side of ``<source> = <value>``. An exact fraction too long to read
    (a loop compounding a rate builds hundreds of digits) is shown as its decimal, marked ≈."""
    if isinstance(v, Fraction) and not isinstance(v, bool):
        calc._check_digits(v)
        if v.denominator != 1 and calc._bits(v) > _LONG_FRACTION_BITS:
            inexact = True
        return calc.format_result(v, inexact)
    if isinstance(v, list | tuple):
        parts = [_shown(x, inexact) for x in v]
        if isinstance(v, tuple):
            return "(" + ", ".join(parts) + ("," if len(v) == 1 else "") + ")"
        return "[" + ", ".join(parts) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_repr(k)}: {_shown(x, inexact)}" for k, x in v.items()) + "}"
    return _repr(v)


def _numbers_in(v: Any) -> list[float]:
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return []
    if isinstance(v, Fraction):
        return [float(v)]
    if isinstance(v, list | tuple):
        return [n for x in v for n in _numbers_in(x)]
    if isinstance(v, dict):
        return [n for x in v.values() for n in _numbers_in(x)]
    return []


_FORMATTED_NUMBER = re.compile(r"[-+]?(?:\d[\d,_]*\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_SPEC_TYPE = re.compile(r"([bcdeEfFgGnosxX%])$")


def _format_number(x: Fraction, spec: str) -> str:
    m = _SPEC_TYPE.search(spec)
    kind = m.group(1) if m else ""
    if kind in ("b", "c", "d", "o", "x", "X", "n"):
        if x.denominator != 1:
            raise ValueError(f"format code {kind!r} needs a whole number")
        return format(x.numerator, spec)
    if kind == "s":
        raise ValueError("format code 's' is for text, not a number")
    if not kind and "." not in spec:  # width, alignment or grouping only
        return format(Decimal(_plain(x)), spec)
    calc._check_digits(x)
    with localcontext() as ctx:
        ctx.prec = max(len(str(abs(x.numerator) // x.denominator)), 1) + 60
        ctx.rounding = ROUND_HALF_EVEN
        return format(Decimal(x.numerator) / Decimal(x.denominator), spec)


# --- the interpreter --------------------------------------------------------------------------


class _Script:
    def __init__(self, source: str, max_seconds: float = MAX_SECONDS) -> None:
        self.source = source
        self.deadline = time.monotonic() + max_seconds
        self.globals = _Scope()
        self.out: list[str] = []
        self.out_chars = 0
        self.values: list[float] = []
        self.steps = 0
        self.active: set[int] = set()  # functions being called: no recursion
        self.print_value = _Builtin("print", self.print_values)
        table = _builtin_table(self)
        self.fraction = _Builtin("Fraction", table.pop("Fraction"))
        self.builtins: dict[str, Any] = {name: _Builtin(name, fn) for name, fn in table.items()}
        self.math_modules = {"math"}  # names the math module is known by (import math as m)

    # bookkeeping

    def step(self) -> None:
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise ValueError(f"step budget exceeded (limit {MAX_STEPS}): a loop runs too long")
        if self.steps % 256 == 0 and time.monotonic() > self.deadline:
            raise ValueError("time budget exceeded: the script runs too long")

    def emit(self, text: str) -> None:
        self.out_chars += len(text) + 1
        if self.out_chars > MAX_OUTPUT_CHARS:
            raise ValueError(f"too much output (limit {MAX_OUTPUT_CHARS} characters)")
        self.out.append(text)

    # names

    def lookup(self, name: str, scope: _Scope, state: _State) -> Any:
        found = scope.find(name)
        if found is not None:
            value, inexact = found
            state.flag = state.flag or inexact
            return value
        if name in calc._CONSTANTS:
            value, inexact = calc._CONSTANTS[name]
            state.flag = state.flag or inexact
            return value
        if name in self.builtins:
            return self.builtins[name]
        if name == "print":  # print as a value (p = print): its arguments have no source text
            return self.print_value
        if name == "__name__":
            return "__main__"
        raise ValueError(f"name {name!r} is not defined")

    def bind(self, target: ast.expr, value: Any, inexact: bool, scope: _Scope) -> None:
        if isinstance(target, ast.Name):
            if (
                scope is self.globals
                and target.id not in scope.vars
                and len(scope.vars) >= MAX_NAMES
            ):
                raise ValueError(f"too many names (limit {MAX_NAMES})")
            scope.vars[target.id] = (value, inexact)
            return
        if isinstance(target, ast.Tuple | ast.List):
            items = self.items(value)
            if len(items) != len(target.elts):
                raise ValueError(f"cannot unpack {len(items)} values into {len(target.elts)} names")
            for t, v in zip(target.elts, items, strict=True):
                self.bind(t, v, inexact, scope)
            return
        if isinstance(target, ast.Subscript):
            state = _State(inexact)
            container = self.eval(target.value, scope, state)
            key = self.eval(target.slice, scope, state)
            self.store_item(container, key, value)
            return
        if isinstance(target, ast.Starred):
            raise ValueError("star unpacking is not supported")
        raise ValueError("only names, tuples of names and [index] can be assigned to")

    def store_item(self, container: Any, key: Any, value: Any) -> None:
        if isinstance(container, dict):
            container[self.key(key)] = value
            _sized(container)
        elif isinstance(container, list):
            container[self.index(container, key)] = value
        else:
            raise ValueError(f"cannot assign into a {_type(container)}")

    def key(self, k: Any) -> Any:
        if isinstance(k, Fraction | bool | str | tuple) or k is None:
            return k
        raise ValueError(f"a {_type(k)} cannot be a dict key")

    def index(self, seq: Any, i: Any) -> int:
        n = _int(i, "an index")
        if not -len(seq) <= n < len(seq):
            raise ValueError("index out of range")
        return n

    def items(self, v: Any) -> list[Any]:
        """The items a ``for`` loop, unpacking or a builtin takes from ``v``."""
        if isinstance(v, list | tuple):
            return list(v)
        if isinstance(v, dict):
            return list(v)
        if isinstance(v, range):
            _sized(v)
            return [Fraction(i) for i in v]
        if isinstance(v, str):
            return list(_sized(v))
        raise ValueError(f"cannot iterate over a {_type(v)}")

    # statements

    def run_block(self, body: list[ast.stmt], scope: _Scope, top: bool = False) -> None:
        for stmt in body:
            self.step()
            try:
                self.run_stmt(stmt, scope, top)
            except ValueError as exc:
                raise _located(stmt, exc) from exc
            except (ArithmeticError, RecursionError, MemoryError) as exc:
                raise _where(stmt, f"cannot evaluate: {type(exc).__name__}") from exc

    def run_stmt(self, stmt: ast.stmt, scope: _Scope, top: bool) -> None:
        if isinstance(stmt, ast.Import | ast.ImportFrom):
            self.check_import(stmt, scope)
        elif isinstance(stmt, ast.Assign):
            state = _State()
            value = self.eval(stmt.value, scope, state)
            for target in stmt.targets:
                self.bind(target, value, state.flag, scope)
        elif isinstance(stmt, ast.AugAssign):
            self.aug_assign(stmt, scope)
        elif isinstance(stmt, ast.Expr):
            self.expression_statement(stmt.value, scope, top)
        elif isinstance(stmt, ast.If):
            state = _State()
            branch = stmt.body if self.eval(stmt.test, scope, state) else stmt.orelse
            self.run_block(branch, scope)
        elif isinstance(stmt, ast.For):
            self.for_loop(stmt, scope)
        elif isinstance(stmt, ast.While):
            self.while_loop(stmt, scope)
        elif isinstance(stmt, ast.FunctionDef):
            self.define(stmt, scope)
        elif isinstance(stmt, ast.Return):
            if scope is self.globals:
                raise ValueError("return outside a function")
            state = _State()
            value = None if stmt.value is None else self.eval(stmt.value, scope, state)
            raise _Return(value, state.flag)
        elif isinstance(stmt, ast.Break):
            raise _Break()
        elif isinstance(stmt, ast.Continue):
            raise _Continue()
        elif isinstance(stmt, ast.Pass):
            pass
        else:
            kind = type(stmt).__name__
            raise ValueError(f"{_CONSTRUCTS.get(kind, kind)} is not supported")

    def check_import(self, stmt: ast.Import | ast.ImportFrom, scope: _Scope) -> None:
        if isinstance(stmt, ast.Import):
            for a in stmt.names:
                if a.name != "math":
                    raise ValueError("only 'import math' is supported")
                self.math_modules.add(a.asname or "math")
            return
        if stmt.module == "fractions" and not stmt.level:
            if any(a.name != "Fraction" for a in stmt.names):
                raise ValueError("only 'from fractions import Fraction' is supported")
            scope.vars[stmt.names[0].asname or "Fraction"] = (self.fraction, False)
            return
        if stmt.module != "math" or stmt.level:
            raise ValueError("only 'from math import ...' is supported")
        for a in stmt.names:
            if a.name not in _MATH_NAMES:
                raise ValueError(f"math.{a.name} is not supported")
            if a.asname:
                scope.vars[a.asname] = (self.math_value(a.name, _State()), a.name in _INEXACT)

    def aug_assign(self, stmt: ast.AugAssign, scope: _Scope) -> None:
        state = _State()
        target = stmt.target
        if isinstance(target, ast.Name):
            found = scope.find(target.id)
            if found is None:
                raise ValueError(f"name {target.id!r} is not defined")
            old, old_flag = found
            state.flag = old_flag
            value = self.binop(stmt.op, old, self.eval(stmt.value, scope, state), state)
            scope.vars[target.id] = (value, state.flag)  # a function's own copy, as in Python
            return
        if isinstance(target, ast.Subscript):
            container = self.eval(target.value, scope, state)
            key = self.eval(target.slice, scope, state)
            old = self.subscript(container, key)
            value = self.binop(stmt.op, old, self.eval(stmt.value, scope, state), state)
            self.store_item(container, key, value)
            return
        raise ValueError("only 'name += expression' and 'x[i] += expression' are supported")

    def expression_statement(self, node: ast.expr, scope: _Scope, top: bool) -> None:
        """A top-level bare expression is shown, as in a calculator; a call to the script's own
        function is not (its prints are its output, and python shows nothing for it)."""
        state = _State()
        own_call = isinstance(node, ast.Call) and isinstance(self.callee(node, scope), _Function)
        value = self.eval(node, scope, state)
        if not top or own_call or value is None or isinstance(node, ast.Call) and _is_print(node):
            return
        if isinstance(value, _Function | _Builtin):
            return
        self.emit(f"{self.src(node)} = {_shown(value, state.flag)}")
        self.values.extend(_numbers_in(value))

    def callee(self, node: ast.Call, scope: _Scope) -> Any:
        if isinstance(node.func, ast.Name):
            found = scope.find(node.func.id)
            return None if found is None else found[0]
        return None

    def for_loop(self, stmt: ast.For, scope: _Scope) -> None:
        state = _State()
        seq = self.items(self.eval(stmt.iter, scope, state))
        broke = False
        for item in seq:
            self.step()
            self.bind(stmt.target, item, state.flag, scope)
            try:
                self.run_block(stmt.body, scope)
            except _Break:
                broke = True
                break
            except _Continue:
                continue
        if not broke:
            self.run_block(stmt.orelse, scope)

    def while_loop(self, stmt: ast.While, scope: _Scope) -> None:
        broke = False
        while self.eval(stmt.test, scope, _State()):
            self.step()
            try:
                self.run_block(stmt.body, scope)
            except _Break:
                broke = True
                break
            except _Continue:
                continue
        if not broke:
            self.run_block(stmt.orelse, scope)

    def define(self, stmt: ast.FunctionDef, scope: _Scope) -> None:
        if stmt.decorator_list:
            raise ValueError("decorators are not supported")
        params, defaults = self.parameters(stmt.args, scope)
        fn = _Function(stmt.name, params, defaults, stmt.body, scope, *_star_names(stmt.args))
        self.bind(ast.Name(id=stmt.name), fn, False, scope)

    def parameters(
        self, args: ast.arguments, scope: _Scope
    ) -> tuple[list[str], dict[str, tuple[Any, bool]]]:
        if args.kwonlyargs or args.posonlyargs:
            raise ValueError("keyword-only and positional-only parameters are not supported")
        params = [a.arg for a in args.args]
        defaults: dict[str, tuple[Any, bool]] = {}
        for name, node in zip(
            params[len(params) - len(args.defaults) :], args.defaults, strict=True
        ):
            state = _State()
            defaults[name] = (self.eval(node, scope, state), state.flag)
        return params, defaults

    # expressions

    def src(self, node: ast.AST) -> str:
        return (ast.get_source_segment(self.source, node) or ast.unparse(node)).strip()

    def eval(self, node: ast.AST, scope: _Scope, state: _State, depth: int = 0) -> Any:
        if depth > MAX_DEPTH:
            raise ValueError(f"expression nested too deeply (limit {MAX_DEPTH})")
        d = depth + 1
        if isinstance(node, ast.Constant):
            v = node.value
            if v is None or isinstance(v, bool):
                return v
            if isinstance(v, int):
                return Fraction(v)
            if isinstance(v, float):
                return Fraction(repr(v))
            if isinstance(v, str):
                return _sized(v)
            raise ValueError(f"unsupported literal {v!r}")
        if isinstance(node, ast.Name):
            return self.lookup(node.id, scope, state)
        if isinstance(node, ast.BinOp):
            # a long a+b+c+... chain is walked iteratively, as calc._eval does
            chain = [node]
            while isinstance(chain[-1].left, ast.BinOp):
                chain.append(chain[-1].left)
            acc = self.eval(chain[-1].left, scope, state, d)
            for link in reversed(chain):
                acc = self.binop(link.op, acc, self.eval(link.right, scope, state, d), state)
            return acc
        if isinstance(node, ast.UnaryOp):
            v = self.eval(node.operand, scope, state, d)
            if isinstance(node.op, ast.Not):
                return not v
            if isinstance(node.op, ast.USub):
                return _Infinity(-v.sign) if isinstance(v, _Infinity) else -_num(v)
            if isinstance(node.op, ast.UAdd):
                return _num(v)
            raise ValueError("operator ~ is not supported")
        if isinstance(node, ast.BoolOp):
            result: Any = None
            for value_node in node.values:
                result = self.eval(value_node, scope, state, d)
                if isinstance(node.op, ast.And) and not result:
                    return result
                if isinstance(node.op, ast.Or) and result:
                    return result
            return result
        if isinstance(node, ast.Compare):
            left = self.eval(node.left, scope, state, d)
            for op, right_node in zip(node.ops, node.comparators, strict=True):
                right = self.eval(right_node, scope, state, d)
                if not _compare(op, left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            test = self.eval(node.test, scope, state, d)
            return self.eval(node.body if test else node.orelse, scope, state, d)
        if isinstance(node, ast.List):
            return _sized([self.eval(e, scope, state, d) for e in self.no_star(node.elts)])
        if isinstance(node, ast.Tuple):
            return _sized(tuple(self.eval(e, scope, state, d) for e in self.no_star(node.elts)))
        if isinstance(node, ast.Dict):
            out: dict[Any, Any] = {}
            for k, v in zip(node.keys, node.values, strict=True):
                if k is None:  # {**other, ...}
                    merged = self.eval(v, scope, state, d)
                    if not isinstance(merged, dict):
                        raise ValueError(f"** needs a dict, got {_type(merged)}")
                    out.update(merged)
                    continue
                out[self.key(self.eval(k, scope, state, d))] = self.eval(v, scope, state, d)
            return _sized(out)
        if isinstance(node, ast.Subscript):
            container = self.eval(node.value, scope, state, d)
            if isinstance(node.slice, ast.Slice):
                return self.slice(container, node.slice, scope, state, d)
            return self.subscript(container, self.eval(node.slice, scope, state, d))
        if isinstance(node, ast.ListComp | ast.GeneratorExp):
            items: list[Any] = []
            self.comprehension(
                node.generators,
                scope,
                state,
                d,
                lambda s: items.append(self.eval(node.elt, s, state, d)),
            )
            return _sized(items)
        if isinstance(node, ast.DictComp):
            result_dict: dict[Any, Any] = {}

            def put(s: _Scope) -> None:
                k = self.key(self.eval(node.key, s, state, d))
                result_dict[k] = self.eval(node.value, s, state, d)

            self.comprehension(node.generators, scope, state, d, put)
            return _sized(result_dict)
        if isinstance(node, ast.Lambda):
            params, defaults = self.parameters(node.args, scope)
            return _Function(
                "<lambda>", params, defaults, node.body, scope, *_star_names(node.args)
            )
        if isinstance(node, ast.JoinedStr):
            return self.fstring(node, scope, state, d)
        if isinstance(node, ast.Call):
            return self.call(node, scope, state, d)
        if isinstance(node, ast.Attribute):
            name = self.math_attr(node, scope)
            if name is not None:
                return self.math_value(name, state)
            if node.attr in _METHODS:  # a bound method as a value: max(t, key=t.get)
                obj = self.eval(node.value, scope, state, d)
                return _Builtin(
                    node.attr, lambda st, *a, _o=obj, _n=node.attr: _method(_o, _n, list(a))
                )
            raise ValueError("attribute access is not supported (only math.<name>)")
        kind = type(node).__name__
        raise ValueError(f"{_EXPR_CONSTRUCTS.get(kind, kind)} is not supported")

    def math_attr(self, node: ast.AST, scope: _Scope) -> str | None:
        """``log`` for ``math.log`` (or ``m.log`` after ``import math as m``), else None."""
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in self.math_modules
            and scope.find(node.value.id) is None
        ):
            return node.attr
        return None

    def math_value(self, name: str, state: _State) -> Any:
        if name in calc._CONSTANTS:
            value, inexact = calc._CONSTANTS[name]
            state.flag = state.flag or inexact
            return value
        if name in ("inf",):
            return _Infinity(1)
        if name in _MATH_NAMES:
            return self.builtins[name]
        raise ValueError(f"math.{name} is not supported")

    def no_star(self, elts: list[ast.expr]) -> list[ast.expr]:
        if any(isinstance(e, ast.Starred) for e in elts):
            raise ValueError("star unpacking is not supported")
        return elts

    def comprehension(
        self,
        generators: list[ast.comprehension],
        scope: _Scope,
        state: _State,
        depth: int,
        emit: Callable[[_Scope], None],
    ) -> None:
        inner = _Scope(parent=scope)

        def level(i: int) -> None:
            if i == len(generators):
                self.step()
                emit(inner)
                return
            gen = generators[i]
            if gen.is_async:
                raise ValueError("async comprehensions are not supported")
            for item in self.items(self.eval(gen.iter, inner if i else scope, state, depth)):
                self.bind(gen.target, item, state.flag, inner)
                if all(self.eval(cond, inner, state, depth) for cond in gen.ifs):
                    level(i + 1)

        level(0)

    def subscript(self, container: Any, key: Any) -> Any:
        if isinstance(container, dict):
            try:
                return container[self.key(key)]
            except KeyError:
                raise ValueError(f"key {_repr(key)} is not in the dict") from None
        if isinstance(container, list | tuple | str):
            return container[self.index(container, key)]
        if isinstance(container, range):
            return Fraction(container[self.index(container, key)])
        raise ValueError(f"a {_type(container)} cannot be indexed")

    def slice(self, container: Any, sl: ast.Slice, scope: _Scope, state: _State, d: int) -> Any:
        if not isinstance(container, list | tuple | str):
            raise ValueError(f"a {_type(container)} cannot be sliced")
        bounds = [
            None if part is None else _int(self.eval(part, scope, state, d), "a slice bound")
            for part in (sl.lower, sl.upper, sl.step)
        ]
        if bounds[2] == 0:
            raise ValueError("slice step cannot be zero")
        return container[slice(*bounds)]

    def fstring(self, node: ast.JoinedStr, scope: _Scope, state: _State, d: int) -> str:
        parts: list[str] = []
        for part in node.values:
            if isinstance(part, ast.Constant):
                parts.append(str(part.value))
                continue
            assert isinstance(part, ast.FormattedValue)
            value = self.eval(part.value, scope, state, d)
            spec = (
                "" if part.format_spec is None else self.fstring(part.format_spec, scope, state, d)
            )
            if part.conversion in (ord("r"), ord("a")):
                value = _repr(value)
            elif part.conversion == ord("s"):
                value = _text(value)
            parts.append(self.format_value(value, spec))
        return _sized("".join(parts))

    def format_value(self, value: Any, spec: str) -> str:
        """``format(value, spec)`` for an f-string field or the ``format`` builtin; a number is
        formatted exactly and the number shown is kept for the agreement check."""
        if isinstance(value, Fraction) and not isinstance(value, bool):
            if spec.endswith("s"):  # a number through %s (awk): its plain text
                return format(_plain(value), spec)
            text = _format_number(value, spec)
            m = _FORMATTED_NUMBER.search(text)
            if m:
                with contextlib.suppress(ValueError):
                    self.values.append(float(m.group(0).replace(",", "").replace("_", "")))
            return text
        if isinstance(value, str):
            return format(value, spec)
        return format(_text(value), spec)

    def binop(self, op: ast.operator, left: Any, right: Any, state: _State) -> Any:
        if _is_num(left) and _is_num(right):
            a, b = _num(left), _num(right)
            if state.flag and isinstance(op, ast.Pow) and b.denominator == 1:
                # an approximate base: work to 60 digits rather than build an exact huge power
                if a == 0 and b < 0:
                    raise ValueError("division by zero")
                if abs(b) > calc.MAX_EXPONENT:
                    raise ValueError(f"exponent too large (limit {calc.MAX_EXPONENT})")
                with localcontext() as ctx:
                    ctx.prec = _TRIM_DIGITS
                    return calc._checked(Fraction(calc._dec(a) ** int(b)))
            if state.flag:
                a, b = _trim(a), _trim(b)
            result = Fraction(calc._binop(op, a, b, state))  # Fraction // Fraction is an int
            return _trim(result) if state.flag else calc._checked(result)
        if isinstance(op, ast.Add):
            if isinstance(left, str) and isinstance(right, str):
                return _sized(left + right)
            if isinstance(left, list) and isinstance(right, list):
                return _sized(left + right)
            if isinstance(left, tuple) and isinstance(right, tuple):
                return _sized(left + right)
        if isinstance(op, ast.Mult):
            if isinstance(left, str | list | tuple) and _is_num(right):
                left, right = right, left
            if _is_num(left) and isinstance(right, str | list | tuple):
                n = _int(left, "a repeat count")
                if n * len(right) > MAX_LENGTH:
                    raise ValueError(f"too many items (limit {MAX_LENGTH})")
                return right * n
        raise ValueError(
            f"unsupported operand types for {type(op).__name__}: {_type(left)} and {_type(right)}"
        )

    def call(self, node: ast.Call, scope: _Scope, state: _State, d: int) -> Any:
        self.step()
        if _is_print(node):
            self.print(node, scope, state, d)
            return None
        func = node.func
        if isinstance(func, ast.Attribute) and self.math_attr(func, scope) is None:
            if func.attr not in _METHODS:
                raise ValueError(f"method .{func.attr}() is not supported")
            obj = self.eval(func.value, scope, state, d)
            args, kwargs = self.arguments(node, scope, state, d)
            if kwargs:
                raise ValueError(f".{func.attr}() takes no keyword arguments")
            return _method(obj, func.attr, args)
        target = self.eval(func, scope, state, d)
        args, kwargs = self.arguments(node, scope, state, d)
        return self.apply(target, args, kwargs, state)

    def arguments(
        self, node: ast.Call, scope: _Scope, state: _State, d: int
    ) -> tuple[list[Any], dict[str, Any]]:
        """A call's arguments, with ``*items`` and ``**mapping`` spread out."""
        args: list[Any] = []
        for a in node.args:
            if isinstance(a, ast.Starred):
                args.extend(_items_of(self.eval(a.value, scope, state, d)))
            else:
                args.append(self.eval(a, scope, state, d))
        kwargs: dict[str, Any] = {}
        for k in node.keywords:
            value = self.eval(k.value, scope, state, d)
            if k.arg is not None:
                kwargs[k.arg] = value
                continue
            if not isinstance(value, dict) or not all(isinstance(x, str) for x in value):
                raise ValueError("** needs a dict with text keys")
            kwargs.update(value)
        return args, kwargs

    def apply(self, target: Any, args: list[Any], kwargs: dict[str, Any], state: _State) -> Any:
        if isinstance(target, _Builtin):
            try:
                return target.fn(state, *args, **kwargs)
            except TypeError as exc:
                raise ValueError(f"bad arguments to {target.name}(): {exc}") from exc
        if isinstance(target, _Function):
            return self.call_function(target, args, kwargs, state)
        raise ValueError(f"a {_type(target)} cannot be called")

    def call_function(
        self, fn: _Function, args: list[Any], kwargs: dict[str, Any], state: _State
    ) -> Any:
        if id(fn) in self.active:
            raise ValueError(f"{fn.name}() calls itself: recursion is not supported")
        if len(args) > len(fn.params) and fn.varargs is None:
            raise ValueError(f"{fn.name}() takes {len(fn.params)} arguments, got {len(args)}")
        local = _Scope(parent=fn.scope)
        for name, value in zip(fn.params, args, strict=False):
            local.vars[name] = (value, state.flag)
        if fn.varargs is not None:
            local.vars[fn.varargs] = (tuple(args[len(fn.params) :]), state.flag)
        extra: dict[str, Any] = {}
        for name, value in kwargs.items():
            if name not in fn.params:
                if fn.varkw is None:
                    raise ValueError(f"{fn.name}() has no parameter {name!r}")
                extra[name] = value
                continue
            if name in local.vars:
                raise ValueError(f"{fn.name}() got two values for {name!r}")
            local.vars[name] = (value, state.flag)
        if fn.varkw is not None:
            local.vars[fn.varkw] = (extra, state.flag)
        for name in fn.params:
            if name not in local.vars:
                if name not in fn.defaults:
                    raise ValueError(f"{fn.name}() is missing the argument {name!r}")
                local.vars[name] = fn.defaults[name]
        self.active.add(id(fn))
        try:
            if isinstance(fn.body, list):
                try:
                    self.run_block(fn.body, local)
                except _Return as ret:
                    state.flag = state.flag or ret.inexact
                    return ret.value
                return None
            return self.eval(fn.body, local, state)
        finally:
            self.active.discard(id(fn))

    def print(self, node: ast.Call, scope: _Scope, state: _State, d: int) -> None:
        sep, end = ", ", "\n"
        for k in node.keywords:
            value = self.eval(k.value, scope, state, d)
            if k.arg == "sep":
                sep = ", " if value is None else _text(value)
            elif k.arg == "end":
                end = "\n" if value is None else _text(value)
            elif k.arg == "flush":
                pass
            else:
                raise ValueError(f"print() keyword {k.arg!r} is not supported")
        parts: list[str] = []
        for arg in node.args:
            arg_state = _State(state.flag)
            if isinstance(arg, ast.Starred):  # print(*items): each item, labelled items[i]
                items = _items_of(self.eval(arg.value, scope, arg_state, d))
                label = self.src(arg.value)
                shown = [(f"{label}[{i}]", v) for i, v in enumerate(items)]
            else:
                shown = [(self.src(arg), self.eval(arg, scope, arg_state, d))]
            for src, value in shown:
                if isinstance(value, str):
                    parts.append(value)
                elif value is None or isinstance(value, bool | _Infinity):
                    parts.append(f"{src} = {_repr(value)}")
                else:
                    parts.append(f"{src} = {_shown(value, arg_state.flag)}")
                    self.values.extend(_numbers_in(value))
        self.write(sep.join(parts), end)

    def write(self, line: str, end: str) -> None:
        if self.out and self.out[-1].endswith("\0"):  # the previous print had end=""
            line = self.out.pop()[:-1] + line
        if "\n" in end:
            self.emit(line + end.split("\n", 1)[0])
        else:
            self.emit(line + end + "\0")

    def print_values(
        self, state: _State, *values: Any, sep: Any = None, end: Any = None, flush: Any = None
    ) -> None:
        """``print`` called through a name (``p = print; p("x", y)``): values without their
        source text, a number as ``<value>``."""
        parts: list[str] = []
        for value in values:
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, Fraction | list | tuple | dict) and not isinstance(value, bool):
                parts.append(_shown(value, state.flag))
                self.values.extend(_numbers_in(value))
            else:
                parts.append(_repr(value))
        self.write(
            (", " if sep is None else _text(sep)).join(parts), "\n" if end is None else _text(end)
        )


def _star_names(args: ast.arguments) -> tuple[str | None, str | None]:
    return (
        args.vararg.arg if args.vararg else None,
        args.kwarg.arg if args.kwarg else None,
    )


def _is_print(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Name) and node.func.id == "print"


def _compare(op: ast.cmpop, a: Any, b: Any) -> bool:
    if isinstance(op, ast.Is | ast.IsNot):
        if a is not None and b is not None and not isinstance(a, bool) and not isinstance(b, bool):
            raise ValueError("'is' only compares with None, True or False")
        same = a is b if (a is None or b is None) else a == b and type(a) is type(b)
        return same if isinstance(op, ast.Is) else not same
    if isinstance(op, ast.In | ast.NotIn):
        if isinstance(b, dict | list | tuple | range) or isinstance(b, str) and isinstance(a, str):
            inside = a in b
        else:
            raise ValueError(f"'in' needs a container, got {_type(b)}")
        return inside if isinstance(op, ast.In) else not inside
    if isinstance(op, ast.Eq):
        return bool(a == b)
    if isinstance(op, ast.NotEq):
        return bool(a != b)
    try:
        if isinstance(op, ast.Lt):
            return bool(a < b)
        if isinstance(op, ast.LtE):
            return bool(a <= b)
        if isinstance(op, ast.Gt):
            return bool(a > b)
        if isinstance(op, ast.GtE):
            return bool(a >= b)
    except TypeError as exc:
        raise ValueError(f"cannot compare a {_type(a)} with a {_type(b)}") from exc
    raise ValueError(f"unsupported comparison {type(op).__name__}")


def _method(obj: Any, name: str, args: list[Any]) -> Any:
    if isinstance(obj, dict) and name in ("items", "keys", "values", "get"):
        if name == "get":
            if not 1 <= len(args) <= 2:
                raise ValueError(".get() takes a key and an optional default")
            return obj.get(args[0], args[1] if len(args) == 2 else None)
        if args:
            raise ValueError(f".{name}() takes no arguments")
        if name == "items":
            return [(k, v) for k, v in obj.items()]
        return list(obj.keys() if name == "keys" else obj.values())
    if isinstance(obj, list) and name in ("append", "extend"):
        if len(args) != 1:
            raise ValueError(f".{name}() takes one argument")
        if name == "append":
            obj.append(args[0])
        else:
            obj.extend(_items_of(args[0]))
        _sized(obj)
        return None
    if isinstance(obj, list | tuple) and name in ("count", "index"):
        if len(args) != 1:
            raise ValueError(f".{name}() takes one argument")
        if name == "count":
            return Fraction(obj.count(args[0]))
        if args[0] not in obj:
            raise ValueError(".index(): the item is not in the list")
        return Fraction(obj.index(args[0]))
    if isinstance(obj, list | dict) and name == "copy":
        if args:
            raise ValueError(".copy() takes no arguments")
        return obj.copy()
    if isinstance(obj, str) and name == "join":
        if len(args) != 1:
            raise ValueError(".join() takes one argument")
        parts = _items_of(args[0])
        if not all(isinstance(p, str) for p in parts):
            raise ValueError(".join() needs text items (use str(x) or an f-string)")
        return _sized(obj.join(parts))
    raise ValueError(f"a {_type(obj)} has no method .{name}()")


def _items_of(v: Any) -> list[Any]:
    if isinstance(v, list | tuple):
        return list(v)
    if isinstance(v, dict):
        return list(v)
    if isinstance(v, range):
        _sized(v)
        return [Fraction(i) for i in v]
    if isinstance(v, str):
        return list(v)
    raise ValueError(f"cannot iterate over a {_type(v)}")


# --- builtins ---------------------------------------------------------------------------------

_MATH_NAMES = frozenset(
    {
        *calc.FUNCTIONS,
        *calc._STATEFUL,
        *calc._CONSTANTS,
        *("floor", "ceil", "fsum", "prod", "trunc", "inf"),
    }
)
_INEXACT = frozenset(n for n, (_, inexact) in calc._CONSTANTS.items() if inexact)


def _builtin_table(script: _Script) -> dict[str, Callable[..., Any]]:
    def plain(name: str, fn: Callable[..., Fraction]) -> Callable[..., Any]:
        def call(state: _State, *args: Any) -> Fraction:
            try:
                return calc._checked(Fraction(fn(*(_num(a) for a in args))))
            except TypeError as exc:
                raise ValueError(f"bad arguments to {name}(): {exc}") from exc

        return call

    def stateful(name: str) -> Callable[..., Any]:
        fn, lo, hi = calc._STATEFUL[name]

        def call(state: _State, *args: Any) -> Fraction:
            if not lo <= len(args) <= hi:
                want = str(lo) if lo == hi else f"{lo}-{hi}"
                raise ValueError(f"{name}() takes {want} argument(s)")
            return calc._checked(fn(state, *(_num(a) for a in args)))

        return call

    def keyed(state: _State, key: Any) -> Callable[[Any], Any]:
        if key is None:
            return lambda x: x
        return lambda x: script.apply(key, [x], {}, state)

    def sum_(state: _State, iterable: Any, start: Any = Fraction(0)) -> Any:
        total = start
        for x in _items_of(iterable):
            script.step()
            total = script.binop(ast.Add(), total, x, state)
        return total

    def extreme(pick: Callable[..., Any], name: str) -> Callable[..., Any]:
        def call(state: _State, *args: Any, key: Any = None, default: Any = ...) -> Any:
            items = _items_of(args[0]) if len(args) == 1 else list(args)
            if not items:
                if default is ...:
                    raise ValueError(f"{name}() of an empty sequence")
                return default
            try:
                return pick(items, key=keyed(state, key))
            except TypeError as exc:
                raise ValueError(f"{name}(): cannot compare these items") from exc

        return call

    def range_(state: _State, *args: Any) -> range:
        if not 1 <= len(args) <= 3:
            raise ValueError("range() takes 1-3 arguments")
        r = range(*(_int(a, "a range() argument") for a in args))
        return _sized(r)

    def zip_(state: _State, *its: Any, strict: Any = False) -> list[tuple[Any, ...]]:
        lists = [_items_of(i) for i in its]
        if strict and len({len(x) for x in lists}) > 1:
            raise ValueError("zip() arguments have different lengths")
        return _sized(list(zip(*lists, strict=False)))

    def enumerate_(state: _State, it: Any, start: Any = Fraction(0)) -> list[tuple[Any, Any]]:
        s = _int(start, "the start")
        return _sized([(Fraction(i + s), x) for i, x in enumerate(_items_of(it))])

    def sorted_(state: _State, it: Any, key: Any = None, reverse: Any = False) -> list[Any]:
        try:
            return sorted(_items_of(it), key=keyed(state, key), reverse=bool(reverse))
        except TypeError as exc:
            raise ValueError("sorted(): cannot compare these items") from exc

    def len_(state: _State, v: Any) -> Fraction:
        if isinstance(v, list | tuple | dict | str | range):
            return Fraction(len(v))
        raise ValueError(f"len() of a {_type(v)}")

    def list_(state: _State, it: Any = ()) -> list[Any]:
        return _sized(_items_of(it))

    def tuple_(state: _State, it: Any = ()) -> tuple[Any, ...]:
        return _sized(tuple(_items_of(it)))

    def dict_(state: _State, it: Any = None, /, **kw: Any) -> dict[Any, Any]:
        out: dict[Any, Any] = {}
        if it is not None:
            if isinstance(it, dict):
                out.update(it)
            else:
                for pair in _items_of(it):
                    k, v = script.items(pair)
                    out[script.key(k)] = v
        out.update(kw)
        return _sized(out)

    def float_(state: _State, x: Any = Fraction(0)) -> Any:
        if isinstance(x, str) and x.strip().lower() in (
            "inf",
            "+inf",
            "infinity",
            "-inf",
            "-infinity",
        ):
            return _Infinity(-1 if x.strip().startswith("-") else 1)
        if isinstance(x, _Infinity):
            return x
        if isinstance(x, str):
            try:
                return Fraction(x.strip().replace("_", ""))
            except ValueError as exc:
                raise ValueError(f"float() cannot read {x!r}") from exc
        return _num(x)

    def int_(state: _State, x: Any = Fraction(0)) -> Fraction:
        if isinstance(x, str):
            try:
                return Fraction(int(x.strip().replace("_", "")))
            except ValueError as exc:
                raise ValueError(f"int() cannot read {x!r}") from exc
        return Fraction(math.trunc(_num(x)))

    def str_(state: _State, x: Any = "") -> str:
        return _text(x)

    def fraction(state: _State, a: Any = Fraction(0), b: Any = None) -> Fraction:
        if isinstance(a, str):
            if b is not None or len(a) > 100:
                raise ValueError("Fraction(text) takes one short text argument")
            try:
                return Fraction(a.strip())
            except ValueError as exc:
                raise ValueError(f"Fraction() cannot read {a!r}") from exc
        x = _num(a) if b is None else calc._binop(ast.Div(), _num(a), _num(b), calc._Inexact())
        return x

    def round_(state: _State, x: Any, ndigits: Any = None) -> Fraction:
        return calc._round(_num(x), None if ndigits is None else _num(ndigits))

    def pow_(state: _State, a: Any, b: Any) -> Any:
        return script.binop(ast.Pow(), a, b, state)

    def floor(state: _State, x: Any) -> Fraction:
        return Fraction(math.floor(_num(x)))

    def ceil(state: _State, x: Any) -> Fraction:
        return Fraction(math.ceil(_num(x)))

    def prod(state: _State, it: Any, start: Any = Fraction(1)) -> Any:
        total = start
        for x in _items_of(it):
            script.step()
            total = script.binop(ast.Mult(), total, x, state)
        return total

    kinds = {
        "int": lambda v: isinstance(v, Fraction) and not isinstance(v, bool) and v.denominator == 1,
        "float": lambda v: isinstance(v, Fraction) and not isinstance(v, bool),
        "str": lambda v: isinstance(v, str),
        "list": lambda v: isinstance(v, list),
        "tuple": lambda v: isinstance(v, tuple),
        "dict": lambda v: isinstance(v, dict),
        "bool": lambda v: isinstance(v, bool),
    }

    def isinstance_(state: _State, value: Any, types: Any) -> bool:
        """``isinstance`` against the builtin types; a number counts as a float (the script's
        floats are exact here) and, when whole, also as an int."""
        wanted = list(types) if isinstance(types, tuple) else [types]
        names = [t.name for t in wanted if isinstance(t, _Builtin) and t.name in kinds]
        if len(names) != len(wanted):
            raise ValueError("isinstance() takes int, float, str, list, tuple, dict or bool")
        return any(kinds[n](value) for n in names)

    def format_(state: _State, value: Any, spec: Any = "") -> str:
        if not isinstance(spec, str):
            raise ValueError("format() needs a text spec")
        return script.format_value(value, spec)

    def any_(state: _State, it: Any) -> bool:
        return any(_items_of(it))

    def all_(state: _State, it: Any) -> bool:
        return all(_items_of(it))

    def reversed_(state: _State, it: Any) -> list[Any]:
        return list(reversed(_items_of(it)))

    table: dict[str, Callable[..., Any]] = {
        name: plain(name, fn) for name, fn in calc.FUNCTIONS.items() if name != "round"
    }
    table |= {name: stateful(name) for name in calc._STATEFUL}
    table |= {
        "round": round_,
        "sum": sum_,
        "fsum": sum_,
        "prod": prod,
        "min": extreme(min, "min"),
        "max": extreme(max, "max"),
        "range": range_,
        "zip": zip_,
        "enumerate": enumerate_,
        "sorted": sorted_,
        "reversed": reversed_,
        "len": len_,
        "list": list_,
        "tuple": tuple_,
        "dict": dict_,
        "float": float_,
        "int": int_,
        "trunc": int_,
        "str": str_,
        "pow": pow_,
        "floor": floor,
        "ceil": ceil,
        "format": format_,
        "isinstance": isinstance_,
        "bool": lambda state, x=False: bool(x),
        "any": any_,
        "all": all_,
        "Fraction": fraction,
    }
    return table


# --- entry points -----------------------------------------------------------------------------


@dataclass
class ScriptResult:
    text: str  # what evaluate_script returns
    values: list[float]  # every number shown, in order (measure_calc_fit compares these)


def run(script: str, max_seconds: float = MAX_SECONDS) -> ScriptResult:
    """Run ``script`` exactly; see the module docstring. Raises ``ValueError``, also when it runs
    past ``max_seconds``."""
    if not script or not script.strip():
        raise ValueError("empty script")
    if len(script) > MAX_SCRIPT_CHARS:
        raise ValueError(f"script too long (limit {MAX_SCRIPT_CHARS} chars)")
    try:
        tree = ast.parse(script, mode="exec")
    except SyntaxError as exc:
        raise ValueError(f"invalid script: line {exc.lineno}: {exc.msg}") from exc
    except (RecursionError, MemoryError, ValueError) as exc:  # ValueError: null bytes
        raise ValueError("invalid script") from exc
    if len(tree.body) > MAX_STATEMENTS:
        raise ValueError(f"too many statements (limit {MAX_STATEMENTS})")
    interp = _Script(script, max_seconds)
    try:
        interp.run_block(tree.body, interp.globals, top=True)
    except (_Break, _Continue) as exc:
        raise ValueError("break or continue outside a loop") from exc
    except _Return as exc:  # pragma: no cover - run_stmt refuses a top-level return
        raise ValueError("return outside a function") from exc
    except RecursionError as exc:
        raise ValueError("script nested too deeply") from exc
    lines = [line[:-1] if line.endswith("\0") else line for line in interp.out]
    text = "\n".join(lines).rstrip("\n")  # a print(..., end="") line may hold its own newlines
    if not text.strip():
        raise ValueError("the script prints nothing (end it with print(...))")
    return ScriptResult(text, interp.values)


def evaluate_script(script: str) -> str:
    return run(script).text
