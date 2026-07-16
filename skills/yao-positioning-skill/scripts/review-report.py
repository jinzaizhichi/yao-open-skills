#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from report_model import load_json, validate_against_schema, validate_report


SCRIPT_INTERFACE = "cli"
SCRIPT_INTERFACE_REASON = "Audits a rendered positioning report bundle for semantic, visual-contract, privacy, and cross-format regressions without writing files."

REQUIRED_FILES = (
    "positioning-report.html",
    "positioning-report-data.json",
    "positioning-report.md",
)
CHART_IDS = (
    "source-grade-chart",
    "claim-confidence-chart",
    "need-map-chart",
    "competitor-role-chart",
    "competitor-map-chart",
    "competitor-radar-chart",
    "mental-position-chart",
    "advantage-heatmap-chart",
    "advantage-radar-chart",
    "option-map-chart",
    "option-radar-chart",
    "validation-chart",
)
MACHINE_ENUMS = {
    "execute",
    "validate_first",
    "insufficient_evidence",
    "recommended",
    "alternative",
    "reserve",
    "eligible",
    "validate",
    "reject",
    "occupied",
    "contested",
    "candidate",
    "unverified",
    "aligned",
    "partial",
    "conflicted",
    "insufficient",
    "direct",
    "indirect",
    "status_quo",
    "inaction",
    "benchmark",
    "expression",
    "product",
    "content",
    "price",
    "channel",
    "sales",
}
LOCAL_PATH_MARKERS = ("/" + "Users" + "/", "\\Users\\", "file:" + "///")
REMOTE_ASSET_MARKERS = ("https:" + "//cdn", "unpkg.com", '<script src="http')


def add_check(checks: list[dict[str, str]], failures: list[str], check_id: str, passed: bool, detail: str) -> None:
    checks.append({"id": check_id, "status": "pass" if passed else "fail", "detail": detail})
    if not passed:
        failures.append(detail)


def markdown_enum_leaks(markdown: str) -> list[str]:
    leaks: list[str] = []
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        matches: list[str] = []
        if line.startswith("|"):
            matches = sorted({cell.strip() for cell in line.strip("|").split("|") if cell.strip() in MACHINE_ENUMS})
        elif line.startswith((">", "-")) and "：" in line:
            value = line.rsplit("：", 1)[-1].strip()
            if value in MACHINE_ENUMS:
                matches = [value]
        if matches:
            leaks.append(f"line {line_number}: {', '.join(matches)}")
    return leaks


