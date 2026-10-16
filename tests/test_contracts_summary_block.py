"""CONTRACT-01..05, TRACE-05: the structured-summary block reader and field-table validator."""

import copy
import json
import re
from pathlib import Path

import pytest

from agent_router import contracts
from agent_router.contracts import (
    SchemaError,
    SchemaUnavailable,
    check_internal,
    extract_block,
    load_schema,
    read_contract,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "fp"
SCHEMA = FIX / "schema" / "summary-schema.json"
HEADING = "## Structured summary (process output)"
VALID = sorted((FIX / "reports" / "valid").glob("*.md"))
EXAMPLES = [p for p in VALID if p.stem.startswith("example-")]
LIVE = [p for p in VALID if p.stem.startswith("live-")]
FENCE = re.compile(r"```json\n(.*?)\n```", re.S)


def _read(path: Path, **kw):
    return read_contract(
        path.read_text(encoding="utf-8"),
        heading=HEADING,
        schema_path=kw.pop("schema_path", SCHEMA),
        accepted_versions=kw.pop("accepted_versions", {1}),
    )


def _block(path: Path) -> dict:
    ext = extract_block(path.read_text(encoding="utf-8"), HEADING)
    assert ext.status == "found"
    return ext.data


def _with_block(text: str, mutate) -> str:
    """The report with its last json fence re-rendered after ``mutate(data)``."""
    matches = list(FENCE.finditer(text))
    m = matches[-1]
    data = json.loads(m.group(1))
    mutate(data)
    return text[: m.start(1)] + json.dumps(data, indent=2) + text[m.end(1) :]


def _fix(data: dict) -> None:
    """Bring a pre-Phase-80 live block up to the current schema (it lacks conclusion.rests_on)."""
    data["conclusion"].setdefault("rests_on", [c["id"] for c in data["chains"][-2:]])


@pytest.fixture(scope="module")
def table():
    return load_schema(SCHEMA)


# -- extraction: one status per fixture ----------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "status"),
    [
        ("absent", "absent"),
        ("multiple", "multiple"),
        ("misplaced", "misplaced"),
        ("invalid_json", "invalid_json"),
    ],
)
def test_extract_status_per_negative_fixture(name, status):
    text = (FIX / "reports" / "negative" / f"{name}.md").read_text(encoding="utf-8")
    ext = extract_block(text, HEADING)
    assert ext.status == status and ext.data is None
    assert _read(FIX / "reports" / "negative" / f"{name}.md")["contract_status"] == status


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.stem)
def test_extract_finds_the_block_in_every_valid_fixture(path):
    ext = extract_block(path.read_text(encoding="utf-8"), HEADING)
    assert ext.status == "found" and ext.data["schema_version"] == 1


def test_unsupported_version_is_read_but_not_validated():
    r = _read(FIX / "reports" / "negative" / "unsupported_version.md")
    assert r["contract_status"] == "unsupported_version"
    assert r["schema_version"] == 2 and r["block"]["schema_version"] == 2
    assert [v["path"] for v in r["violations"]] == ["schema_version"]


def test_accepted_versions_are_a_parameter():
    path = FIX / "reports" / "negative" / "unsupported_version.md"
    assert (
        _read(path, accepted_versions={1, 2})["contract_status"] == "schema_error"
    )  # v2 vs a v1 table
    assert _read(EXAMPLES[0], accepted_versions={2})["contract_status"] == "unsupported_version"


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_shipped_examples_are_valid(path):
    r = _read(path)
    assert r["contract_status"] == "valid", r["violations"]
    assert not [v for v in r["violations"] if v["severity"] == "error"]


@pytest.mark.parametrize("path", LIVE, ids=lambda p: p.stem)
def test_live_reports_predating_conclusion_rests_on_fail_the_current_schema(path):
    """A finding, pinned: these three reports were written before first-principles added the
    required conclusion.rests_on (its own checker rejects them the same way). Brought up to
    date they read as valid."""
    r = _read(path)
    assert r["contract_status"] == "schema_violation"
    assert [v["path"] for v in r["violations"] if v["severity"] == "error"] == [
        "conclusion.rests_on"
    ]
    fixed = read_contract(
        _with_block(path.read_text(encoding="utf-8"), _fix),
        heading=HEADING,
        schema_path=SCHEMA,
        accepted_versions={1},
    )
    assert fixed["contract_status"] == "valid", fixed["violations"]


