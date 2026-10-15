"""Extract, validate and cross-check a structured-summary block in an agent's report.

The block is a heading followed by exactly one fenced ``json`` block, last in the file. Its
contract is a *field table*, a small JSON document of the publisher's own (not JSON Schema):
``required``, ``fields`` (each with ``type``, ``nullable``, ``enum``, ``pattern``, ``const``,
``items``, ``fields``, ``length``, ``minimum``, ``maximum``) and documentation keys. The keywords
are the ones the publisher's own checker implements. A field spec carrying any other keyword
makes :func:`load_schema` raise :class:`SchemaError`: a schema feature this validator does not
understand must not be silently ignored.

Evolution is add-only on the publisher's side, so a data field the table does not know is a
*warning* here, not an error.

Nothing in this module raises on a malformed report. :func:`read_contract` never raises at all.

Status codes of :func:`read_contract` (``contract_status``):

========================  ==================================================================
``valid``                 one well-placed block, accepted version, no schema error
``absent``                no block
``multiple``              more than one block (or the heading more than once)
``misplaced``             one block, but not the last section, or content follows it
``invalid_json``          the fence does not hold a JSON object
``schema_violation``      parsed, accepted version, but the field table rejects it
``unsupported_version``   parsed, ``schema_version`` is not in the accepted set (not validated)
``schema_unavailable``    the schema file is missing or unreadable
``schema_error``          the schema file is not a usable field table (bad JSON, unknown
                          keyword or type, or its version differs from the block's)
========================  ==================================================================

Block-internal invariants (:func:`check_internal`) are *recorded*, never repaired, and do not
change the status: a ``valid`` block whose ``rests_on`` dangles stays ``valid`` and lists the
violation (``code`` beginning ``internal-``). They are listed for a ``schema_violation`` block
too, and never run for an ``unsupported_version`` one. The status answers "can the structure
be read", the violations answer "is what it says self-consistent"; folding the second into the first
would make one dangling id discard a whole otherwise-readable block.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ERROR = "error"
WARNING = "warning"

_DOC_KEYS = frozenset({"source", "null_when", "$comment"})
_KNOWN_FIELD_KEYS = (
    frozenset(
        {
            "type",
            "nullable",
            "const",
            "enum",
            "pattern",
            "items",
            "fields",
            "length",
            "minimum",
            "maximum",
        }
    )
    | _DOC_KEYS
)
_TYPES: dict[str, type] = {
    "integer": int,
    "string": str,
    "boolean": bool,
    "array": list,
    "object": dict,
}


class SchemaError(Exception):
    """The schema file is not a field table this validator can apply."""


class SchemaUnavailable(SchemaError):
    """The schema file cannot be read at all."""


@dataclass(frozen=True)
class Violation:
    path: str
    message: str
    severity: str = ERROR
    code: str = "schema"

    def as_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "message": self.message,
            "severity": self.severity,
            "code": self.code,
        }


@dataclass(frozen=True)
class FieldTable:
    path: str
    schema_version: Any
    required: tuple[str, ...]
    fields: dict[str, dict[str, Any]]
    raw: dict[str, Any] = field(repr=False, default_factory=dict)


@dataclass(frozen=True)
class Extraction:
    status: str  # found | absent | multiple | misplaced | invalid_json
    data: dict[str, Any] | None = None
    detail: str = ""
    line: int | None = None  # 1-based line of the block's opening fence


# --- extraction -------------------------------------------------------------------------------

_FENCE_OPEN = re.compile(r"^ {0,3}(?P<ticks>`{3,})(?P<info>.*)$")
_FENCE_CLOSE = re.compile(r"^ {0,3}(?P<ticks>`{3,})\s*$")
_H2 = re.compile(r"^## ")


def _fences(lines: list[str]) -> tuple[list[bool], list[tuple[int, int, str, str, bool]]]:
    """Per line: inside a fenced code block? And each fence as (start, end, info, body, closed).
    A fence of three or more backticks closes on a line of at least as many and nothing else;
    an unterminated fence runs to the end of the text."""
    inside = [False] * len(lines)
    found: list[tuple[int, int, str, str, bool]] = []
    start = open_len = None
    for i, line in enumerate(lines):
        if open_len is None:
            m = _FENCE_OPEN.match(line)
            if m:
                open_len, start, inside[i] = len(m.group("ticks")), i, True
            continue
        inside[i] = True
        m = _FENCE_CLOSE.match(line)
        if m and len(m.group("ticks")) >= open_len:
            info = _FENCE_OPEN.match(lines[start]).group("info").strip()  # type: ignore[index, union-attr]
            found.append((start, i, info, "\n".join(lines[start + 1 : i]), True))  # type: ignore[operator]
            open_len = start = None
    if open_len is not None:
        info = _FENCE_OPEN.match(lines[start]).group("info").strip()  # type: ignore[index, union-attr]
        found.append((start, len(lines) - 1, info, "\n".join(lines[start + 1 :]), False))  # type: ignore[operator]
    return inside, found


def extract_block(text: str, heading: str, *, fence: str = "json") -> Extraction:
    """Find the one summary block under ``heading``. Never raises."""
    try:
        return _extract(str(text), heading, fence)
    except Exception as exc:  # defensive: extraction must never take a hook down
        return Extraction("invalid_json", detail=f"extraction failed: {exc}")


def _extract(text: str, heading: str, fence: str) -> Extraction:
    lines = text.split("\n")
    inside, fences = _fences(lines)
    heads = [i for i, ln in enumerate(lines) if not inside[i] and ln.strip() == heading]
    first_head = heads[0] if heads else None
    cands = [
        f
        for f in fences
        if f[2] == fence
        and ((first_head is not None and f[0] > first_head) or '"schema_version"' in f[3])
    ]
    if not cands:
        return Extraction("absent", detail="no summary block")
    if len(cands) > 1:
        return Extraction("multiple", detail=f"{len(cands)} summary blocks", line=cands[1][0] + 1)
    if len(heads) > 1:
        return Extraction("multiple", detail=f"heading appears {len(heads)} times")
    start, end, _info, body, closed = cands[0]
    if first_head is None or start < first_head:
        return Extraction("misplaced", detail="block is not under the heading", line=start + 1)
    if any(inside[i] is False and _H2.match(lines[i]) for i in range(end + 1, len(lines))):
        return Extraction("misplaced", detail="a section follows the block", line=start + 1)
    if any(ln.strip() for ln in lines[end + 1 :]):
        return Extraction("misplaced", detail="content follows the block", line=start + 1)
    # the block section is the last "## " section: nothing but this heading opens one after it
    for i in range(first_head + 1, start):
        if not inside[i] and _H2.match(lines[i]):
            return Extraction(
                "misplaced", detail="another section opens after the heading", line=start + 1
            )
    try:
        data = json.loads(body)
    except ValueError as exc:
        return Extraction("invalid_json", detail=str(exc), line=start + 1)
    if not closed:
        return Extraction("invalid_json", detail="the fence is never closed", line=start + 1)
    if not isinstance(data, dict):
        return Extraction("invalid_json", detail="the block is not a JSON object", line=start + 1)
    return Extraction("found", data=data, line=start + 1)


# --- the field table --------------------------------------------------------------------------


def _check_spec(spec: Any, path: str) -> None:
    if not isinstance(spec, dict):
        raise SchemaError(f"{path}: field spec must be a JSON object")
    unknown = set(spec) - _KNOWN_FIELD_KEYS
    if unknown:
        raise SchemaError(f"{path}: unknown schema keyword(s) {sorted(unknown)!r}")
    if "type" in spec and spec["type"] not in _TYPES:
        raise SchemaError(f"{path}: unknown type {spec['type']!r}")
    if "pattern" in spec:
        try:
            re.compile(spec["pattern"])
        except (re.error, TypeError) as exc:
            raise SchemaError(f"{path}: bad pattern: {exc}") from exc
    if "items" in spec:
        _check_spec(spec["items"], f"{path}[]")
    if "fields" in spec:
        if not isinstance(spec["fields"], dict):
            raise SchemaError(f"{path}.fields must be a JSON object")
        for key, sub in spec["fields"].items():
            _check_spec(sub, f"{path}.{key}")


def load_schema(path: str | Path) -> FieldTable:
    """Read a field table. Raises :class:`SchemaUnavailable` when unreadable and
    :class:`SchemaError` when it is not JSON, not an object, or uses a keyword or type this
    validator does not implement."""
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise SchemaUnavailable(f"cannot read schema file {p}: {exc}") from exc
    try:
        schema = json.loads(raw)
    except ValueError as exc:
        raise SchemaError(f"schema file {p} is not valid JSON: {exc}") from exc
    if not isinstance(schema, dict):
        raise SchemaError(f"schema file {p}: top level must be a JSON object")
    fields = schema.get("fields", {})
    if not isinstance(fields, dict):
        raise SchemaError(f"schema file {p}: 'fields' must be a JSON object")
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(k, str) for k in required):
        raise SchemaError(f"schema file {p}: 'required' must be a list of strings")
    for key, spec in fields.items():
        _check_spec(spec, key)
    return FieldTable(str(p), schema.get("schema_version"), tuple(required), fields, schema)


def _type_ok(value: Any, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _validate_value(value: Any, spec: dict[str, Any], path: str, out: list[Violation]) -> None:
    if value is None:
        if not spec.get("nullable", False):
            out.append(Violation(path, "null is not allowed", code="null"))
        return
    t = spec.get("type")
    if t is not None and not _type_ok(value, t):
        out.append(Violation(path, f"expected type {t}, got {type(value).__name__}", code="type"))
        return
    if "const" in spec and value != spec["const"]:
        out.append(Violation(path, f"expected {spec['const']!r}, got {value!r}", code="const"))
    if "enum" in spec and value not in spec["enum"]:
        out.append(Violation(path, f"{value!r} is not one of {spec['enum']}", code="enum"))
    if "pattern" in spec and isinstance(value, str) and not re.fullmatch(spec["pattern"], value):
        out.append(
            Violation(path, f"{value!r} does not match pattern {spec['pattern']!r}", code="pattern")
        )
    if "length" in spec and hasattr(value, "__len__") and len(value) != spec["length"]:
        out.append(
            Violation(path, f"expected length {spec['length']}, got {len(value)}", code="length")
        )
    if "minimum" in spec and _is_number(value) and value < spec["minimum"]:
        out.append(Violation(path, f"{value} is below minimum {spec['minimum']}", code="range"))
    if "maximum" in spec and _is_number(value) and value > spec["maximum"]:
        out.append(Violation(path, f"{value} is above maximum {spec['maximum']}", code="range"))
    if t == "array" and "items" in spec and isinstance(value, list):
        for i, item in enumerate(value):
            _validate_value(item, spec["items"], f"{path}[{i}]", out)
    if t == "object" and "fields" in spec and isinstance(value, dict):
        sub = spec["fields"]
        for key in value:
            if key not in sub:
                out.append(
                    Violation(f"{path}.{key}", "unknown field", severity=WARNING, code="unknown")
                )
        for key, subspec in sub.items():
            if key not in value:
                out.append(Violation(f"{path}.{key}", "missing required key", code="required"))
            else:
                _validate_value(value[key], subspec, f"{path}.{key}", out)


def validate(data: Any, schema: FieldTable) -> list[Violation]:
    """Check ``data`` against the field table: required keys, types, nullability, enums, id
    patterns, nested items and fields, constants, lengths and ranges. Never raises."""
    out: list[Violation] = []
    if not isinstance(data, dict):
        return [Violation("", "the block is not a JSON object", code="type")]
    try:
        for key in schema.required:
            if key not in data:
                out.append(Violation(key, "missing required key", code="required"))
        for key in data:
            if key not in schema.fields:
                out.append(Violation(key, "unknown field", severity=WARNING, code="unknown"))
        for key, spec in schema.fields.items():
            if key in data:
                _validate_value(data[key], spec, key, out)
    except Exception as exc:  # defensive: a validator bug must read as a finding, not a crash
        out.append(Violation("", f"validator failed: {exc}", code="validator"))
    return out


# --- block-internal invariants ----------------------------------------------------------------


def _items(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    v = data.get(key)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _ref_ids(refs: Any) -> list[tuple[int, str]]:
    return (
        [(i, r) for i, r in enumerate(refs) if isinstance(r, str)] if isinstance(refs, list) else []
    )


def check_internal(data: Any) -> list[Violation]:
    """Invariants that need no prose: ids unique per collection, every ``rests_on`` id resolves
    inside the block, ``gate.cleared`` follows the last pass. Records; never repairs; never
    raises."""
    if not isinstance(data, dict):
        return []
    out: list[Violation] = []
    try:
        known: set[str] = set()
        for key in ("assumptions", "ground_truths", "chains"):
            seen: set[str] = set()
            for i, item in enumerate(_items(data, key)):
                ident = item.get("id")
                if not isinstance(ident, str):
                    continue
                if ident in seen:
                    out.append(
                        Violation(
                            f"{key}[{i}].id",
                            f"duplicate id {ident!r}",
                            code="internal-duplicate-id",
                        )
                    )
                seen.add(ident)
                if key != "assumptions":
                    known.add(ident)

        def resolve(refs: Any, base: str) -> None:
            for i, ref in _ref_ids(refs):
                if ref.rstrip("?") not in known:
                    out.append(
                        Violation(
                            f"{base}[{i}]",
                            f"{ref!r} names no ground truth or chain in the block",
                            code="internal-dangling-rests-on",
                        )
                    )

        for i, chain in enumerate(_items(data, "chains")):
            resolve(chain.get("rests_on"), f"chains[{i}].rests_on")
        concl = data.get("conclusion")
        if isinstance(concl, dict):
            resolve(concl.get("rests_on"), "conclusion.rests_on")
        gate = data.get("gate")
        if isinstance(gate, dict) and isinstance(gate.get("passes"), list):
            passes = gate["passes"]
            if passes and isinstance(passes[-1], dict):
                last = passes[-1]
                want = (
                    last.get("gate_cleared") is True and last.get("hand_wavy_cap_cleared") is True
                )
                if gate.get("cleared") is not want:
                    out.append(
                        Violation(
                            "gate.cleared",
                            f"gate.cleared is {gate.get('cleared')!r} but the last pass "
                            f"implies {want!r}",
                            code="internal-gate-cleared",
                        )
                    )
            elif not passes and gate.get("cleared") is True:
                out.append(
                    Violation(
                        "gate.cleared",
                        "gate.cleared is true but there is no pass",
                        code="internal-gate-cleared",
                    )
                )
    except Exception as exc:  # defensive
        out.append(Violation("", f"internal check failed: {exc}", code="internal-check"))
    return out


# --- the one-call reader ----------------------------------------------------------------------


def read_contract(
    text: str,
    *,
    heading: str,
    schema_path: str | Path,
    accepted_versions: set[int] | frozenset[int] | tuple[int, ...],
    fence: str = "json",
) -> dict[str, Any]:
    """Read the block in ``text`` and say how far it can be trusted. Never raises.

    Returns ``contract_status`` (see the module docstring), ``violations`` (dicts with ``path``,
    ``message``, ``severity``, ``code``: schema findings and, for a ``valid`` block, internal
    ones), ``schema_version`` (the block's own, when it has one), ``schema_path`` and ``block``
    (the parsed data, or None). ``unsupported_version`` still carries the parsed block."""
    result: dict[str, Any] = {
        "contract_status": "schema_error",
        "violations": [],
        "schema_version": None,
        "schema_path": str(schema_path),
        "block": None,
    }

    def done(status: str, violations: list[Violation] | None = None) -> dict[str, Any]:
        result["contract_status"] = status
        result["violations"] = [v.as_dict() for v in violations or []]
        return result

    try:
        ext = extract_block(text, heading, fence=fence)
        if ext.status != "found":
            return done(ext.status, [Violation("", ext.detail, code=ext.status)])
        data = ext.data
        result["block"] = data
        version = data.get("schema_version") if data else None
        result["schema_version"] = version
        if _is_int(version) and version not in set(accepted_versions):
            return done(
                "unsupported_version",
                [Violation("schema_version", f"version {version} is not accepted", code="version")],
            )
        try:
            table = load_schema(schema_path)
        except SchemaUnavailable as exc:
            return done("schema_unavailable", [Violation("", str(exc), code="schema-file")])
        except SchemaError as exc:
            return done("schema_error", [Violation("", str(exc), code="schema-file")])
        if _is_int(version) and table.schema_version != version:
            return done(
                "schema_error",
                [
                    Violation(
                        "schema_version",
                        f"schema file is version {table.schema_version!r}, block is {version}",
                        code="schema-file",
                    )
                ],
            )
        found = validate(data, table) + check_internal(data)
        if any(v.severity == ERROR and not v.code.startswith("internal-") for v in found):
            return done("schema_violation", found)
        return done("valid", found)
    except Exception as exc:  # defensive: the reader never raises
        return done("schema_error", [Violation("", f"reader failed: {exc}", code="reader")])


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)
