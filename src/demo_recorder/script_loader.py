"""Load and validate JSON demo scripts."""

import json
from pathlib import Path

from pydantic import ValidationError

from .models import DemoScript


def load_script(path: str | Path) -> DemoScript:
    """Load a demo script from a JSON file with clear error messages."""
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Script not found: {path}")

    if not path.suffix == ".json":
        raise ValueError(f"Expected .json file, got: {path.suffix}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path.name}: {e}") from e

    try:
        return DemoScript.model_validate(raw)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " → ".join(str(l) for l in err["loc"])
            errors.append(f"  {loc}: {err['msg']}")
        msg = f"Script validation failed ({path.name}):\n" + "\n".join(errors)
        raise ValueError(msg) from e