def test_extract_never_raises_on_odd_input():
    for text in ("", "\n\n", "```json\n", HEADING, HEADING + "\n```json\n[1]\n```\n"):
        ext = extract_block(text, HEADING)
        assert ext.status in {"absent", "invalid_json", "misplaced", "multiple"}
    assert extract_block(HEADING + "\n```json\n[1]\n```\n", HEADING).status == "invalid_json"
    assert extract_block("a\n" + HEADING + '\n```json\n{"a": 1\n', HEADING).status == "invalid_json"


def test_a_heading_inside_a_fence_is_not_a_heading():
    text = f"```\n{HEADING}\n```\n\nbody\n"
    assert extract_block(text, HEADING).status == "absent"


def test_a_second_section_after_the_block_is_misplaced():
    text = (EXAMPLES[0].read_text(encoding="utf-8")).rstrip() + "\n\n## Answer\n\nlate\n"
    assert extract_block(text, HEADING).status == "misplaced"


# -- internal invariants -----------------------------------------------------------------------


def test_dangling_rests_on_is_one_violation_at_the_right_path():
    r = _read(FIX / "reports" / "negative" / "dangling_rests_on.md")
    internal = [v for v in r["violations"] if v["code"].startswith("internal-")]
    assert [(v["path"], v["code"]) for v in internal] == [
        (
            f"chains[0].rests_on[{len(r['block']['chains'][0]['rests_on']) - 1}]",
            "internal-dangling-rests-on",
        )
    ]
    assert "GT-99" in internal[0]["message"]
    assert r["block"]["chains"][0]["rests_on"][-1] == "GT-99"  # recorded, never repaired


def test_internal_violation_leaves_a_readable_block_valid():
    text = _with_block(
        (FIX / "reports" / "negative" / "dangling_rests_on.md").read_text(encoding="utf-8"), _fix
    )
    r = read_contract(text, heading=HEADING, schema_path=SCHEMA, accepted_versions={1})
    assert r["contract_status"] == "valid"
    assert [v["code"] for v in r["violations"] if v["severity"] == "error"] == [
        "internal-dangling-rests-on"
    ]


def test_check_internal_duplicate_ids_and_gate_cleared():
    data = copy.deepcopy(_block(LIVE[0]))
    _fix(data)
    assert check_internal(data) == []
    dup = copy.deepcopy(data)
    dup["chains"].append(dict(dup["chains"][0]))
    assert [v.code for v in check_internal(dup)] == ["internal-duplicate-id"]
    assert check_internal(dup)[0].path == f"chains[{len(dup['chains']) - 1}].id"
    wrong = copy.deepcopy(data)
    wrong["gate"]["cleared"] = not wrong["gate"]["cleared"]
    assert [v.code for v in check_internal(wrong)] == ["internal-gate-cleared"]
    empty = copy.deepcopy(data)
    empty["gate"]["passes"], empty["gate"]["cleared"] = [], True
    assert [v.code for v in check_internal(empty)] == ["internal-gate-cleared"]
    empty["gate"]["cleared"] = False
    assert check_internal(empty) == []


def test_check_internal_conclusion_rests_on_and_question_marks():
    data = copy.deepcopy(_block(LIVE[0]))
    data["conclusion"]["rests_on"] = ["C1", "GT-1?", "C77"]
    assert [v.path for v in check_internal(data)] == ["conclusion.rests_on[2]"]


def test_check_internal_never_raises_on_garbage():
    for junk in (
        None,
        [],
        "x",
        {"chains": "x"},
        {"chains": [None, 3], "gate": {"passes": [1]}},
        {"conclusion": {"rests_on": [1, None]}},
        {"gate": {"passes": [None], "cleared": 1}},
    ):
        check_internal(junk)


# -- the field table and its must-fail controls --------------------------------------------------


def test_valid_block_has_no_errors(table):
    assert [v for v in validate(_block(EXAMPLES[0]), table) if v.severity == "error"] == []


