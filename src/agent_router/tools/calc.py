"""Exact calculator: a whitelisted AST evaluator over Fractions (agent-router, MIT).

Never calls ``eval``/``exec``. Supports int/decimal literals (as exact Fractions),
``+ - * / // % **``, unary +/-, parentheses, postfix percent (``17% of 2340``, ``50%``) and
the functions in ``FUNCTIONS``. Irrational results (``sqrt(2)``, fractional powers, and the
approximate functions ``log``, ``ln``, ``log10``, ``log2``, ``exp`` and the constants ``pi`` and
``e``, 50 digits) are reported as ``≈ decimal``. A ``math.`` prefix is accepted. A top-level
list or tuple (``[2*3, 7/2]``) evaluates each item and returns ``[6, 7/2 (≈ 3.5)]``.
``evaluate_script`` runs a short straight-line script (assignments, ``print``); see its
docstring. All failures raise ``ValueError``.
"""

import ast
import math
import operator
import re
from collections.abc import Callable
from decimal import Decimal, localcontext
from fractions import Fraction

MAX_EXPONENT = 10_000
# Output cap: stays under CPython's 4300-digit int->str limit.
MAX_DIGITS = 4_000
# Intermediate cap on numerator + denominator size (~2x the output cap).
MAX_RESULT_BITS = 32_000
# factorial/comb/perm/round arguments; factorial(1000) has 2568 digits.
MAX_INT_ARG = 1_000
MAX_EXPRESSION_CHARS = 1_000
MAX_DEPTH = 100
MAX_SCRIPT_CHARS = 10_000
MAX_STATEMENTS = 200
MAX_NAMES = 100
MAX_EXP_ARG = 9_000  # exp(9000) has ~3,900 digits, just under MAX_DIGITS
MAX_ITEMS = 50  # a top-level list: agents batch a table's rows (6 of ~600 calls in the fp runs)
DECIMAL_PLACES = 10
_APPROX_DIGITS = 50

_NUM = r"\d+(?:\.\d+)?"
_THOUSANDS = re.compile(r"(?<![\d.,])\d{1,3}(?:,\d{3})+(?![\d.,])")
_CALL = re.compile(r"[A-Za-z_]\w*\s*\(")
_PERCENT_OF = re.compile(rf"({_NUM})\s*%\s*of\s+(.+)$", re.IGNORECASE)
# "50%" / "50% * x": percent. "50% + 10" (no space before %) is percent; "10 % -3" is modulo.
_POSTFIX_PERCENT = re.compile(rf"({_NUM})(?:\s*%(?=\s*(?:$|[)*/,]))|%(?=\s*[+\-]))")


class _Inexact:
    """Mutable flag shared through one evaluation."""

    def __init__(self) -> None:
        self.flag = False


def _as_int(x: Fraction, fn: str) -> int:
    if x.denominator != 1:
        raise ValueError(f"{fn}() needs integer arguments")
    return x.numerator


def _small_int(x: Fraction, fn: str) -> int:
    n = _as_int(x, fn)
    if abs(n) > MAX_INT_ARG:
        raise ValueError(f"{fn}() argument too large (limit {MAX_INT_ARG})")
    return n


def percent_of(pct: Fraction, value: Fraction = Fraction(1)) -> Fraction:
    """``pct`` percent of ``value`` (``percent_of(17, 2340)`` is 17% of 2340)."""
    return Fraction(pct) / 100 * Fraction(value)


def _sqrt(x: Fraction, state: _Inexact) -> Fraction:
    if x < 0:
        raise ValueError("sqrt() of a negative number")
    rn, rd = math.isqrt(x.numerator), math.isqrt(x.denominator)
    if rn * rn == x.numerator and rd * rd == x.denominator:
        return Fraction(rn, rd)
    state.flag = True
    with localcontext() as ctx:
        ctx.prec = _APPROX_DIGITS
        return Fraction(Decimal(x.numerator).sqrt() / Decimal(x.denominator).sqrt())


