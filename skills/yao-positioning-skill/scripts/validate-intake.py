#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from schema_validator import validate_against_schema


SCRIPT_INTERFACE = "cli"
SCRIPT_INTERFACE_REASON = "Validates the minimum positioning intake before any external research or competitor analysis starts."
SCHEMA = Path(__file__).resolve().parents[1] / "templates" / "intake-brief.schema.json"


QUESTION_BANK = {
    "subject.name": {
        "question": "这次要定位的是谁或什么？",
        "why": "定位对象决定分析结构和竞争集合。",
        "examples": ["一家企业服务公司", "一门 AI 课程", "我的个人专家品牌"],
    },
    "objective": {
        "question": "希望这次定位解决什么具体决策？",
        "why": "获客、品牌升级和进入新市场会产生不同结论。",
        "examples": ["让官网更容易理解", "进入中国大陆企业市场", "摆脱普通代运营认知"],
    },
    "offer": {
        "question": "客户最终购买和得到的是什么？",
        "why": "定位必须建立在真实产品和交付上。",
        "examples": ["季度 GEO 运营服务", "6 周训练营", "软件加顾问服务"],
    },
    "market.region": {
        "question": "本次优先分析哪个地域？",
        "why": "地域会改变竞品、法规和用户认知。",
        "examples": ["中国大陆", "新加坡", "全球英语市场"],
    },
    "market.language": {
        "question": "本次研究使用什么主要语言？",
        "why": "语言决定检索范围和用户表达。",
        "examples": ["中文", "英语", "中英双语"],
    },
    "target_user_hypothesis": {
        "question": "谁会决定购买，通常在什么情况下开始寻找方案？",
        "why": "决策者和触发场景决定真实竞争对象。",
        "examples": ["品牌负责人发现 AI 回答错误时", "创业者准备系统获客时", "HR 需要改善团队状态时"],
    },
    "inputs.accessible_subject_material": {
        "question": "可以提供哪项主体资料供检查？",
        "why": "至少需要一项可读取材料才能理解当前公开定位和真实交付。",
        "examples": ["直接文字介绍", "公司或产品附件", "官网或产品页 URL"],
    },
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"input file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("intake root must be a JSON object")
    return data


def has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def readiness_missing(data: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    subject = data.get("subject") if isinstance(data.get("subject"), dict) else {}
    market = data.get("market") if isinstance(data.get("market"), dict) else {}
    if not has_text(subject.get("name")):
        missing.append("subject.name")
    if not has_text(data.get("objective")):
        missing.append("objective")
    if not has_text(data.get("offer")):
        missing.append("offer")
    if not has_text(market.get("region")):
        missing.append("market.region")
    if not has_text(market.get("language")):
        missing.append("market.language")
    targets = data.get("target_user_hypothesis")
    if not isinstance(targets, list) or not any(has_text(item) for item in targets):
        missing.append("target_user_hypothesis")
    inputs = data.get("inputs") if isinstance(data.get("inputs"), list) else []
    inspectable = any(
        isinstance(item, dict)
        and item.get("accessible") is True
        and item.get("role") in {"subject", "offer", "proof"}
        and has_text(item.get("locator"))
        for item in inputs
    )
    if not inspectable:
        missing.append("inputs.accessible_subject_material")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a positioning intake brief before research starts.")
    parser.add_argument("input", type=Path, help="Path to intake brief JSON")
    args = parser.parse_args()

    try:
        data = load_json(args.input)
        schema_errors = validate_against_schema(data, SCHEMA)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    missing = readiness_missing(data) if not schema_errors else []
    received = sorted({
        item.get("input_type")
        for item in data.get("inputs", [])
        if isinstance(item, dict) and item.get("input_type") in {"text", "file", "url"}
    })
    payload = {
        "valid_structure": not schema_errors,
        "research_ready": not schema_errors and not missing,
        "status": "intake_ready" if not schema_errors and not missing else "intake_incomplete",
        "errors": schema_errors,
        "missing": missing,
        "received_input_types": received,
        "questions": [
            {"field": field, **QUESTION_BANK[field]}
            for field in missing[:3]
            if field in QUESTION_BANK
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["research_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