def review_bundle(bundle_dir: Path, strict: bool = False) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    failures: list[str] = []
    warnings: list[str] = []
    bundle_dir = bundle_dir.resolve()

    paths = {name: bundle_dir / name for name in REQUIRED_FILES}
    for name, path in paths.items():
        add_check(checks, failures, f"file-{name}", path.is_file(), f"Report bundle contains {name}")
    if failures:
        return {
            "ok": False,
            "bundle_dir": str(bundle_dir),
            "summary": {"check_count": len(checks), "failure_count": len(failures), "warning_count": 0},
            "checks": checks,
            "failures": failures,
            "warnings": warnings,
        }

    html = paths["positioning-report.html"].read_text(encoding="utf-8")
    markdown = paths["positioning-report.md"].read_text(encoding="utf-8")
    data = load_json(paths["positioning-report-data.json"])

    schema_errors = validate_against_schema(data)
    semantic_errors, semantic_warnings = validate_report(data)
    add_check(checks, failures, "data-schema", not schema_errors, "Normalized report data passes Draft 2020-12 structural validation")
    add_check(checks, failures, "data-semantics", not semantic_errors, "Normalized report data passes evidence-aware semantic validation")
    warnings.extend(semantic_warnings)

    summary = data.get("executive_summary", {}) if isinstance(data, dict) else {}
    snapshot = data.get("positioning_snapshot", {}) if isinstance(data, dict) else {}
    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    recommended = str(summary.get("recommended_positioning") or "")
    report_title = str(meta.get("report_title") or "")
    add_check(checks, failures, "parity-recommendation", bool(recommended) and recommended in html and recommended in markdown, "Recommended positioning is identical across HTML, JSON, and Markdown")
    add_check(checks, failures, "parity-title", bool(report_title) and report_title in html and report_title in markdown, "Report title is identical across HTML, JSON, and Markdown")
    snapshot_texts = [
        str(snapshot.get("current_one_liner") or ""),
        str(snapshot.get("current_mental_label") or ""),
        str(snapshot.get("desired_one_liner") or ""),
        str(snapshot.get("desired_mental_label") or ""),
        str(snapshot.get("contrast_sentence") or ""),
    ]
    snapshot_parity = all(value and value in html and value in markdown for value in snapshot_texts)
    add_check(checks, failures, "plain-positioning-parity", snapshot_parity, "Current position, desired position, one-line recommendation, and contrast sentence match across formats")
    plain_markers = all(marker in html for marker in (
        'id="snapshot-current-label"',
        'id="snapshot-desired-label"',
        'id="competitor-shorthand-grid"',
        'id="snapshot-reasons"',
        'id="snapshot-sacrifices"',
    ))
    add_check(checks, failures, "plain-positioning-contract", plain_markers, "HTML begins with the governed plain-language positioning snapshot")

    leaks = markdown_enum_leaks(markdown)
    add_check(checks, failures, "markdown-enum-localization", not leaks, "Markdown contains no user-facing machine enum labels")
    if leaks:
        warnings.extend(f"machine enum leak: {item}" for item in leaks)
    add_check(checks, failures, "markdown-price-semantics", "不适用（未核验）" not in markdown, "Markdown does not label non-applicable prices as unverified")
    add_check(checks, failures, "markdown-punctuation", "—" not in markdown and "–" not in markdown, "Markdown contains no em or en dash punctuation regressions")

    chart_markers_present = all(f'id="{chart_id}"' in html for chart_id in CHART_IDS)
    add_check(checks, failures, "chart-contract", chart_markers_present, f"HTML contains all {len(CHART_IDS)} governed chart containers")
    add_check(checks, failures, "scatter-collision-contract", "spreadScatterPoints" in html and html.count("同分点轻微错位") >= 3, "Scatter plots separate duplicate points and disclose the visual offset")
    add_check(checks, failures, "scatter-label-key-contract", "renderScatterKey" in html and "scatter-key-label" in html and "scatterPointLabel" in html, "Scatter plots use numbered points and complete external label keys")
    add_check(checks, failures, "competitor-radar-five-dimensions", 'name: "心智显著"' in html and "mentalPositionByOccupant" in html, "Competitor radar uses five evidence-backed positioning dimensions")
    add_check(checks, failures, "radar-series-key-contract", "renderSeriesKey" in html and 'legend: { show: false }' in html, "Radar charts expose complete external series keys without paged legends")
    add_check(checks, failures, "deterministic-chart-render", "animation: false" in html, "Charts disable entry animation for deterministic screen and print output")
    add_check(checks, failures, "empty-state-semantics", 'listText(item.disqualifiers, "暂无否决项")' in html and 'value !== undefined && value !== ""' in html, "Empty disqualifiers and populated table cells use distinct copy")

    add_check(checks, failures, "sticky-navigation", 'id="report-topbar"' in html and "setupNavigation" in html and "setupTopbar" in html, "HTML includes governed top sticky navigation")
    add_check(checks, failures, "mobile-table-cue", "setupTableScrollCues" in html and 'data-overflow="true"' in html, "Horizontally overflowing tables expose a state-driven edge cue")
    add_check(checks, failures, "print-a4-contract", "width: 176mm" in html and 'matchMedia("print")' in html and 'addEventListener("beforeprint"' in html, "Print layout uses the governed A4 width and chart resize hooks")
    add_check(checks, failures, "print-complex-chart-width", "#advantage-diagnosis .chart-grid" in html and "#positioning-options .chart-grid" in html, "Complex heatmap and radar sections become full-width in print")

    privacy_ok = all(token not in html and token not in markdown for token in LOCAL_PATH_MARKERS)
    offline_ok = all(token not in html for token in REMOTE_ASSET_MARKERS)
    add_check(checks, failures, "privacy-local-paths", privacy_ok, "Rendered report does not expose local absolute paths")
    add_check(checks, failures, "offline-runtime", offline_ok, "Rendered report does not depend on remote script or CDN assets")
    add_check(checks, failures, "template-placeholders", not any(token in html for token in ("{{REPORT_DATA}}", "{{ECHARTS_JS}}", "{{REPORT_TITLE}}")), "Rendered HTML contains no unresolved template placeholders")

    if strict and warnings:
        failures.extend(f"strict warning: {warning}" for warning in warnings)
    return {
        "ok": not failures,
        "bundle_dir": str(bundle_dir),
        "summary": {
            "check_count": len(checks),
            "pass_count": sum(item["status"] == "pass" for item in checks),
            "failure_count": len(failures),
            "warning_count": len(warnings),
        },
        "checks": checks,
        "failures": failures,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Review a rendered positioning report bundle.")
    parser.add_argument("bundle_dir", type=Path, help="Directory containing the HTML, JSON, and Markdown report bundle")
    parser.add_argument("--strict", action="store_true", help="Treat source freshness and semantic warnings as failures")
    args = parser.parse_args()
    try:
        report = review_bundle(args.bundle_dir, strict=args.strict)
    except (OSError, ValueError) as exc:
        print(f"cannot review report bundle: {exc}", file=sys.stderr)
        return 2
    stream = sys.stdout if report["ok"] else sys.stderr
    print(json.dumps(report, ensure_ascii=False, indent=2), file=stream)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