def _pow(base: Fraction, exp: Fraction, state: _Inexact) -> Fraction:
    if abs(exp) > MAX_EXPONENT:
        raise ValueError(f"exponent too large (limit {MAX_EXPONENT})")
    if base != 0:
        # |log2(result)| ~ |exp| * |log2(base)|; reject before doing the work.
        log2_base = abs(base.numerator.bit_length() - base.denominator.bit_length()) + 1
        if exp.denominator == 1:
            log2_base = max(base.numerator.bit_length(), base.denominator.bit_length())
        if log2_base * abs(exp) > MAX_RESULT_BITS:
            raise ValueError("result too large")
    if exp.denominator == 1:
        e = exp.numerator
        if base == 0 and e < 0:
            raise ValueError("division by zero")
        return base**e
    if base < 0:
        raise ValueError("fractional power of a negative number")
    if base == 0:
        return Fraction(0)
    state.flag = True
    with localcontext() as ctx:
        ctx.prec = _APPROX_DIGITS
        d = Decimal(base.numerator) / Decimal(base.denominator)
        return Fraction(d ** (Decimal(exp.numerator) / Decimal(exp.denominator)))


def _round(x: Fraction, ndigits: Fraction | None = None) -> Fraction:
    if ndigits is None:
        return Fraction(round(x))
    return Fraction(round(x, _small_int(ndigits, "round")))


def _factorial(n: Fraction) -> Fraction:
    k = _small_int(n, "factorial")
    if k < 0:
        raise ValueError("factorial() of a negative number")
    return Fraction(math.factorial(k))


def _comb(n: Fraction, k: Fraction) -> Fraction:
    a, b = _small_int(n, "comb"), _small_int(k, "comb")
    if a < 0 or b < 0:
        raise ValueError("comb() needs non-negative integers")
    return Fraction(math.comb(a, b))


def _perm(n: Fraction, k: Fraction | None = None) -> Fraction:
    a = _small_int(n, "perm")
    b = None if k is None else _small_int(k, "perm")
    if a < 0 or (b is not None and b < 0):
        raise ValueError("perm() needs non-negative integers")
    return Fraction(math.perm(a, b))


def _gcd(*xs: Fraction) -> Fraction:
    return Fraction(math.gcd(*(_as_int(x, "gcd") for x in xs)))


def _lcm(*xs: Fraction) -> Fraction:
    ints = [_as_int(x, "lcm") for x in xs]
    if sum(i.bit_length() for i in ints) > MAX_RESULT_BITS:
        raise ValueError("result too large")
    return Fraction(math.lcm(*ints))


_PI = Fraction(Decimal("3.14159265358979323846264338327950288419716939937510582097494"))


def _dec(x: Fraction) -> Decimal:
    return Decimal(x.numerator) / Decimal(x.denominator)


def _positive(x: Fraction, fn: str) -> None:
    if x <= 0:
        raise ValueError(f"{fn}() of a non-positive number (math domain error)")


def _ln(x: Fraction, state: _Inexact) -> Fraction:
    _positive(x, "ln")
    if x == 1:
        return Fraction(0)
    state.flag = True
    with localcontext() as ctx:
        ctx.prec = _APPROX_DIGITS
        return Fraction(_dec(x).ln())


def _log(x: Fraction, state: _Inexact, base: Fraction | None = None) -> Fraction:
    if base is None:
        _positive(x, "log")
        return _ln(x, state)
    _positive(x, "log")
    _positive(base, "log")
    if base == 1:
        raise ValueError("log() with base 1 (division by zero)")
    if x == 1:
        return Fraction(0)
    state.flag = True
    with localcontext() as ctx:
        ctx.prec = _APPROX_DIGITS
        return Fraction(_dec(x).ln() / _dec(base).ln())