def test_control_enum_value_mutation(table):
    data = _block(LIVE[0])
    _fix(data)
    data["chains"][0]["confidence"] = "CERTAIN"
    (v,) = [x for x in validate(data, table) if x.severity == "error"]
    assert v.path == "chains[0].confidence" and v.code == "enum"


def test_control_missing_required_key(table):
    data = _block(LIVE[0])
    _fix(data)
    del data["dead_ends"]
    (v,) = [x for x in validate(data, table) if x.severity == "error"]
    assert (v.path, v.code) == ("dead_ends", "required")
    nested = _block(LIVE[0])
    _fix(nested)
    del nested["assumptions"][0]["verdict"]
    (v,) = [x for x in validate(nested, table) if x.severity == "error"]
    assert (v.path, v.code) == ("assumptions[0].verdict", "required")


def test_control_id_pattern(table):
    data = _block(LIVE[0])
    _fix(data)
    data["ground_truths"][0]["id"] = "GT-0"
    (v,) = [x for x in validate(data, table) if x.severity == "error"]
    assert (v.path, v.code) == ("ground_truths[0].id", "pattern")


def test_control_type_const_null_and_length(table):
    data = _block(LIVE[0])
    _fix(data)
    data["schema_version"] = 3
    data["ground_truths"][0]["read_at_source"] = "yes"
    data["conclusion"]["confidence"] = None
    data["gate"]["passes"][0]["bands"] = data["gate"]["passes"][0]["bands"][:5]
    got = {(v.path, v.code) for v in validate(data, table) if v.severity == "error"}
    assert got == {
        ("schema_version", "const"),
        ("ground_truths[0].read_at_source", "type"),
        ("conclusion.confidence", "null"),
        ("gate.passes[0].bands", "length"),
    }


def test_nullable_fields_accept_null(table):
    data = _block(EXAMPLES[0])  # a legacy example: techniques, gate and re_entry are null
    assert data["gate"] is None
    assert [v for v in validate(data, table) if v.severity == "error"] == []


def test_unknown_data_fields_are_warnings(table):
    data = _block(LIVE[0])
    _fix(data)
    data["added_later"] = 1
    data["chains"][0]["note"] = "x"
    found = validate(data, table)
    assert {(v.path, v.severity) for v in found if v.code == "unknown"} == {
        ("added_later", "warning"),
        ("chains[0].note", "warning"),
    }
    assert not [v for v in found if v.severity == "error"]
    text = _with_block(LIVE[0].read_text(encoding="utf-8"), lambda d: (_fix(d), d.update(extra=1)))
    r = read_contract(text, heading=HEADING, schema_path=SCHEMA, accepted_versions={1})
    assert r["contract_status"] == "valid"
    assert [v["severity"] for v in r["violations"]] == ["warning"]


def test_validate_never_raises_on_non_objects(table):
    for junk in (None, [], "x", 3):
        assert [v.code for v in validate(junk, table)] == ["type"]
    validate({"assumptions": [None, 1, {"id": []}], "gate": 4, "techniques": []}, table)


def test_control_unknown_schema_keyword_is_a_schema_error(tmp_path):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema["fields"]["run_mode"]["oneOf"] = []
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(schema))
    with pytest.raises(SchemaError, match="oneOf"):
        load_schema(bad)
    deep = json.loads(SCHEMA.read_text(encoding="utf-8"))
    deep["fields"]["assumptions"]["items"]["fields"]["id"]["format"] = "uuid"
    bad.write_text(json.dumps(deep))
    with pytest.raises(SchemaError, match="assumptions\\[\\]\\.id"):
        load_schema(bad)
    r = _read(EXAMPLES[0], schema_path=bad)
    assert r["contract_status"] == "schema_error" and r["block"] is not None


def test_schema_file_problems_are_distinct_statuses(tmp_path):
    with pytest.raises(SchemaUnavailable):
        load_schema(tmp_path / "missing.json")
    assert _read(EXAMPLES[0], schema_path=tmp_path / "missing.json")["contract_status"] == (
        "schema_unavailable"
    )
    junk = tmp_path / "junk.json"
    junk.write_text("{nope")
    assert _read(EXAMPLES[0], schema_path=junk)["contract_status"] == "schema_error"
    unknown_type = json.loads(SCHEMA.read_text(encoding="utf-8"))
    unknown_type["fields"]["run_mode"]["type"] = "float"
    junk.write_text(json.dumps(unknown_type))
    with pytest.raises(SchemaError, match="unknown type"):
        load_schema(junk)


