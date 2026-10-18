"""Translate an ``awk 'BEGIN{...}'`` arithmetic program into the calculator's script language.

The first-principles agents compute with awk as often as with one-line python: assignments,
``printf``, ``^``, ``for (i=0; i<n; i++)`` and ``split`` of a literal list, all in a ``BEGIN``
block with no input. ``translate`` turns such a program into a script
:mod:`agent_router.tools.calc_script` runs (``printf`` becomes ``print(... format(x, spec) ...,
end="")``), so the router's fit check can ask whether the calculator computes it. Anything else
awk does (fields, patterns, getline, regexes, string concatenation, a non-literal ``split``)
returns None. Nothing is executed here: this is a parser that emits text.
"""

from __future__ import annotations

import keyword
import re

_TOKEN = re.compile(
    r"""
    (?P<ws>[ \t]+|\\\n)
  | (?P<comment>\#[^\n]*)
  | (?P<nl>\n)
  | (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)
  | (?P<str>"(?:[^"\\\n]|\\.)*")
  | (?P<name>[A-Za-z_]\w*)
  | (?P<op>\*\*=|\+\+|--|\+=|-=|\*=|/=|%=|\^=|==|!=|<=|>=|&&|\|\||\*\*|[-+*/%^<>=!?:;,(){}\[\]])
    """,
    re.X,
)
_FUNCTIONS = {"log": "log", "exp": "exp", "sqrt": "sqrt", "int": "int"}
_KEYWORDS = {"if", "else", "for", "while", "printf", "print", "split", "break", "continue"}
_CONVERSION = re.compile(r"%([-+ 0#]*)(\d*)(?:\.(\d+))?([diouxXeEfgGcs%])")
_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/"}


class _Refuse(Exception):
    pass


def _tokens(src: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if m is None:
            raise _Refuse(f"unexpected {src[pos]!r}")
        pos = m.end()
        kind = m.lastgroup or ""
        if kind in ("ws", "comment"):
            continue
        out.append((kind, m.group(0)))
    out.append(("eof", ""))
    return out


def _unquote(literal: str) -> str:
    body = literal[1:-1]
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), "\\" + m.group(1)), body)


