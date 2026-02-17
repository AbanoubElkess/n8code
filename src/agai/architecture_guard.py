from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from . import types as agai_types


class ArchitectureGuard:
    def __init__(self, reference_path: str = "config/architecture_reference.json") -> None:
        self.reference_path = Path(reference_path)

    def validate(self) -> dict[str, Any]:
        if not self.reference_path.exists():
            return {"ok": False, "errors": [f"Reference file not found: {self.reference_path}"]}
        spec = json.loads(self.reference_path.read_text(encoding="utf-8"))
        interfaces: dict[str, list[str]] = spec.get("interfaces", {})
        errors: list[str] = []

        for type_name, expected_fields in interfaces.items():
            attr = getattr(agai_types, type_name, None)
            if attr is None:
                errors.append(f"Missing type: {type_name}")
                continue
            if is_dataclass(attr):
                found = [f.name for f in fields(attr)]
                missing = [name for name in expected_fields if name not in found]
                if missing:
                    errors.append(f"{type_name} missing fields: {missing}")
            else:
                # For protocols/classes, validate callable methods.
                missing_methods = [name for name in expected_fields if not hasattr(attr, name)]
                if missing_methods:
                    errors.append(f"{type_name} missing methods: {missing_methods}")

        return {"ok": not errors, "errors": errors}

