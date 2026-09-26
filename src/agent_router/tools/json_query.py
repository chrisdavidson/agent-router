"""JMESPath query over a workspace JSON file or JSON text (jmespath.py, MIT)."""

import json
from pathlib import Path

import jmespath
from jmespath.exceptions import JMESPathError

from agent_router.tools._paths import one_source, read_text_inside


def query(expression: str, path: str | None = None, text: str | None = None, *, root: Path) -> str:
    """Run ``expression`` against JSON from ``path`` (inside ``root``) or ``text``.

    Returns the result as pretty-printed JSON. Raises ``ValueError`` on bad input.
    """
    one_source(path, text, "text")
    raw = read_text_inside(root, path) if path is not None else text
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
    try:
        result = jmespath.search(expression, data)
    except JMESPathError as e:
        raise ValueError(f"invalid JMESPath expression: {e}") from e
    return json.dumps(result, indent=2, ensure_ascii=False)
