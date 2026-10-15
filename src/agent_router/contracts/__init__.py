"""Readers for the structured output blocks agents publish at the end of a report.

Nothing here knows which agent wrote the report: the block's heading, the schema file and the
accepted schema versions are all parameters. Standard library only.
"""

from agent_router.contracts.summary_block import (
    Extraction,
    FieldTable,
    SchemaError,
    SchemaUnavailable,
    Violation,
    check_internal,
    extract_block,
    load_schema,
    read_contract,
    validate,
)

__all__ = [
    "Extraction",
    "FieldTable",
    "SchemaError",
    "SchemaUnavailable",
    "Violation",
    "check_internal",
    "extract_block",
    "load_schema",
    "read_contract",
    "validate",
]
