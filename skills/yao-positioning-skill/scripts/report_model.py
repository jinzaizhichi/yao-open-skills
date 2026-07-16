#!/usr/bin/env python3
from __future__ import annotations

SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Imported by the report validator and renderer for shared report semantics."

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from schema_validator import validate_against_schema


TOP_LEVEL_ARRAYS = (
    "sources",
    "claims",
    "evidence",
    "user_needs",
    "competitors",
    "mental_positions",
    "advantages",
    "opportunities",
    "positioning_options",
    "strategic_actions",
    "validation_plan",
)
ALLOWED_CLAIM_TYPES = {"fact", "self_report", "inference", "hypothesis", "recommendation"}
ALLOWED_CONFIDENCE = {"high", "medium", "low", "insufficient"}
ALLOWED_COMPETITOR_TYPES = {"direct", "indirect", "status_quo", "inaction", "benchmark"}
ALLOWED_SOURCE_GRADES = {"A", "B", "C", "D", "E"}
ALLOWED_ADVANTAGE_STATUS = {"eligible", "validate", "reject"}
ALLOWED_OPTION_STATUS = {"recommended", "alternative", "reserve", "rejected"}
ALLOWED_RECOMMENDATION_STATUS = {"execute", "validate_first", "insufficient_evidence"}
ALLOWED_FRESHNESS_STATUS = {"current", "stale", "not_applicable", "unknown"}
ALLOWED_SOURCE_PERSPECTIVE = {"official", "user", "independent", "internal", "mixed"}
ALLOWED_MARKET_FIT = {"aligned", "partial", "mismatch", "unknown"}
ALLOWED_MENTAL_POSITION_STATUS = {"occupied", "contested", "candidate", "unverified"}
ALLOWED_ALIGNMENT_STATUS = {"aligned", "partial", "conflicted", "insufficient"}
ALLOWED_ACTION_AREAS = {"expression", "product", "content", "price", "channel", "sales"}
ALLOWED_ACTION_PRIORITY = {"high", "medium", "low"}
ALLOWED_THRESHOLD_UNITS = {"rate", "score_5"}
ID_FIELDS = {
    "sources": "source_id",
    "claims": "claim_id",
    "evidence": "evidence_id",
    "user_needs": "need_id",
    "competitors": "competitor_id",
    "mental_positions": "mental_position_id",
    "advantages": "advantage_id",
    "opportunities": "opportunity_id",
    "positioning_options": "option_id",
    "strategic_actions": "action_id",
    "validation_plan": "experiment_id",
}
PORTABLE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"input file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("report root must be a JSON object")
    return data