def _log10(x: Fraction, state: _Inexact) -> Fraction:
    _positive(x, "log10")
    if x == 1:
        return Fraction(0)
    state.flag = True
    with localcontext() as ctx:
        ctx.prec = _APPROX_DIGITS
        return Fraction(_dec(x).log10())


def _log2(x: Fraction, state: _Inexact) -> Fraction:
    _positive(x, "log2")
    if x == 1:
        return Fraction(0)
    state.flag = True
    with localcontext() as ctx:
        ctx.prec = _APPROX_DIGITS
        return Fraction(_dec(x).ln() / Decimal(2).ln())


def _exp(x: Fraction, state: _Inexact) -> Fraction:
    if abs(x) > MAX_EXP_ARG:
        raise ValueError(f"exp() argument too large (limit {MAX_EXP_ARG})")
    if x == 0:
        return Fraction(1)
    state.flag = True
    with localcontext() as ctx:
        ctx.prec = _APPROX_DIGITS
        return Fraction(_dec(x).exp())


def _e_constant() -> Fraction:
    with localcontext() as ctx:
        ctx.prec = _APPROX_DIGITS + 10
        return Fraction(Decimal(1).exp())


_E = _e_constant()
# name -> (value, inexact): usable in an expression with no assignment
_CONSTANTS: dict[str, tuple[Fraction, bool]] = {"pi": (_PI, True), "e": (_E, True)}

FUNCTIONS: dict[str, Callable[..., Fraction]] = {
    "abs": lambda x: abs(x),
    "round": _round,
    "factorial": _factorial,
    "comb": _comb,
    "perm": _perm,
    "gcd": _gcd,
    "lcm": _lcm,
    "percent_of": percent_of,
}
# name -> (function called as fn(state, *args), min args, max args); the result may be inexact
_STATEFUL: dict[str, tuple[Callable[..., Fraction], int, int]] = {
    "sqrt": (lambda state, x: _sqrt(x, state), 1, 1),
    "ln": (lambda state, x: _ln(x, state), 1, 1),
    "log": (lambda state, x, base=None: _log(x, state, base), 1, 2),
    "log10": (lambda state, x: _log10(x, state), 1, 1),
    "log2": (lambda state, x: _log2(x, state), 1, 1),
    "exp": (lambda state, x: _exp(x, state), 1, 1),
}

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}


def _bits(x: Fraction) -> int:
    return x.numerator.bit_length() + x.denominator.bit_length()


def _binop(op_node: ast.operator, left: Fraction, right: Fraction, state: _Inexact) -> Fraction:
    if isinstance(op_node, ast.Pow):
        return _checked(_pow(left, right, state))
    op = _BINOPS.get(type(op_node))
    if op is None:
        raise ValueError(f"unsupported operator {type(op_node).__name__}")
    if _bits(left) + _bits(right) > MAX_RESULT_BITS:
        raise ValueError("result too large")
    try:
        return op(left, right)
    except ZeroDivisionError as e:
        raise ValueError("division by zero") from e


def _checked(x: Fraction) -> Fraction:
    if _bits(x) > MAX_RESULT_BITS:
        raise ValueError("result too large")
    return x


_Env = dict[str, tuple[Fraction, bool]]


def _lookup(name: str, state: _Inexact, env: _Env | None) -> Fraction:
    found = (env or {}).get(name) or _CONSTANTS.get(name)
    if found is None:
        raise ValueError(f"name {name!r} is not defined")
    value, inexact = found
    state.flag = state.flag or inexact
    return value


