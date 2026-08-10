import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Example:
    id: str
    input: Any
    expected: Any = None
    tags: list[str] = field(default_factory=list)
    scorer: str | None = None


def load_dataset(path: str | Path) -> list[Example]:
    path = Path(path)
    examples = []
    with path.open() as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_num} — invalid JSON: {e}")
            if "id" not in row or "input" not in row:
                raise ValueError(f"{path}:{line_num} — missing required field 'id' or 'input'")
            examples.append(
                Example(
                    id=row["id"],
                    input=row["input"],
                    expected=row.get("expected"),
                    tags=row.get("tags", []),
                    scorer=row.get("scorer"),
                )
            )

    ids = [e.id for e in examples]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate example ids in {path}: {dupes}")

    return examples