def _require_text(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty string")


def _require_id(value: Any, path: str, errors: list[str]) -> None:
    _require_text(value, path, errors)
    if isinstance(value, str) and not PORTABLE_ID.fullmatch(value):
        errors.append(f"{path} must be a portable report ID using letters, numbers, underscore, or hyphen")


def _parse_iso_date(value: Any, path: str, errors: list[str]) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        errors.append(f"{path} must be an ISO date in YYYY-MM-DD format")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{path} must be a valid calendar date")
        return None


def _require_object(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object")


def _require_array(value: Any, path: str, errors: list[str], *, nonempty: bool = False) -> None:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
    elif nonempty and not value:
        errors.append(f"{path} must not be empty")


def _require_string_array(value: Any, path: str, errors: list[str], *, nonempty: bool = False) -> bool:
    _require_array(value, path, errors, nonempty=nonempty)
    if not isinstance(value, list):
        return False
    for index, item in enumerate(value):
        _require_text(item, f"{path}[{index}]", errors)
    if len(value) != len(set(item for item in value if isinstance(item, str))):
        errors.append(f"{path} must not contain duplicate IDs or values")
    return True


def _check_references(
    value: Any,
    path: str,
    known_ids: set[str],
    errors: list[str],
    *,
    nonempty: bool = False,
) -> None:
    if not _require_string_array(value, path, errors, nonempty=nonempty):
        return
    for item in value:
        if item not in known_ids:
            errors.append(f"{path} references unknown ID {item}")


def _check_score(value: Any, path: str, errors: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 5:
        errors.append(f"{path} must be between 1 and 5")


def _index_records(
    data: dict[str, Any],
    collection: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    id_field = ID_FIELDS[collection]
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(data.get(collection, [])):
        path = f"{collection}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        value = item.get(id_field)
        _require_id(value, f"{path}.{id_field}", errors)
        if not isinstance(value, str) or not value:
            continue
        if value in result:
            errors.append(f"{path}.{id_field} duplicates {value}")
        result[value] = item
    return result


def validate_report(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for key in ("meta", "subject", "research_scope", "positioning_snapshot", "executive_summary"):
        _require_object(data.get(key), key, errors)
    for key in TOP_LEVEL_ARRAYS:
        _require_array(data.get(key), key, errors, nonempty=key != "opportunities")
    if errors:
        return errors, warnings

    meta = data["meta"]
    subject = data["subject"]
    scope = data["research_scope"]
    snapshot = data["positioning_snapshot"]
    summary = data["executive_summary"]
    for path, value in (
        ("meta.report_title", meta.get("report_title")),
        ("meta.generated_at", meta.get("generated_at")),
        ("meta.locale", meta.get("locale")),
        ("meta.research_mode", meta.get("research_mode")),
        ("meta.status", meta.get("status")),
        ("meta.version", meta.get("version")),
        ("subject.name", subject.get("name")),
        ("subject.type", subject.get("type")),
        ("subject.identity", subject.get("identity")),
        ("subject.stage", subject.get("stage")),
        ("subject.objective", subject.get("objective")),
        ("research_scope.region", scope.get("region")),
        ("research_scope.time_window", scope.get("time_window")),
        ("research_scope.notes", scope.get("notes")),
        ("positioning_snapshot.current_category", snapshot.get("current_category")),
        ("positioning_snapshot.current_one_liner", snapshot.get("current_one_liner")),
        ("positioning_snapshot.current_mental_label", snapshot.get("current_mental_label")),
        ("positioning_snapshot.current_problem", snapshot.get("current_problem")),
        ("positioning_snapshot.primary_competitor_id", snapshot.get("primary_competitor_id")),
        ("positioning_snapshot.desired_category", snapshot.get("desired_category")),
        ("positioning_snapshot.desired_mental_label", snapshot.get("desired_mental_label")),
        ("positioning_snapshot.desired_one_liner", snapshot.get("desired_one_liner")),
        ("positioning_snapshot.contrast_sentence", snapshot.get("contrast_sentence")),
        ("executive_summary.recommended_positioning", summary.get("recommended_positioning")),
        ("executive_summary.category", summary.get("category")),
        ("executive_summary.differentiation_label", summary.get("differentiation_label")),
        ("executive_summary.core_value", summary.get("core_value")),
        ("executive_summary.unique_mechanism", summary.get("unique_mechanism")),
        ("executive_summary.mindshare_keyword", summary.get("mindshare_keyword")),
        ("executive_summary.recommendation_status", summary.get("recommendation_status")),
        ("executive_summary.rationale", summary.get("rationale")),
        ("executive_summary.counterevidence_condition", summary.get("counterevidence_condition")),
        ("executive_summary.next_action", summary.get("next_action")),
    ):
        _require_text(value, path, errors)
    if meta.get("research_mode") not in {"local", "standard", "deep"}:
        errors.append("meta.research_mode must be local, standard, or deep")
    if subject.get("type") not in {"personal_ip", "course", "product", "service", "brand", "company"}:
        errors.append("subject.type is invalid")
    if summary.get("recommendation_status") not in ALLOWED_RECOMMENDATION_STATUS:
        errors.append("executive_summary.recommendation_status is invalid")
    report_date = _parse_iso_date(meta.get("generated_at"), "meta.generated_at", errors)
    planned = scope.get("planned_competitor_count")
    if isinstance(planned, bool) or not isinstance(planned, int) or planned <= 0:
        errors.append("research_scope.planned_competitor_count must be a positive integer")
    for field in ("target_users", "constraints", "assets"):
        _require_string_array(subject.get(field), f"subject.{field}", errors, nonempty=field == "target_users")

    indexes = {name: _index_records(data, name, errors) for name in TOP_LEVEL_ARRAYS}
    if errors:
        return errors, warnings
    evidence_ids = set(indexes["evidence"])
    source_ids = set(indexes["sources"])
    claim_ids = set(indexes["claims"])
    need_ids = set(indexes["user_needs"])

    for field in ("reason_to_believe", "sacrifice"):
        _require_string_array(snapshot.get(field), f"positioning_snapshot.{field}", errors, nonempty=True)
        values = snapshot.get(field)
        if isinstance(values, list) and len(values) > 3:
            errors.append(f"positioning_snapshot.{field} must contain at most 3 items")
    _check_references(
        snapshot.get("evidence_ids"),
        "positioning_snapshot.evidence_ids",
        evidence_ids,
        errors,
        nonempty=True,
    )
    if snapshot.get("primary_competitor_id") not in indexes["competitors"]:
        errors.append("positioning_snapshot.primary_competitor_id references an unknown competitor")
    for snapshot_field, summary_field in (
        ("desired_category", "category"),
        ("desired_mental_label", "mindshare_keyword"),
        ("desired_one_liner", "recommended_positioning"),
    ):
        if snapshot.get(snapshot_field) != summary.get(summary_field):
            errors.append(
                f"positioning_snapshot.{snapshot_field} must match executive_summary.{summary_field}"
            )
    expression_budgets = (
        ("current_one_liner", 60),
        ("current_mental_label", 12),
        ("current_problem", 80),
        ("desired_mental_label", 12),
        ("desired_one_liner", 80),
        ("contrast_sentence", 50),
    )
    for field, limit in expression_budgets:
        value = snapshot.get(field)
        if isinstance(value, str) and len(value) > limit:
            warnings.append(
                f"positioning_snapshot.{field} exceeds the plain-language budget of {limit} characters"
            )

    _check_references(summary.get("evidence_ids"), "executive_summary.evidence_ids", evidence_ids, errors, nonempty=True)

    for index, source in enumerate(data["sources"]):
        path = f"sources[{index}]"
        for field in (
            "title", "publisher", "url_or_file", "source_type", "perspective", "grade", "accessed_at",
            "directness", "freshness_status", "origin_group", "intended_use", "notes",
        ):
            _require_text(source.get(field), f"{path}.{field}", errors)
        if source.get("grade") not in ALLOWED_SOURCE_GRADES:
            errors.append(f"{path}.grade must be one of A, B, C, D, E")
        if source.get("perspective") not in ALLOWED_SOURCE_PERSPECTIVE:
            errors.append(f"{path}.perspective is invalid")
        if "published_at" not in source:
            errors.append(f"{path}.published_at must be present; use null when unknown")
        elif source.get("published_at") is not None:
            _require_text(source.get("published_at"), f"{path}.published_at", errors)
        if source.get("freshness_status") not in ALLOWED_FRESHNESS_STATUS:
            errors.append(f"{path}.freshness_status is invalid")
        accessed_date = _parse_iso_date(source.get("accessed_at"), f"{path}.accessed_at", errors)
        published_date = None
        if source.get("published_at") is not None:
            published_date = _parse_iso_date(source.get("published_at"), f"{path}.published_at", errors)
        if published_date and accessed_date and published_date > accessed_date:
            errors.append(f"{path}.published_at must not be after accessed_at")
        if accessed_date and report_date and accessed_date > report_date:
            errors.append(f"{path}.accessed_at must not be after meta.generated_at")
        if source.get("freshness_status") == "current" and source.get("published_at") is None:
            warnings.append(f"{path} is current but published_at is unknown; verify or downgrade freshness")
        if source.get("freshness_status") in {"stale", "unknown"}:
            warnings.append(f"{path} freshness is {source.get('freshness_status')}; current claims must be downgraded")

    for index, claim in enumerate(data["claims"]):
        path = f"claims[{index}]"
        for field in ("claim_type", "claim_text", "reasoning", "confidence", "falsification_condition"):
            _require_text(claim.get(field), f"{path}.{field}", errors)
        if claim.get("claim_type") not in ALLOWED_CLAIM_TYPES:
            errors.append(f"{path}.claim_type is invalid")
        if claim.get("confidence") not in ALLOWED_CONFIDENCE:
            errors.append(f"{path}.confidence is invalid")
        requires_evidence = claim.get("claim_type") in {"fact", "inference", "recommendation"}
        _check_references(claim.get("evidence_ids"), f"{path}.evidence_ids", evidence_ids, errors, nonempty=requires_evidence)
        _require_string_array(claim.get("counterevidence"), f"{path}.counterevidence", errors)
        _require_string_array(claim.get("report_sections"), f"{path}.report_sections", errors, nonempty=True)

    for index, evidence in enumerate(data["evidence"]):
        path = f"evidence[{index}]"
        for field in ("summary", "market_fit_notes", "notes"):
            _require_text(evidence.get(field), f"{path}.{field}", errors)
        if evidence.get("market_fit") not in ALLOWED_MARKET_FIT:
            errors.append(f"{path}.market_fit is invalid")
        if evidence.get("source_id") not in source_ids:
            errors.append(f"{path}.source_id references unknown source {evidence.get('source_id')}")
        _check_references(evidence.get("claim_ids"), f"{path}.claim_ids", claim_ids, errors, nonempty=True)
        for field in ("relevance", "directness", "freshness"):
            _check_score(evidence.get(field), f"{path}.{field}", errors)
        for field in ("independent", "conflict"):
            if not isinstance(evidence.get(field), bool):
                errors.append(f"{path}.{field} must be boolean")

    evidence_by_id = indexes["evidence"]
    claims_by_id = indexes["claims"]
    for index, claim in enumerate(data["claims"]):
        for evidence_id in claim.get("evidence_ids", []):
            evidence = evidence_by_id.get(evidence_id, {})
            if claim.get("claim_id") not in evidence.get("claim_ids", []):
                errors.append(
                    f"claims[{index}].evidence_ids item {evidence_id} does not link back through evidence.claim_ids"
                )
    for index, evidence in enumerate(data["evidence"]):
        for claim_id in evidence.get("claim_ids", []):
            claim = claims_by_id.get(claim_id, {})
            if evidence.get("evidence_id") not in claim.get("evidence_ids", []):
                errors.append(
                    f"evidence[{index}].claim_ids item {claim_id} does not link back through claims.evidence_ids"
                )

    for index, claim in enumerate(data["claims"]):
        if claim.get("claim_type") not in {"fact", "inference", "recommendation"}:
            critical = False
        else:
            critical = True
        grades = {
            indexes["sources"].get(evidence_by_id.get(evidence_id, {}).get("source_id"), {}).get("grade")
            for evidence_id in claim.get("evidence_ids", [])
        }
        grades.discard(None)
        claim_evidence = [
            evidence_by_id[evidence_id]
            for evidence_id in claim.get("evidence_ids", [])
            if evidence_id in evidence_by_id
        ]
        if critical and grades and grades <= {"E"}:
            errors.append(f"claims[{index}] cannot be supported only by grade E sources")
        if critical and claim_evidence and not any((item.get("relevance") or 0) >= 4 for item in claim_evidence):
            warnings.append(f"claims[{index}] has no highly relevant evidence; verify claim and market fit")
        if claim.get("confidence") == "high":
            origin_groups = {
                indexes["sources"].get(item.get("source_id"), {}).get("origin_group")
                for item in claim_evidence
                if item.get("independent")
            }
            origin_groups.discard(None)
            if len(origin_groups) < 2:
                errors.append(f"claims[{index}] high confidence requires two independent origin groups")
            if any(item.get("conflict") for item in claim_evidence):
                errors.append(f"claims[{index}] high confidence cannot retain conflicting evidence")
            freshness = {
                indexes["sources"].get(item.get("source_id"), {}).get("freshness_status")
                for item in claim_evidence
            }
            if freshness - {"current", "not_applicable"}:
                errors.append(f"claims[{index}] high confidence requires current or time-invariant sources")
            if not any((item.get("directness") or 0) >= 4 for item in claim_evidence):
                errors.append(f"claims[{index}] high confidence requires direct evidence")
            if not any((item.get("relevance") or 0) >= 4 for item in claim_evidence):
                errors.append(f"claims[{index}] high confidence requires highly relevant evidence")
            if not any(item.get("market_fit") == "aligned" for item in claim_evidence):
                errors.append(f"claims[{index}] high confidence requires market-aligned evidence")

    recommendation_claim_ids = {
        item["claim_id"] for item in data["claims"] if item.get("claim_type") == "recommendation"
    }
    for evidence_id in summary.get("evidence_ids", []):
        linked_claims = set(evidence_by_id.get(evidence_id, {}).get("claim_ids", []))
        if not linked_claims.intersection(recommendation_claim_ids):
            errors.append(
                f"executive_summary.evidence_ids item {evidence_id} is not linked to a recommendation claim"
            )

    for index, need in enumerate(data["user_needs"]):
        path = f"user_needs[{index}]"
        for field in ("segment", "task", "scene", "willingness_signal"):
            _require_text(need.get(field), f"{path}.{field}", errors)
        for field in ("importance", "urgency", "dissatisfaction"):
            _check_score(need.get(field), f"{path}.{field}", errors)
        _check_references(need.get("evidence_ids"), f"{path}.evidence_ids", evidence_ids, errors, nonempty=True)

    covered_competitor_types: set[str] = set()
    for index, competitor in enumerate(data["competitors"]):
        path = f"competitors[{index}]"
        for field in ("name", "competitor_type", "category", "positioning_statement"):
            _require_text(competitor.get(field), f"{path}.{field}", errors)
        for field in ("target_users", "differentiation_claims", "strengths", "weaknesses", "mindshare_keywords"):
            _require_string_array(competitor.get(field), f"{path}.{field}", errors, nonempty=True)
        if "price_label" not in competitor:
            errors.append(f"{path}.price_label must be present; use null when unknown")
        if not isinstance(competitor.get("price_verified"), bool):
            errors.append(f"{path}.price_verified must be boolean")
        if competitor.get("price_verified") and competitor.get("price_label") in (None, ""):
            errors.append(f"{path}.price_verified cannot be true without price_label")
        competitor_type = competitor.get("competitor_type")
        if competitor_type not in ALLOWED_COMPETITOR_TYPES:
            errors.append(f"{path}.competitor_type is invalid")
        else:
            covered_competitor_types.add(competitor_type)
        for field in ("category_clarity", "differentiation_strength", "proof_strength", "user_relevance"):
            _check_score(competitor.get(field), f"{path}.{field}", errors)
        _check_references(competitor.get("evidence_ids"), f"{path}.evidence_ids", evidence_ids, errors)
        if not competitor.get("evidence_ids"):
            warnings.append(f"{path} has no evidence and must be displayed as unverified")
        positioning_statement = competitor.get("positioning_statement")
        if isinstance(positioning_statement, str) and len(positioning_statement) > 60:
            warnings.append(f"{path}.positioning_statement is too long for a one-line mental model")

    required_roles = {"direct", "indirect", "status_quo", "inaction"}
    missing_roles = sorted(required_roles - covered_competitor_types)
    if missing_roles:
        warnings.append(f"competitor set is missing roles: {', '.join(missing_roles)}")
    if meta.get("research_mode") in {"standard", "deep"}:
        direct_count = sum(item.get("competitor_type") == "direct" for item in data["competitors"])
        indirect_count = sum(item.get("competitor_type") == "indirect" for item in data["competitors"])
        benchmark_count = sum(item.get("competitor_type") == "benchmark" for item in data["competitors"])
        if direct_count < 3:
            warnings.append(f"standard competitor research expects at least 3 direct competitors; found {direct_count}")
        if indirect_count < 1:
            warnings.append("standard competitor research expects at least 1 indirect competitor")
        if benchmark_count < 1:
            warnings.append("standard competitor research has no mental benchmark; explain why or add one")

    for index, position in enumerate(data["mental_positions"]):
        path = f"mental_positions[{index}]"
        for field in ("keyword", "category", "occupant", "status", "confidence"):
            _require_text(position.get(field), f"{path}.{field}", errors)
        _check_score(position.get("ladder_level"), f"{path}.ladder_level", errors)
        if position.get("status") not in ALLOWED_MENTAL_POSITION_STATUS:
            errors.append(f"{path}.status is invalid")
        if position.get("confidence") not in ALLOWED_CONFIDENCE:
            errors.append(f"{path}.confidence is invalid")
        _check_references(position.get("evidence_ids"), f"{path}.evidence_ids", evidence_ids, errors)
        if position.get("status") != "unverified" and not position.get("evidence_ids"):
            errors.append(f"{path}.evidence_ids must support a verified mental position")

    for index, advantage in enumerate(data["advantages"]):
        path = f"advantages[{index}]"
        for field in ("label", "description"):
            _require_text(advantage.get(field), f"{path}.{field}", errors)
        for field in ("relevance", "rarity", "evidence_strength", "defensibility", "strategic_fit", "expression_focus"):
            _check_score(advantage.get(field), f"{path}.{field}", errors)
        _check_score(advantage.get("competitor_median"), f"{path}.competitor_median", errors)
        if advantage.get("status") not in ALLOWED_ADVANTAGE_STATUS:
            errors.append(f"{path}.status is invalid")
        _check_references(advantage.get("evidence_ids"), f"{path}.evidence_ids", evidence_ids, errors)
        _require_string_array(advantage.get("disqualifiers"), f"{path}.disqualifiers", errors)
        if advantage.get("status") == "eligible" and advantage.get("disqualifiers"):
            errors.append(f"{path} cannot be eligible while disqualifiers remain")
        if advantage.get("status") == "eligible" and not (
            (advantage.get("relevance") or 0) >= 4
            and (advantage.get("rarity") or 0) >= 3
            and (advantage.get("evidence_strength") or 0) >= 3
            and (advantage.get("strategic_fit") or 0) >= 3
            and (advantage.get("expression_focus") or 0) >= 3
        ):
            errors.append(f"{path} does not meet the D6 minimums for eligible status")

    layer = data.get("four_layer_positioning")
    if subject.get("type") in {"personal_ip", "course"} and not isinstance(layer, dict):
        errors.append("four_layer_positioning is required for personal_ip and course reports")
    if isinstance(layer, dict):
        for field in ("mission", "persona", "business", "content", "alignment_status"):
            _require_text(layer.get(field), f"four_layer_positioning.{field}", errors)
        if layer.get("alignment_status") not in ALLOWED_ALIGNMENT_STATUS:
            errors.append("four_layer_positioning.alignment_status is invalid")
        _require_string_array(layer.get("strengths"), "four_layer_positioning.strengths", errors)
        _require_string_array(layer.get("conflicts"), "four_layer_positioning.conflicts", errors)
        _check_references(layer.get("evidence_ids"), "four_layer_positioning.evidence_ids", evidence_ids, errors, nonempty=True)

    course_extension = data.get("course_marketing_extension")
    if subject.get("type") == "course" and not isinstance(course_extension, dict):
        errors.append("course_marketing_extension is required for course reports")
    if isinstance(course_extension, dict):
        for field in (
            "professional_persona", "character_persona", "audience_persona_fit", "target_person",
            "course_result", "method_mechanism", "delivery_structure", "content_difference",
        ):
            _require_text(course_extension.get(field), f"course_marketing_extension.{field}", errors)
        _check_references(
            course_extension.get("evidence_ids"),
            "course_marketing_extension.evidence_ids",
            evidence_ids,
            errors,
            nonempty=True,
        )
        action_path = course_extension.get("action_path")
        _require_array(action_path, "course_marketing_extension.action_path", errors, nonempty=True)
        if isinstance(action_path, list):
            for index, step in enumerate(action_path):
                path = f"course_marketing_extension.action_path[{index}]"
                if not isinstance(step, dict):
                    errors.append(f"{path} must be an object")
                    continue
                for field in ("stage", "task", "pain_point", "current_solution"):
                    _require_text(step.get(field), f"{path}.{field}", errors)
                _check_references(step.get("evidence_ids"), f"{path}.evidence_ids", evidence_ids, errors, nonempty=True)
        marketing_mix = course_extension.get("marketing_mix_4p")
        _require_object(marketing_mix, "course_marketing_extension.marketing_mix_4p", errors)
        if isinstance(marketing_mix, dict):
            for dimension in ("product", "price", "channel", "promotion"):
                choice = marketing_mix.get(dimension)
                path = f"course_marketing_extension.marketing_mix_4p.{dimension}"
                if not isinstance(choice, dict):
                    errors.append(f"{path} must be an object")
                    continue
                for field in ("baseline", "differentiation_choice"):
                    _require_text(choice.get(field), f"{path}.{field}", errors)
                _check_references(choice.get("evidence_ids"), f"{path}.evidence_ids", evidence_ids, errors, nonempty=True)

    for index, opportunity in enumerate(data["opportunities"]):
        path = f"opportunities[{index}]"
        for field in ("supply_gap", "category_option", "risk", "confidence"):
            _require_text(opportunity.get(field), f"{path}.{field}", errors)
        if opportunity.get("confidence") not in ALLOWED_CONFIDENCE:
            errors.append(f"{path}.confidence is invalid")
        _check_references(opportunity.get("user_need_ids"), f"{path}.user_need_ids", need_ids, errors, nonempty=True)
        _check_references(opportunity.get("evidence_ids"), f"{path}.evidence_ids", evidence_ids, errors, nonempty=True)
        opportunity_evidence = set(opportunity.get("evidence_ids", []))
        linked_need_evidence = {
            evidence_id
            for need_id in opportunity.get("user_need_ids", [])
            for evidence_id in indexes["user_needs"].get(need_id, {}).get("evidence_ids", [])
        }
        competitor_evidence = {
            evidence_id for item in data["competitors"] for evidence_id in item.get("evidence_ids", [])
        }
        capability_evidence = {
            evidence_id for item in data["advantages"] for evidence_id in item.get("evidence_ids", [])
        }
        if not opportunity_evidence.intersection(linked_need_evidence):
            errors.append(f"{path}.evidence_ids must include linked user-need evidence")
        if not opportunity_evidence.intersection(competitor_evidence):
            errors.append(f"{path}.evidence_ids must include competitor or substitute evidence")
        if not opportunity_evidence.intersection(capability_evidence):
            errors.append(f"{path}.evidence_ids must include subject capability evidence")

    recommended: dict[str, Any] | None = None
    for index, option in enumerate(data["positioning_options"]):
        path = f"positioning_options[{index}]"
        for field in (
            "name", "target_user", "key_scene", "category", "differentiation_label", "differentiation",
            "core_value", "unique_mechanism", "proof", "mindshare_keyword", "reposition_from", "rationale",
        ):
            _require_text(option.get(field), f"{path}.{field}", errors)
        for field in ("execution_cost", "risk_level", "user_value", "competitive_uniqueness", "category_clarity"):
            _check_score(option.get(field), f"{path}.{field}", errors)
        if option.get("status") not in ALLOWED_OPTION_STATUS:
            errors.append(f"{path}.status is invalid")
        if option.get("status") == "recommended":
            if recommended is not None:
                errors.append("positioning_options must contain exactly one recommended option")
            recommended = option
        _check_references(
            option.get("evidence_ids"), f"{path}.evidence_ids", evidence_ids, errors,
            nonempty=option.get("status") == "recommended",
        )
    if recommended is None:
        errors.append("positioning_options must contain exactly one recommended option")
    if not 2 <= len(data["positioning_options"]) <= 3:
        warnings.append("positioning_options should normally contain 2 to 3 options")
    if recommended:
        for summary_field, option_field in (
            ("category", "category"),
            ("differentiation_label", "differentiation_label"),
            ("core_value", "core_value"),
            ("unique_mechanism", "unique_mechanism"),
            ("mindshare_keyword", "mindshare_keyword"),
        ):
            if summary.get(summary_field) != recommended.get(option_field):
                errors.append(
                    f"executive_summary.{summary_field} must match the recommended option {option_field}"
                )
        unshared = set(summary.get("evidence_ids", [])) - set(recommended.get("evidence_ids", []))
        if unshared:
            errors.append(
                "executive_summary.evidence_ids must be a subset of the recommended option evidence_ids"
            )

    recommendation_evidence = set(summary.get("evidence_ids", []))
    recommendation_relevance = [
        evidence_by_id.get(evidence_id, {}).get("relevance", 0)
        for evidence_id in recommendation_evidence
    ]
    if recommendation_relevance and max(recommendation_relevance) < 4:
        message = "recommendation evidence must include at least one highly relevant item"
        if summary.get("recommendation_status") == "execute":
            errors.append(message)
        else:
            warnings.append(message)
    recommendation_market_fit = [
        evidence_by_id.get(evidence_id, {}).get("market_fit")
        for evidence_id in recommendation_evidence
    ]
    if recommendation_market_fit and "aligned" not in recommendation_market_fit:
        message = "recommendation evidence must include at least one market-aligned evidence item"
        if summary.get("recommendation_status") == "execute":
            errors.append(message)
        else:
            warnings.append(message)
    need_evidence = {
        evidence_id for item in data["user_needs"] for evidence_id in item.get("evidence_ids", [])
    }
    competitor_evidence = {
        evidence_id for item in data["competitors"] for evidence_id in item.get("evidence_ids", [])
    }
    capability_evidence = {
        evidence_id for item in data["advantages"] for evidence_id in item.get("evidence_ids", [])
    }
    recommendation_coverage = (
        ("user-need evidence", need_evidence),
        ("competitor or substitute evidence", competitor_evidence),
        ("subject capability evidence", capability_evidence),
    )
    for label, coverage in recommendation_coverage:
        if recommendation_evidence.intersection(coverage):
            continue
        message = f"{summary.get('recommendation_status')} recommendation evidence must include {label}"
        if summary.get("recommendation_status") == "execute":
            errors.append(message)
        elif summary.get("recommendation_status") == "validate_first":
            warnings.append(message)

    for index, action in enumerate(data["strategic_actions"]):
        path = f"strategic_actions[{index}]"
        for field in ("area", "action", "rationale", "priority", "owner", "horizon", "success_signal"):
            _require_text(action.get(field), f"{path}.{field}", errors)
        if action.get("area") not in ALLOWED_ACTION_AREAS:
            errors.append(f"{path}.area is invalid")
        if action.get("priority") not in ALLOWED_ACTION_PRIORITY:
            errors.append(f"{path}.priority is invalid")
        _check_references(action.get("evidence_ids"), f"{path}.evidence_ids", evidence_ids, errors, nonempty=True)
    action_areas = {item.get("area") for item in data["strategic_actions"]}
    missing_action_areas = sorted({"expression", "product", "content", "price", "channel", "sales"} - action_areas)
    if missing_action_areas:
        warnings.append(f"strategic action plan is missing areas: {', '.join(missing_action_areas)}")

    for index, experiment in enumerate(data["validation_plan"]):
        path = f"validation_plan[{index}]"
        for field in ("hypothesis", "audience", "method", "baseline", "metric", "decision_rule"):
            _require_text(experiment.get(field), f"{path}.{field}", errors)
        threshold = experiment.get("threshold")
        threshold_unit = experiment.get("threshold_unit")
        if threshold_unit not in ALLOWED_THRESHOLD_UNITS:
            errors.append(f"{path}.threshold_unit must be rate or score_5")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            errors.append(f"{path}.threshold must be numeric")
        elif threshold_unit == "rate" and not 0 <= threshold <= 1:
            errors.append(f"{path}.threshold must be between 0 and 1 for rate")
        elif threshold_unit == "score_5" and not 1 <= threshold <= 5:
            errors.append(f"{path}.threshold must be between 1 and 5 for score_5")
        for field in ("sample", "duration_days"):
            value = experiment.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                errors.append(f"{path}.{field} must be a positive integer")

    if isinstance(planned, int) and not isinstance(planned, bool) and planned > len(data["competitors"]):
        warnings.append(f"competitor coverage is {len(data['competitors'])}/{planned}; explain the gap in the report")
    if summary.get("recommendation_status") == "execute" and not any(
        item.get("status") == "eligible" for item in data["advantages"]
    ):
        errors.append("execute recommendations require at least one eligible advantage")
    if summary.get("recommendation_status") == "execute":
        linked_recommendation_claims = [
            claim for claim in data["claims"]
            if claim.get("claim_type") == "recommendation"
            and recommendation_evidence.intersection(claim.get("evidence_ids", []))
        ]
        if not linked_recommendation_claims or any(
            claim.get("confidence") != "high" for claim in linked_recommendation_claims
        ):
            errors.append("execute recommendations require high-confidence recommendation claims")
        if any(evidence_by_id.get(item, {}).get("conflict") for item in recommendation_evidence):
            errors.append("execute recommendation evidence must not contain unresolved conflicts")
        if isinstance(layer, dict) and layer.get("alignment_status") in {"conflicted", "insufficient"}:
            errors.append("execute recommendations require four-layer positioning without direct conflicts")
        if "direct" not in covered_competitor_types or "indirect" not in covered_competitor_types:
            errors.append("execute recommendations require direct and indirect competitor roles")
        if not covered_competitor_types.intersection({"status_quo", "inaction"}):
            errors.append("execute recommendations require a status-quo or inaction alternative")
        direct_competitor_evidence = {
            evidence_id
            for competitor in data["competitors"]
            if competitor.get("competitor_type") == "direct"
            for evidence_id in competitor.get("evidence_ids", [])
        }
        direct_competitor_perspectives = {
            indexes["sources"].get(evidence_by_id.get(evidence_id, {}).get("source_id"), {}).get("perspective")
            for evidence_id in direct_competitor_evidence
        }
        if not direct_competitor_perspectives.intersection({"user", "mixed"}):
            errors.append("execute recommendations require user-side evidence for a direct competitor")
    return errors, warnings


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 4)


def _median(values: list[float]) -> float | None:
    clean = sorted(value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool))
    if not clean:
        return None
    middle = len(clean) // 2
    if len(clean) % 2:
        return round(float(clean[middle]), 2)
    return round((clean[middle - 1] + clean[middle]) / 2, 2)


def compute_metrics(data: dict[str, Any]) -> dict[str, Any]:
    evidence_by_id = {item["evidence_id"]: item for item in data.get("evidence", [])}
    source_by_id = {item["source_id"]: item for item in data.get("sources", [])}
    critical_claims = [
        claim for claim in data.get("claims", []) if claim.get("claim_type") in {"fact", "inference", "recommendation"}
    ]
    covered_claims = [claim for claim in critical_claims if claim.get("evidence_ids")]
    independently_supported = 0
    conflict_claim_count = 0
    used_evidence_ids: set[str] = set()
    for claim in critical_claims:
        origin_groups: set[str] = set()
        claim_has_conflict = False
        for evidence_id in claim.get("evidence_ids", []):
            evidence = evidence_by_id.get(evidence_id)
            if not evidence:
                continue
            used_evidence_ids.add(evidence_id)
            claim_has_conflict = claim_has_conflict or bool(evidence.get("conflict"))
            source = source_by_id.get(evidence.get("source_id"), {})
            if evidence.get("independent"):
                origin_groups.add(str(source.get("origin_group") or source.get("source_id")))
        if len(origin_groups) >= 2:
            independently_supported += 1
        conflict_claim_count += int(claim_has_conflict)

    ab_supported_evidence = sum(
        source_by_id.get(evidence_by_id[item].get("source_id"), {}).get("grade") in {"A", "B"}
        for item in used_evidence_ids
    )
    market_aligned_evidence = sum(
        evidence_by_id[item].get("market_fit") == "aligned" for item in used_evidence_ids
    )
    dynamic_sources = [
        item for item in data.get("sources", []) if item.get("freshness_status") != "not_applicable"
    ]
    current_sources = sum(item.get("freshness_status") == "current" for item in dynamic_sources)

    competitor_types = Counter(item.get("competitor_type") for item in data.get("competitors", []))
    competitors_with_evidence = sum(bool(item.get("evidence_ids")) for item in data.get("competitors", []))
    core_competitors = [
        item for item in data.get("competitors", []) if item.get("competitor_type") in {"direct", "indirect", "benchmark"}
    ]
    competitors_with_user_evidence = sum(
        any(
            source_by_id.get(evidence_by_id.get(evidence_id, {}).get("source_id"), {}).get("perspective")
            in {"user", "mixed"}
            for evidence_id in item.get("evidence_ids", [])
        )
        for item in core_competitors
    )
    transparent_prices = sum(bool(item.get("price_verified")) for item in core_competitors)
    planned = data.get("research_scope", {}).get("planned_competitor_count") or len(data.get("competitors", []))
    valid_differences = sum(
        item.get("relevance", 0) >= 4
        and item.get("rarity", 0) >= 3
        and item.get("evidence_strength", 0) >= 3
        and item.get("status") == "eligible"
        for item in data.get("advantages", [])
    )
    key_risks = sum(
        option.get("risk_level", 0) >= 4 for option in data.get("positioning_options", [])
    ) + conflict_claim_count
    claim_confidence = Counter(item.get("confidence") for item in data.get("claims", []))
    source_grades = Counter(item.get("grade") for item in data.get("sources", []))

    needs = data.get("user_needs", [])
    options = data.get("positioning_options", [])
    recommended = next((item for item in options if item.get("status") == "recommended"), {})
    metrics = {
        "evidence_coverage_rate": _ratio(len(covered_claims), len(critical_claims)),
        "independent_corroboration_rate": _ratio(independently_supported, len(critical_claims)),
        "ab_source_share": _ratio(ab_supported_evidence, len(used_evidence_ids)),
        "freshness_compliance_rate": _ratio(current_sources, len(dynamic_sources)),
        "unresolved_conflict_rate": _ratio(conflict_claim_count, len(critical_claims)),
        "market_fit_coverage_rate": _ratio(market_aligned_evidence, len(used_evidence_ids)),
        "competitor_set_coverage": min(1.0, _ratio(len(data.get("competitors", [])), planned) or 0.0),
        "competitor_evidence_coverage": _ratio(competitors_with_evidence, len(data.get("competitors", []))),
        "competitor_user_evidence_coverage": _ratio(competitors_with_user_evidence, len(core_competitors)),
        "price_transparency_rate": _ratio(transparent_prices, len(core_competitors)),
        "need_importance_median": _median([item.get("importance") for item in needs]),
        "need_urgency_median": _median([item.get("urgency") for item in needs]),
        "need_dissatisfaction_median": _median([item.get("dissatisfaction") for item in needs]),
        "valid_difference_count": valid_differences,
        "recommended_category_clarity": recommended.get("category_clarity"),
        "recommended_user_value": recommended.get("user_value"),
        "recommended_competitive_uniqueness": recommended.get("competitive_uniqueness"),
        "recommended_execution_cost": recommended.get("execution_cost"),
        "key_risk_count": key_risks,
        "source_grade_counts": dict(sorted(source_grades.items())),
        "competitor_type_counts": dict(sorted((str(k), v) for k, v in competitor_types.items() if k)),
        "claim_confidence_counts": dict(sorted((str(k), v) for k, v in claim_confidence.items() if k)),
    }
    return metrics


def normalize_report(data: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(data, ensure_ascii=False))
    normalized["computed_metrics"] = compute_metrics(normalized)
    return normalized


def safe_source_display(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "证据不足"
    if re.match(r"^https?://", value, flags=re.IGNORECASE):
        return value
    normalized = value.replace("\\", "/")
    return normalized.rsplit("/", 1)[-1] or "本地文件"


def safe_json_for_script(data: dict[str, Any]) -> str:
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