def _math_name(node: ast.AST) -> str | None:
    """``log`` for the call target ``math.log``; None for any other attribute."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "math"
    ):
        return node.attr
    return None


def _eval(node: ast.AST, state: _Inexact, depth: int = 0, env: _Env | None = None) -> Fraction:
    if depth > MAX_DEPTH:
        raise ValueError(f"expression nested too deeply (limit {MAX_DEPTH})")
    if isinstance(node, ast.Expression):
        return _eval(node.body, state, depth + 1, env)
    if isinstance(node, ast.Name):
        return _lookup(node.id, state, env)
    if isinstance(node, ast.Attribute):
        name = _math_name(node)
        if name is None:
            raise ValueError("attribute access is not supported (only math.<name>)")
        return _lookup(name, state, None)  # math.<constant>; never a user variable
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise ValueError(f"unsupported literal {node.value!r}")
        return Fraction(repr(node.value)) if isinstance(node.value, float) else Fraction(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        v = _eval(node.operand, state, depth + 1, env)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        # "a+b+c+..." parses as a left-leaning chain; walk it iteratively so long flat
        # sums/products don't count as nesting. Only right operands add depth.
        chain = [node]
        while isinstance(chain[-1].left, ast.BinOp):
            chain.append(chain[-1].left)
        acc = _eval(chain[-1].left, state, depth + 1, env)
        for link in reversed(chain):
            acc = _binop(link.op, acc, _eval(link.right, state, depth + 1, env), state)
        return acc
    if isinstance(node, ast.Call):
        name = node.func.id if isinstance(node.func, ast.Name) else _math_name(node.func)
        if name is None or node.keywords:
            raise ValueError("only plain calls to supported functions are allowed")
        if name not in _STATEFUL and name not in FUNCTIONS:
            raise ValueError(f"unknown function {name!r}")
        args = [_eval(a, state, depth + 1, env) for a in node.args]
        try:
            if name in _STATEFUL:
                fn, lo, hi = _STATEFUL[name]
                if not lo <= len(args) <= hi:
                    want = str(lo) if lo == hi else f"{lo}-{hi}"
                    raise ValueError(f"{name}() takes {want} argument(s)")
                return _checked(fn(state, *args))
            fn = FUNCTIONS.get(name)
            if fn is None:
                raise ValueError(f"unknown function {name!r}")
            return _checked(Fraction(fn(*args)))
        except TypeError as e:
            raise ValueError(f"bad arguments to {name}(): {e}") from e
    raise ValueError(f"unsupported syntax: {type(node).__name__}")


def _preprocess(expression: str) -> str:
    expr = expression.strip()
    if not _CALL.search(expr) and not expr.startswith("["):  # in a list, "5,100" is two items
        # "2,340" is a thousands separator only when no function call could use commas.
        expr = _THOUSANDS.sub(lambda m: m.group(0).replace(",", ""), expr)
    m = _PERCENT_OF.search(expr)
    if m:
        rest = _THOUSANDS.sub(lambda mm: mm.group(0).replace(",", ""), m.group(2))
        expr = f"{expr[: m.start()]}percent_of({m.group(1)}, ({rest}))"
    expr = _POSTFIX_PERCENT.sub(r"percent_of(\1)", expr)
    return expr.replace("^", "**").replace("×", "*").replace("÷", "/")


def _decimal(x: Fraction) -> str:
    with localcontext() as ctx:
        ctx.prec = max(len(str(abs(x.numerator) // x.denominator)), 1) + DECIMAL_PLACES + 5
        d = (Decimal(x.numerator) / Decimal(x.denominator)).quantize(
            Decimal(1).scaleb(-DECIMAL_PLACES)
        )
    s = f"{d:f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _check_digits(x: Fraction) -> None:
    # bit_length * log10(2) over-estimates digits by < 1; avoids str() on huge ints.
    for part in (x.numerator, x.denominator):
        if part.bit_length() * 0.30103 > MAX_DIGITS:
            raise ValueError(f"result has more than {MAX_DIGITS} digits")


def format_result(x: Fraction, inexact: bool = False) -> str:
    _check_digits(x)
    if inexact:
        return f"≈ {_decimal(x)}"
    if x.denominator == 1:
        return str(x.numerator)
    return f"{x.numerator}/{x.denominator} (≈ {_decimal(x)})"


def evaluate(expression: str) -> str:
    """Evaluate ``expression`` exactly; return ``int``, ``a/b (≈ decimal)`` or ``≈ decimal``."""
    if not expression or not expression.strip():
        raise ValueError("empty expression")
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise ValueError(f"expression too long (limit {MAX_EXPRESSION_CHARS} chars)")
    source = _preprocess(expression)
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"invalid expression: {e.msg}") from e
    except (RecursionError, MemoryError) as e:
        raise ValueError("expression nested too deeply") from e
    items = tree.body.elts if isinstance(tree.body, ast.List | ast.Tuple) else None
    if items is not None:
        if not items:
            raise ValueError("empty list")
        if len(items) > MAX_ITEMS:
            raise ValueError(f"too many items (limit {MAX_ITEMS})")
        return "[" + ", ".join(_one(ast.Expression(body=node)) for node in items) + "]"
    return _one(tree)


def _one(tree: ast.Expression) -> str:
    state = _Inexact()
    try:
        return format_result(_eval(tree, state), state.flag)
    except (ArithmeticError, RecursionError, MemoryError) as e:  # decimal/overflow edge cases
        raise ValueError(f"cannot evaluate: {type(e).__name__}") from e


# --- scripts ----------------------------------------------------------------------------------

_BUILTIN_NAMES = frozenset({*FUNCTIONS, *_STATEFUL, *_CONSTANTS, "math", "print"})
_CONSTRUCTS = {
    "For": "for loop",
    "AsyncFor": "for loop",
    "While": "while loop",
    "If": "if statement",
    "FunctionDef": "function definition",
    "AsyncFunctionDef": "function definition",
    "ClassDef": "class definition",
    "With": "with statement",
    "Try": "try statement",
    "Return": "return statement",
    "Delete": "del statement",
    "Global": "global statement",
    "Assert": "assert statement",
    "Raise": "raise statement",
    "AnnAssign": "annotated assignment",
    "Match": "match statement",
}
_EXPR_CONSTRUCTS = {
    "ListComp": "comprehension",
    "SetComp": "comprehension",
    "DictComp": "comprehension",
    "GeneratorExp": "comprehension",
    "Subscript": "subscript",
    "Lambda": "lambda",
    "List": "list",
    "Tuple": "tuple",
    "Dict": "dict",
    "Set": "set",
    "JoinedStr": "f-string",
    "Compare": "comparison",
    "BoolOp": "boolean operator",
    "IfExp": "conditional expression",
    "NamedExpr": "walrus assignment",
}


def _where(node: ast.AST, msg: str) -> ValueError:
    return ValueError(f"line {getattr(node, 'lineno', '?')}: {msg}")


def _first_construct(node: ast.AST) -> ast.AST | None:
    """The first expression node in ``node`` that is a named unsupported construct."""
    for sub in ast.walk(node):
        if type(sub).__name__ in _EXPR_CONSTRUCTS:
            return sub
    return None


def _source(script: str, node: ast.AST) -> str:
    return (ast.get_source_segment(script, node) or ast.unparse(node)).strip()


def _value(node: ast.expr, env: _Env) -> tuple[Fraction, bool]:
    if isinstance(node, ast.JoinedStr):
        raise _where(node, 'f-strings are not supported (use print("label", expr))')
    state = _Inexact()
    try:
        return _eval(node, state, 0, env), state.flag
    except ValueError as exc:
        if str(exc).startswith("unsupported syntax"):
            bad = _first_construct(node)
            if bad is not None:
                raise _where(
                    bad, f"{_EXPR_CONSTRUCTS[type(bad).__name__]} is not supported"
                ) from exc
        raise _where(node, str(exc)) from exc
    except (ArithmeticError, RecursionError, MemoryError) as exc:
        raise _where(node, f"cannot evaluate: {type(exc).__name__}") from exc


def _show(script: str, node: ast.expr, env: _Env) -> str:
    value, inexact = _value(node, env)
    try:
        return f"{_source(script, node)} = {format_result(value, inexact)}"
    except ValueError as exc:
        raise _where(node, str(exc)) from exc


def _print_line(script: str, call: ast.Call, env: _Env) -> str | None:
    if call.keywords:
        raise _where(call, "print() keyword arguments (sep, end, file) are not supported")
    parts: list[str] = []
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            parts.append(arg.value)  # a label, emitted verbatim
        else:
            parts.append(_show(script, arg, env))
    return ", ".join(parts) if parts else None


def _check_import(stmt: ast.Import | ast.ImportFrom) -> None:
    if isinstance(stmt, ast.Import):
        if any(a.name != "math" or a.asname for a in stmt.names):
            raise _where(stmt, "only 'import math' is supported")
        return
    if stmt.module != "math" or stmt.level:
        raise _where(stmt, "only 'from math import ...' is supported")
    for a in stmt.names:
        if a.asname or a.name not in _BUILTIN_NAMES - {"math", "print"}:
            raise _where(stmt, f"math.{a.name} is not supported")


def _assign(script: str, stmt: ast.stmt, env: _Env) -> None:
    if isinstance(stmt, ast.Assign):
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            raise _where(stmt, "only 'name = expression' assignments are supported")
        target, aug = stmt.targets[0], None
    else:
        assert isinstance(stmt, ast.AugAssign)
        if not isinstance(stmt.target, ast.Name):
            raise _where(stmt, "only 'name += expression' updates are supported")
        target, aug = stmt.target, stmt.op
    name = target.id
    if name in _BUILTIN_NAMES:
        raise _where(stmt, f"cannot assign to {name!r}: it is a function or constant")
    if name not in env and len(env) >= MAX_NAMES:
        raise _where(stmt, f"too many names (limit {MAX_NAMES})")
    value, inexact = _value(stmt.value, env)
    if aug is not None:
        if name not in env:
            raise _where(stmt, f"name {name!r} is not defined")
        old, old_inexact = env[name]
        state = _Inexact()
        try:
            value = _binop(aug, old, value, state)
        except ValueError as exc:
            raise _where(stmt, str(exc)) from exc
        inexact = inexact or old_inexact or state.flag
    env[name] = (_checked(value), inexact)


def evaluate_script(script: str) -> str:
    """Run a straight-line script exactly; return one output line per ``print`` / bare expression.

    Statements (newline- or ``;``-separated): ``import math`` and ``from math import ...``
    (ignored), ``name = expr``, ``name += expr`` (and the other arithmetic operators),
    ``print(a, "label", b)`` and a bare expression. An expression is shown as
    ``<source text> = <value>``; a string-literal ``print`` argument is emitted verbatim; the
    arguments of one ``print`` are joined with ``", "``. Names keep their inexact (``≈``) flag.
    No loops, functions, f-strings, subscripts, comprehensions, attribute access other than
    ``math.<name>`` or I/O: those raise ``ValueError`` naming the construct and its line. The
    script is parsed, never executed. All failures raise ``ValueError``.
    """
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
    env: _Env = {}
    out: list[str] = []
    for stmt in tree.body:
        kind = type(stmt).__name__
        if isinstance(stmt, ast.Import | ast.ImportFrom):
            _check_import(stmt)
        elif isinstance(stmt, ast.Assign | ast.AugAssign):
            _assign(script, stmt, env)
        elif isinstance(stmt, ast.Expr):
            call = stmt.value
            if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "print":
                line = _print_line(script, call, env)
                if line is not None:
                    out.append(line)
                continue
            out.append(_show(script, stmt.value, env))
        else:
            raise _where(stmt, f"{_CONSTRUCTS.get(kind, kind)} is not supported")
    if not out:
        raise ValueError("the script prints nothing (end it with print(...))")
    return "\n".join(out)