class _Translator:
    def __init__(self, src: str) -> None:
        self.toks = _tokens(src)
        self.i = 0
        self.lines: list[str] = []
        self.scalars: set[str] = set()
        self.arrays: set[str] = set()

    # tokens

    def peek(self, ahead: int = 0) -> tuple[str, str]:
        return self.toks[min(self.i + ahead, len(self.toks) - 1)]

    def take(self, value: str | None = None, kind: str | None = None) -> str:
        k, v = self.peek()
        if (value is not None and v != value) or (kind is not None and k != kind):
            raise _Refuse(f"expected {value or kind}, got {v!r}")
        self.i += 1
        return v

    def at(self, value: str) -> bool:
        return self.peek()[1] == value and self.peek()[0] in ("op", "name")

    def skip_terminators(self) -> None:
        while self.peek()[0] == "nl" or self.at(";"):
            self.i += 1

    def skip_newlines(self) -> None:
        while self.peek()[0] == "nl":
            self.i += 1

    # names

    def var(self, name: str) -> str:
        if name in _FUNCTIONS or name in _KEYWORDS or name in ("BEGIN", "END", "getline"):
            raise _Refuse(f"{name} used as a variable")
        if name.isupper() and name in ("NR", "NF", "FS", "OFS", "RS", "ORS", "FILENAME"):
            raise _Refuse("awk built-in variables are input-related")
        safe = f"v_{name}" if keyword.iskeyword(name) or name in ("None", "True", "False") else name
        return safe

    # statements

    def program(self) -> str:
        self.skip_newlines()
        self.take("BEGIN")
        self.skip_newlines()
        self.take("{")
        body = self.block_body(0)
        self.take("}")
        self.skip_terminators()
        if self.peek()[0] != "eof":
            raise _Refuse("only a BEGIN block is supported")
        init = [f"{a} = {{}}" for a in sorted(self.arrays)]
        init += [f"{s} = 0" for s in sorted(self.scalars - self.arrays)]
        return "\n".join(init + body)

    def block_body(self, depth: int) -> list[str]:
        out: list[str] = []
        self.skip_terminators()
        while not self.at("}") and self.peek()[0] != "eof":
            out += self.statement(depth)
            self.skip_terminators()
        return out

    def body(self, depth: int) -> list[str]:
        """A statement or a braced block, as indented lines (``pass`` when empty)."""
        self.skip_newlines()
        if self.at("{"):
            self.take("{")
            lines = self.block_body(depth)
            self.take("}")
        else:
            lines = self.statement(depth)
        return lines or ["    " * depth + "pass"]

    def statement(self, depth: int) -> list[str]:
        pad = "    " * depth
        kind, v = self.peek()
        if kind == "op" and v == "{":
            self.take("{")
            lines = self.block_body(depth)
            self.take("}")
            return lines
        if kind == "name" and v == "if":
            self.take("if")
            self.take("(")
            cond = self.expr()
            self.take(")")
            lines = [f"{pad}if {cond}:"] + self.body(depth + 1)
            save = self.i
            self.skip_terminators()
            if self.at("else"):
                self.take("else")
                lines += [f"{pad}else:"] + self.body(depth + 1)
            else:
                self.i = save
            return lines
        if kind == "name" and v == "while":
            self.take("while")
            self.take("(")
            cond = self.expr()
            self.take(")")
            return [f"{pad}while {cond}:"] + self.body(depth + 1)
        if kind == "name" and v == "for":
            return self.for_loop(depth)
        if kind == "name" and v == "printf":
            self.take("printf")
            return [pad + self.printf()]
        if kind == "name" and v == "print":
            self.take("print")
            return [pad + self.print()]
        if kind == "name" and v == "break":
            self.take("break")
            return [pad + "break"]
        if kind == "name" and v == "split":
            return [pad + self.split()]
        return [pad + self.simple()]

    def for_loop(self, depth: int) -> list[str]:
        pad = "    " * depth
        self.take("for")
        self.take("(")
        if self.peek()[0] == "name" and self.peek(1)[1] == "in":
            raise _Refuse("for (k in array) is not supported")
        init = None if self.at(";") else self.simple()
        self.take(";")
        cond = "True" if self.at(";") else self.expr()
        self.take(";")
        step = None if self.at(")") else self.simple()
        self.take(")")
        start = self.i
        inner = self.body(depth + 1)
        if any(t[1] == "continue" for t in self.toks[start : self.i]):
            raise _Refuse("continue inside for(;;) is not supported")
        lines = [pad + init] if init else []
        lines.append(f"{pad}while {cond}:")
        lines += inner
        if step:
            lines.append("    " * (depth + 1) + step)
        return lines

    def lvalue(self) -> str:
        name = self.take(kind="name")
        if self.at("["):
            self.take("[")
            index = self.expr()
            self.take("]")
            self.arrays.add(self.var(name))
            return f"{self.var(name)}[{index}]"
        self.scalars.add(self.var(name))
        return self.var(name)

    def simple(self) -> str:
        """An assignment, ``x++`` / ``x--`` / ``++x``, or a bare expression."""
        if self.at("++") or self.at("--"):
            op = self.take()
            return f"{self.lvalue()} {'+' if op == '++' else '-'}= 1"
        if self.peek()[0] == "name" and (
            self.peek(1)[1] in ("=", "+=", "-=", "*=", "/=", "%=", "^=", "**=", "++", "--", "[")
        ):
            save = self.i
            target = self.lvalue()
            op = self.peek()[1]
            if op in ("++", "--"):
                self.take()
                return f"{target} {'+' if op == '++' else '-'}= 1"
            if op in ("=", "+=", "-=", "*=", "/=", "%=", "^=", "**="):
                self.take()
                py = {"^=": "**=", "**=": "**="}.get(op, op)
                return f"{target} {py} {self.expr()}"
            self.i = save
        return self.expr()

    def args(self, closing: str | None = None) -> list[str]:
        out = [self.expr()]
        while self.at(","):
            self.take(",")
            self.skip_newlines()
            out.append(self.expr())
        return out

    def printf(self) -> str:
        paren = self.at("(")
        if paren:
            self.take("(")
        kind, fmt = self.peek()
        if kind != "str":
            raise _Refuse("printf needs a literal format")
        self.take()
        values: list[str] = []
        while self.at(","):
            self.take(",")
            self.skip_newlines()
            values.append(self.expr())
        if paren:
            self.take(")")
        if self.at(">") or self.at("|"):
            raise _Refuse("printf redirection")
        return f"print({_format_call(_unquote(fmt), values)}, end='')"

    def print(self) -> str:
        if self.at(";") or self.at("}") or self.peek()[0] == "nl":
            return "print('')"
        parts: list[str] = []
        for item in self.args():
            parts.append(item if item.startswith(("'", '"')) else f"format({item}, '.6g')")
        if self.at(">") or self.at("|"):
            raise _Refuse("print redirection")
        return f"print({', '.join(parts)}, sep=' ')"

    def split(self) -> str:
        """``split("1 2 3", A, " ")`` of a literal list, as a dict literal ``A = {1: 1, ...}``."""
        self.take("split")
        self.take("(")
        kind, text = self.peek()
        if kind != "str":
            raise _Refuse("split of a non-literal string")
        self.take()
        self.take(",")
        name = self.var(self.take(kind="name"))
        sep = " "
        if self.at(","):
            self.take(",")
            kind, s = self.peek()
            if kind != "str":
                raise _Refuse("split with a non-literal separator")
            self.take()
            sep = _unquote(s)
        self.take(")")
        raw = _unquote(text)
        pieces = raw.split() if sep == " " else raw.split(sep)
        items = []
        for n, piece in enumerate(pieces, start=1):
            try:
                float(piece)
                items.append(f"{n}: {piece}")
            except ValueError:
                items.append(f"{n}: {piece!r}")
        self.arrays.add(name)
        return f"{name} = {{{', '.join(items)}}}"

    # expressions (a precedence climb that emits fully parenthesised python)

    def expr(self) -> str:
        return self.ternary()

    def ternary(self) -> str:
        cond = self.or_()
        if self.at("?"):
            self.take("?")
            a = self.ternary()
            self.take(":")
            b = self.ternary()
            return f"({a} if {cond} else {b})"
        return cond

    def or_(self) -> str:
        left = self.and_()
        while self.at("||"):
            self.take()
            left = f"({left} or {self.and_()})"
        return left

    def and_(self) -> str:
        left = self.compare()
        while self.at("&&"):
            self.take()
            left = f"({left} and {self.compare()})"
        return left

    def compare(self) -> str:
        left = self.additive()
        if self.peek()[1] in ("<", "<=", ">", ">=", "==", "!=") and self.peek()[0] == "op":
            op = self.take()
            left = f"({left} {op} {self.additive()})"
        return left

    def additive(self) -> str:
        left = self.term()
        while self.peek()[1] in ("+", "-") and self.peek()[0] == "op":
            op = self.take()
            left = f"({left} {op} {self.term()})"
        if self.starts_operand():
            raise _Refuse("string concatenation is not supported")
        return left

    def term(self) -> str:
        left = self.unary()
        while self.peek()[1] in ("*", "/", "%") and self.peek()[0] == "op":
            op = self.take()
            left = f"({left} {op} {self.unary()})"
        return left

    def unary(self) -> str:
        if self.at("!"):
            self.take()
            return f"(not {self.unary()})"
        if self.at("-") or self.at("+"):
            op = self.take()
            return f"({op}{self.unary()})"
        return self.power()

    def power(self) -> str:
        base = self.postfix()
        if self.at("^") or self.at("**"):
            self.take()
            return f"({base} ** {self.unary()})"  # right-associative, binds tighter than unary
        return base

    def postfix(self) -> str:
        kind, v = self.peek()
        if kind == "num":
            self.take()
            return v
        if kind == "str":
            self.take()
            return repr(_unquote(v))
        if kind == "op" and v == "(":
            self.take("(")
            inner = self.expr()
            self.take(")")
            return f"({inner})"
        if kind == "op" and v in ("++", "--"):
            raise _Refuse("++/-- inside an expression")
        if kind == "name":
            if v in _FUNCTIONS and self.peek(1)[1] == "(":
                self.take()
                self.take("(")
                args = self.args()
                self.take(")")
                return f"{_FUNCTIONS[v]}({', '.join(args)})"
            if self.peek(1)[1] == "(":
                raise _Refuse(f"function {v}() is not supported")
            if v in _KEYWORDS:
                raise _Refuse(f"{v} inside an expression")
            self.take()
            name = self.var(v)
            if self.at("["):
                self.take("[")
                index = self.expr()
                self.take("]")
                self.arrays.add(name)
                return f"{name}[{index}]"
            if self.at("++") or self.at("--"):
                raise _Refuse("++/-- inside an expression")
            self.scalars.add(name)
            return name
        if kind == "op" and v == "$":
            raise _Refuse("fields are input-related")
        raise _Refuse(f"unexpected {v!r}")

    def starts_operand(self) -> bool:
        kind, v = self.peek()
        return kind in ("num", "str", "name") and v not in ("in",) or (kind == "op" and v == "(")


