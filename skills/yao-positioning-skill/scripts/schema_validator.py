#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Provides dependency-free structural validation for the report validator and renderer."

DEFAULT_SCHEMA = Path(__file__).resolve().parents[1] / "templates" / "report-data.schema.json"


def _json_equal(left: Any, right: Any) -> bool:
    return type(left) is type(right) and left == right


def _schema_type_matches(value: Any, expected: str) -> bool:
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    return expected in checks and checks[expected](value)


def _resolve_local_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"unsupported non-local schema reference: {ref}")
    current: Any = root
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f"schema reference does not exist: {ref}")
        current = current[token]
    if not isinstance(current, dict):
        raise ValueError(f"schema reference is not an object: {ref}")
    return current


def _schema_path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    return key if parent == "$" else f"{parent}.{key}"


def _validate_schema_value(
    value: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    if "$ref" in schema:
        _validate_schema_value(value, _resolve_local_ref(root, str(schema["$ref"])), root, path, errors)
        schema = {key: item for key, item in schema.items() if key != "$ref"}

    expected_types = schema.get("type")
    if expected_types is not None:
        candidates = [expected_types] if isinstance(expected_types, str) else expected_types
        if not isinstance(candidates, list) or not all(isinstance(item, str) for item in candidates):
            raise ValueError(f"invalid type declaration in schema at {path}")
        if not any(_schema_type_matches(value, item) for item in candidates):
            errors.append(f"{path} must match schema type: {' or '.join(candidates)}")
            return

    if "enum" in schema and not any(_json_equal(value, candidate) for candidate in schema["enum"]):
        errors.append(f"{path} must be one of the schema enum values")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{_schema_path(path, key)} is required by the schema")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{_schema_path(path, key)} additional property is not allowed by the schema")
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                _validate_schema_value(value[key], child_schema, root, _schema_path(path, key), errors)

    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            errors.append(f"{path} must contain at least {schema['minItems']} items")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            errors.append(f"{path} must contain at most {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            canonical = [json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in value]
            if len(canonical) != len(set(canonical)):
                errors.append(f"{path} must contain unique items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema_value(item, item_schema, root, _schema_path(path, index), errors)

    if isinstance(value, str) and isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
        errors.append(f"{path} must contain at least {schema['minLength']} characters")
    if isinstance(value, str) and isinstance(schema.get("pattern"), str) and re.fullmatch(schema["pattern"], value) is None:
        errors.append(f"{path} does not match the schema pattern")

    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        if isinstance(schema.get("minimum"), (int, float)) and value < schema["minimum"]:
            errors.append(f"{path} must be at least {schema['minimum']}")
        if isinstance(schema.get("maximum"), (int, float)) and value > schema["maximum"]:
            errors.append(f"{path} must be at most {schema['maximum']}")


def validate_against_schema(
    data: dict[str, Any],
    schema_path: Path = DEFAULT_SCHEMA,
) -> list[str]:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"report schema does not exist: {schema_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid report schema at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(schema, dict):
        raise ValueError("report schema root must be a JSON object")
    errors: list[str] = []
    _validate_schema_value(data, schema, schema, "$", errors)
    return errors