def test_schema_version_mismatch_is_not_a_block_violation(tmp_path):
    other = json.loads(SCHEMA.read_text(encoding="utf-8"))
    other["schema_version"] = 7
    p = tmp_path / "v7.json"
    p.write_text(json.dumps(other))
    assert _read(EXAMPLES[0], schema_path=p)["contract_status"] == "schema_error"


def test_read_contract_never_raises():
    for text in ("", None, 3, "```json\n{}\n```"):
        r = read_contract(text, heading=HEADING, schema_path=SCHEMA, accepted_versions={1})
        assert "contract_status" in r
    r = read_contract(
        f"{HEADING}\n```json\n{{}}\n```\n",
        heading=HEADING,
        schema_path=SCHEMA,
        accepted_versions={1},
    )
    assert r["contract_status"] == "schema_violation"
    assert {v["path"] for v in r["violations"]} >= {"assumptions", "conclusion"}


def test_the_contracts_package_names_no_first_principles_literal():
    """TRACE-05: the reader is parameterised, never agent-specific."""
    pkg = ROOT / "src" / "agent_router" / "contracts"
    files = sorted(pkg.glob("*.py"))
    assert len(files) >= 2
    for f in files:
        text = f.read_text(encoding="utf-8").lower()
        for banned in (
            "first-principles",
            "first_principles",
            "firstprinciples",
            "first principles",
        ):
            assert banned not in text, f"{f.name} names {banned!r}"
    assert contracts.read_contract  # imported above, so the package loads without the literal


# -- optional: a field added after its schema version began -------------------------------------


def _schema_with_optional(tmp_path, flag=True):
    raw = json.loads(SCHEMA.read_text(encoding="utf-8"))
    raw["fields"]["conclusion"]["fields"]["rests_on"]["optional"] = flag
    path = tmp_path / "summary-schema.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


@pytest.mark.parametrize("path", LIVE, ids=lambda p: p.stem)
def test_an_optional_field_may_be_absent_from_an_older_block(tmp_path, path):
    """first-principles' fix for the conclusion.rests_on break: the field is marked optional,
    so a block written before it existed validates as schema_version 1 again."""
    r = read_contract(
        path.read_text(encoding="utf-8"),
        heading=HEADING,
        schema_path=_schema_with_optional(tmp_path),
        accepted_versions={1},
    )
    assert r["contract_status"] == "valid", r["violations"]


def test_optional_does_not_make_a_sibling_optional(tmp_path):
    table = load_schema(_schema_with_optional(tmp_path))
    data = _block(LIVE[0])
    del data["conclusion"]["confidence"]
    (v,) = [x for x in validate(data, table) if x.severity == "error"]
    assert (v.path, v.code) == ("conclusion.confidence", "required")


def test_an_optional_field_present_is_still_validated(tmp_path):
    table = load_schema(_schema_with_optional(tmp_path))
    data = _block(LIVE[0])
    data["conclusion"]["rests_on"] = ["not-an-id"]
    (v,) = [x for x in validate(data, table) if x.severity == "error"]
    assert (v.path, v.code) == ("conclusion.rests_on[0]", "pattern")


def test_optional_must_be_a_boolean(tmp_path):
    with pytest.raises(SchemaError, match="optional"):
        load_schema(_schema_with_optional(tmp_path, flag="yes"))


def test_optional_needs_nullable_and_is_not_allowed_at_the_top_level(tmp_path):
    """Mirrors the publisher's own checker (first-principles 261015-tya)."""
    raw = json.loads(SCHEMA.read_text(encoding="utf-8"))
    rests_on = raw["fields"]["conclusion"]["fields"]["rests_on"]
    rests_on.update(optional=True, nullable=False)
    bad = tmp_path / "not-nullable.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SchemaError, match="nullable"):
        load_schema(bad)
    raw = json.loads(SCHEMA.read_text(encoding="utf-8"))
    raw["fields"]["dead_ends"]["optional"] = True
    raw["fields"]["dead_ends"]["nullable"] = True
    top = tmp_path / "top-level.json"
    top.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SchemaError, match="top-level"):
        load_schema(top)