def _format_call(fmt: str, values: list[str]) -> str:
    """A printf format and its arguments as a python expression built with ``format``."""
    parts: list[str] = []
    pos = 0
    args = iter(values)
    for m in _CONVERSION.finditer(fmt):
        if m.start() > pos:
            parts.append(repr(fmt[pos : m.start()]))
        pos = m.end()
        flags, width, prec, conv = m.groups()
        if conv == "%":
            parts.append(repr("%"))
            continue
        try:
            value = next(args)
        except StopIteration:
            raise _Refuse("printf has fewer arguments than conversions") from None
        align = "<" if "-" in flags else ""
        sign = "+" if "+" in flags else (" " if " " in flags else "")
        zero = "0" if "0" in flags and not align else ""
        precision = f".{prec}" if prec else ""
        if conv in ("d", "i"):
            parts.append(f"format(int({value}), '{align}{sign}{zero}{width}d')")
        elif conv in ("f", "e", "E", "g", "G"):
            spec = f"{align}{sign}{zero}{width}{precision or '.6'}{conv}"
            parts.append(f"format({value}, '{spec}')")
        elif conv == "s":
            parts.append(f"format({value}, '{align}{width}{precision}s')")
        else:
            raise _Refuse(f"printf %{conv} is not supported")
    if pos < len(fmt):
        parts.append(repr(fmt[pos:]))
    if next(args, None) is not None:
        raise _Refuse("printf has more arguments than conversions")
    return " + ".join(parts) if parts else "''"


def translate(program: str) -> str | None:
    """The calculator script for an awk ``BEGIN{...}`` program, or None when it is not one."""
    try:
        return _Translator(program).program()
    except (_Refuse, RecursionError):
        return None
