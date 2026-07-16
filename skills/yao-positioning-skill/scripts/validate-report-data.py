#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from report_model import load_json, validate_against_schema, validate_report


SCRIPT_INTERFACE = "cli"
SCRIPT_INTERFACE_REASON = "Validates report data against the structural schema and evidence-aware semantic gates without writing files."


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate positioning report JSON.")
    parser.add_argument("input", type=Path, help="Path to positioning report JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    try:
        data = load_json(args.input)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        schema_errors = validate_against_schema(data)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    semantic_errors, warnings = validate_report(data)
    errors = schema_errors + semantic_errors

    def count_records(key: str) -> int:
        value = data.get(key)
        return len(value) if isinstance(value, list) else 0

    payload = {
        "valid": not errors and not (args.strict and warnings),
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "sources": count_records("sources"),
            "claims": count_records("claims"),
            "evidence": count_records("evidence"),
            "competitors": count_records("competitors"),
            "positioning_options": count_records("positioning_options"),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    for message in errors:
        print(f"ERROR: {message}", file=sys.stderr)
    if args.strict:
        for message in warnings:
            print(f"WARNING: {message}", file=sys.stderr)
    return 0 if payload["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
