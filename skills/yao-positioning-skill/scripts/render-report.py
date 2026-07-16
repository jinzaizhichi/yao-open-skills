#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from report_model import (
    load_json,
    normalize_report,
    safe_json_for_script,
    safe_source_display,
    validate_against_schema,
    validate_report,
)


SCRIPT_INTERFACE = "cli"
SCRIPT_INTERFACE_REASON = "Validates positioning data and writes the declared offline HTML, Markdown, and normalized JSON report bundle."

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "assets" / "report-template.html"
DEFAULT_ECHARTS = ROOT / "assets" / "echarts.min.js"

STATUS_LABELS = {
    "execute": "可以执行",
    "validate_first": "建议先验证",
    "insufficient_evidence": "证据不足",
    "recommended": "推荐",
    "alternative": "备选",
    "reserve": "保留",
    "rejected": "否决",
    "eligible": "可进入定位",
    "validate": "待验证",
    "reject": "否决",
    "occupied": "已占据",
    "contested": "争夺中",
    "candidate": "候选位置",
    "unverified": "未验证",
    "aligned": "一致",
    "partial": "部分一致",
    "conflicted": "存在冲突",
    "insufficient": "证据不足",
    "high": "高",
    "medium": "中",
    "low": "低",
    "current": "时效内",
    "stale": "已过期",
    "not_applicable": "不适用",
    "unknown": "时效未知",
}
RESEARCH_MODE_LABELS = {"local": "本地证据", "standard": "标准研究", "deep": "深度研究"}
COMPETITOR_TYPE_LABELS = {
    "direct": "直接竞品",
    "indirect": "间接方案",
    "status_quo": "现状方案",
    "inaction": "不行动",
    "benchmark": "心智标杆",
}
ACTION_AREA_LABELS = {
    "expression": "表达",
    "product": "产品",
    "content": "内容",
    "price": "价格",
    "channel": "渠道",
    "sales": "销售",
}


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def display(value: Any) -> str:
    if value is None or value == "":
        return "证据不足"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def percent(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "证据不足"
    return f"{value * 100:.0f}%"


def threshold_display(value: Any, unit: Any) -> str:
    if unit == "score_5" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}/5"
    return percent(value)


def markdown_escape(value: Any) -> str:
    return html.escape(display(value), quote=False).replace("|", "\\|").replace("\n", " ")


def markdown_list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "证据不足"
    return "、".join(markdown_escape(item) for item in values)


def enum_label(value: Any, labels: dict[str, str] = STATUS_LABELS) -> str:
    return labels.get(str(value), display(value))


def competitor_price_display(item: dict[str, Any], subject_type: Any) -> str:
    label = display(item.get("price_label"))
    if item.get("price_verified"):
        return f"{label}（已核验）"
    if "不适用" in label:
        return label
    suffix = "（未纳入定位比较）" if subject_type == "personal_ip" else "（未核验）"
    return f"{label}{suffix}"


def render_markdown(data: dict[str, Any]) -> str:
    meta = data["meta"]
    subject = data["subject"]
    snapshot = data["positioning_snapshot"]
    summary = data["executive_summary"]
    metrics = data["computed_metrics"]
    direct_competitors = [item for item in data["competitors"] if item.get("competitor_type") == "direct"]
    direct_competitors.sort(key=lambda item: item.get("competitor_id") != snapshot.get("primary_competitor_id"))
    lines = [
        f"# {markdown_escape(meta['report_title'])}",
        "",
        f"> 研究对象：{markdown_escape(subject['name'])}  ",
        f"> 研究模式：{markdown_escape(enum_label(meta.get('research_mode'), RESEARCH_MODE_LABELS))}  ",
        f"> 报告日期：{markdown_escape(meta.get('generated_at'))}",
        "",
        "## 一句话看懂定位",
        "",
        f"- 现在容易被理解为：**{markdown_escape(snapshot['current_mental_label'])}**",
        f"- 当前一句话：{markdown_escape(snapshot['current_one_liner'])}",
        f"- 当前问题：{markdown_escape(snapshot['current_problem'])}",
        f"- 建议只占一个词：**{markdown_escape(snapshot['desired_mental_label'])}**",
        f"- 对立句：{markdown_escape(snapshot['contrast_sentence'])}",
        "",
        "### 主要对手，一句话理解",
        "",
        "| 对手 | 一句话理解 | 记忆标签 |",
        "|---|---|---|",
    ]
    for item in direct_competitors[:3]:
        lines.append(
            "| " + " | ".join([
                markdown_escape(item.get("name")),
                markdown_escape(item.get("positioning_statement")),
                markdown_escape((item.get("mindshare_keywords") or [item.get("category")])[0]),
            ]) + " |"
        )
    lines.extend([
        "",
        "### 推荐一句话",
        "",
        f"**{markdown_escape(snapshot['desired_one_liner'])}**",
        "",
        f"- 给谁：{markdown_escape(subject['target_users'][0])}",
        f"- 我们是什么：{markdown_escape(snapshot['desired_category'])}",
        f"- 最关键的不同：{markdown_escape(summary['differentiation_label'])}",
        f"- 推荐状态：{markdown_escape(enum_label(summary['recommendation_status']))}",
        f"- 下一步：{markdown_escape(summary['next_action'])}",
        "",
        "### 为什么可以相信",
        "",
    ])
    lines.extend(f"- {markdown_escape(item)}" for item in snapshot["reason_to_believe"])
    lines.extend(["", "### 明确不做", ""])
    lines.extend(f"- {markdown_escape(item)}" for item in snapshot["sacrifice"])
    lines.extend([
        "",
        f"> 完整判断：{markdown_escape(summary.get('rationale'))}",
        f"> 反证条件：{markdown_escape(summary['counterevidence_condition'])}",
        "",
        "## 研究可信度",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 证据覆盖率 | {percent(metrics.get('evidence_coverage_rate'))} |",
        f"| 独立佐证率 | {percent(metrics.get('independent_corroboration_rate'))} |",
        f"| A/B 级证据占比 | {percent(metrics.get('ab_source_share'))} |",
        f"| 时效合规率 | {percent(metrics.get('freshness_compliance_rate'))} |",
        f"| 本地市场适配证据占比 | {percent(metrics.get('market_fit_coverage_rate'))} |",
        f"| 竞品证据覆盖率 | {percent(metrics.get('competitor_evidence_coverage'))} |",
        f"| 核心竞品用户侧证据覆盖率 | {percent(metrics.get('competitor_user_evidence_coverage'))} |",
        f"| 未解决冲突率 | {percent(metrics.get('unresolved_conflict_rate'))} |",
        "",
        "## 用户需求",
        "",
        "| 用户 | 场景 | 任务 | 重要性 | 紧迫性 | 不满程度 |",
        "|---|---|---|---:|---:|---:|",
    ])
    for item in data["user_needs"]:
        lines.append(
            "| " + " | ".join(
                markdown_escape(item.get(key))
                for key in ("segment", "scene", "task", "importance", "urgency", "dissatisfaction")
            ) + " |"
        )

    lines.extend([
        "",
        "## 市场机会与无效空位",
        "",
        "| 机会品类 | 关联需求 | 供应缺口 | 主要风险 | 置信度 | 证据 |",
        "|---|---|---|---|---|---|",
    ])
    for item in data["opportunities"]:
        lines.append(
            "| " + " | ".join([
                markdown_escape(item.get("category_option")),
                markdown_escape(", ".join(item.get("user_need_ids", []))),
                markdown_escape(item.get("supply_gap")),
                markdown_escape(item.get("risk")),
                markdown_escape(enum_label(item.get("confidence"))),
                markdown_escape(", ".join(item.get("evidence_ids", []))),
            ]) + " |"
        )

    lines.extend([
        "",
        "## 竞品与替代方案",
        "",
        "| 对手 | 类型 | 一句话理解 | 记忆标签 | 价格 | 证据 |",
        "|---|---|---|---|---|---|",
    ])
    for item in data["competitors"]:
        lines.append(
            "| " + " | ".join([
                markdown_escape(item.get("name")),
                markdown_escape(enum_label(item.get("competitor_type"), COMPETITOR_TYPE_LABELS)),
                markdown_escape(item.get("positioning_statement")),
                markdown_escape((item.get("mindshare_keywords") or [item.get("category")])[0]),
                markdown_escape(competitor_price_display(item, subject.get("type"))),
                markdown_escape(", ".join(item.get("evidence_ids", [])) or "未验证"),
            ]) + " |"
        )

    lines.extend([
        "",
        "## 心智阶梯与已占位置",
        "",
        "| 关键词 | 品类 | 占位者 | 阶梯 | 状态 | 置信度 | 证据 |",
        "|---|---|---|---:|---|---|---|",
    ])
    for item in data["mental_positions"]:
        lines.append(
            "| " + " | ".join([
                markdown_escape(item.get("keyword")),
                markdown_escape(item.get("category")),
                markdown_escape(item.get("occupant")),
                markdown_escape(item.get("ladder_level")),
                markdown_escape(enum_label(item.get("status"))),
                markdown_escape(enum_label(item.get("confidence"))),
            ]) + f" | {markdown_escape(', '.join(item.get('evidence_ids', [])) or '未验证')} |"
        )

    lines.extend([
        "",
        "## 差异化与优势诊断",
        "",
        "| 优势候选 | 用户相关 | 稀缺 | 证据 | 防御 | 战略适配 | 状态 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for item in data["advantages"]:
        lines.append(
            "| " + " | ".join([
                markdown_escape(item.get("label")),
                markdown_escape(item.get("relevance")),
                markdown_escape(item.get("rarity")),
                markdown_escape(item.get("evidence_strength")),
                markdown_escape(item.get("defensibility")),
                markdown_escape(item.get("strategic_fit")),
                markdown_escape(enum_label(item.get("status"))),
            ]) + " |"
        )

    layer = data.get("four_layer_positioning")
    if isinstance(layer, dict):
        lines.extend([
            "",
            "## 使命、人设、商业与内容四层一致性",
            "",
            f"- 使命：{markdown_escape(layer.get('mission'))}",
            f"- 人设：{markdown_escape(layer.get('persona'))}",
            f"- 商业：{markdown_escape(layer.get('business'))}",
            f"- 内容：{markdown_escape(layer.get('content'))}",
            f"- 一致性：{markdown_escape(enum_label(layer.get('alignment_status')))}",
            f"- 已对齐：{markdown_list(layer.get('strengths'))}",
            f"- 冲突：{markdown_list(layer.get('conflicts'))}",
        ])

    course_extension = data.get("course_marketing_extension")
    if isinstance(course_extension, dict):
        lines.extend([
            "",
            "## 课程营销定位扩展",
            "",
            f"- 专业人设：{markdown_escape(course_extension.get('professional_persona'))}",
            f"- 性格人设：{markdown_escape(course_extension.get('character_persona'))}",
            f"- 用户人格匹配：{markdown_escape(course_extension.get('audience_persona_fit'))}",
            f"- 靶心人：{markdown_escape(course_extension.get('target_person'))}",
            f"- 课程结果：{markdown_escape(course_extension.get('course_result'))}",
            f"- 方法机制：{markdown_escape(course_extension.get('method_mechanism'))}",
            f"- 交付结构：{markdown_escape(course_extension.get('delivery_structure'))}",
            f"- 内容差异：{markdown_escape(course_extension.get('content_difference'))}",
            "",
            "### 靶心人行动路径与痛点",
            "",
            "| 阶段 | 用户任务 | 核心痛点 | 当前方案 | 证据 |",
            "|---|---|---|---|---|",
        ])
        for step in course_extension.get("action_path", []):
            lines.append(
                "| " + " | ".join([
                    markdown_escape(step.get("stage")),
                    markdown_escape(step.get("task")),
                    markdown_escape(step.get("pain_point")),
                    markdown_escape(step.get("current_solution")),
                    markdown_escape(", ".join(step.get("evidence_ids", []))),
                ]) + " |"
            )
        lines.extend([
            "",
            "### 蓝海市场 4P 差异",
            "",
            "| 维度 | 当前基线 | 差异选择 | 证据 |",
            "|---|---|---|---|",
        ])
        mix_labels = {"product": "产品", "price": "价格", "channel": "渠道", "promotion": "传播"}
        for key in ("product", "price", "channel", "promotion"):
            item = course_extension.get("marketing_mix_4p", {}).get(key, {})
            lines.append(
                "| " + " | ".join([
                    mix_labels[key],
                    markdown_escape(item.get("baseline")),
                    markdown_escape(item.get("differentiation_choice")),
                    markdown_escape(", ".join(item.get("evidence_ids", []))),
                ]) + " |"
            )

    lines.extend([
        "",
        "## 定位方案比较",
        "",
        "| 方案 | 目标用户 | 品类 | 差异 | 用户价值 | 独特性 | 成本 | 风险 | 状态 |",
        "|---|---|---|---|---:|---:|---:|---:|---|",
    ])
    for item in data["positioning_options"]:
        lines.append(
            "| " + " | ".join([
                markdown_escape(item.get("name")),
                markdown_escape(item.get("target_user")),
                markdown_escape(item.get("category")),
                markdown_escape(item.get("differentiation")),
                markdown_escape(item.get("user_value")),
                markdown_escape(item.get("competitive_uniqueness")),
                markdown_escape(item.get("execution_cost")),
                markdown_escape(item.get("risk_level")),
                markdown_escape(enum_label(item.get("status"))),
            ]) + " |"
        )

    lines.extend([
        "",
        "## 表达、产品、内容、价格、渠道与销售建议",
        "",
        "| 领域 | 行动 | 理由 | 优先级 | 负责人 | 周期 | 成功信号 | 证据 |",
        "|---|---|---|---|---|---|---|---|",
    ])
    for item in data["strategic_actions"]:
        lines.append(
            "| " + " | ".join([
                markdown_escape(enum_label(item.get("area"), ACTION_AREA_LABELS)),
                markdown_escape(item.get("action")),
                markdown_escape(item.get("rationale")),
                markdown_escape(enum_label(item.get("priority"))),
                markdown_escape(item.get("owner")),
                markdown_escape(item.get("horizon")),
                markdown_escape(item.get("success_signal")),
                markdown_escape(", ".join(item.get("evidence_ids", []))),
            ]) + " |"
        )

    lines.extend([
        "",
        "## 验证计划",
        "",
        "| 假设 | 受众 | 方法 | 指标 | 门槛 | 决策规则 |",
        "|---|---|---|---|---:|---|",
    ])
    for item in data["validation_plan"]:
        lines.append(
            "| " + " | ".join([
                markdown_escape(item.get("hypothesis")),
                markdown_escape(item.get("audience")),
                markdown_escape(item.get("method")),
                markdown_escape(item.get("metric")),
                threshold_display(item.get("threshold"), item.get("threshold_unit")),
                markdown_escape(item.get("decision_rule")),
            ]) + " |"
        )

    lines.extend([
        "",
        "## 证据台账",
        "",
        "| 编号 | 主张 | 来源 | 摘要 | 市场适配 | 独立 | 冲突 |",
        "|---|---|---|---|---|---|---|",
    ])
    source_titles = {item["source_id"]: item["title"] for item in data["sources"]}
    for item in data["evidence"]:
        lines.append(
            "| " + " | ".join([
                markdown_escape(item.get("evidence_id")),
                markdown_escape(", ".join(item.get("claim_ids", []))),
                markdown_escape(source_titles.get(item.get("source_id"))),
                markdown_escape(item.get("summary")),
                markdown_escape({"aligned": "匹配", "partial": "部分匹配", "mismatch": "不匹配", "unknown": "未知"}.get(item.get("market_fit"))),
                markdown_escape(item.get("independent")),
                markdown_escape(item.get("conflict")),
            ]) + " |"
        )

    lines.extend([
        "",
        "## 来源附录",
        "",
    ])
    for item in data["sources"]:
        source_ref = safe_source_display(item.get("url_or_file"))
        lines.append(
            f"- **{markdown_escape(item['source_id'])}** {markdown_escape(item['title'])}，"
            f"等级 {markdown_escape(item.get('grade'))}，时效：{markdown_escape(enum_label(item.get('freshness_status')))}，用途：{markdown_escape(item.get('intended_use'))}，"
            f"来源：{markdown_escape(source_ref)}"
        )
    lines.append("")
    return "\n".join(lines)


def html_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(data, ensure_ascii=False))
    for source in payload.get("sources", []):
        source["url_or_file"] = safe_source_display(source.get("url_or_file"))
    return payload


def render_html(data: dict[str, Any], template_path: Path, echarts_path: Path) -> str:
    try:
        template = template_path.read_text(encoding="utf-8")
        echarts_source = echarts_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"required render asset is missing: {exc.filename}") from exc
    required_markers = ("{{REPORT_TITLE}}", "{{REPORT_DATA}}", "{{ECHARTS_JS}}")
    missing = [marker for marker in required_markers if marker not in template]
    if missing:
        raise ValueError(f"report template is missing markers: {', '.join(missing)}")
    return (
        template.replace("{{REPORT_TITLE}}", html.escape(str(data["meta"]["report_title"]), quote=True))
        .replace("{{REPORT_DATA}}", safe_json_for_script(html_payload(data)))
        .replace("{{ECHARTS_JS}}", re.sub(r"</script", r"<\\/script", echarts_source, flags=re.IGNORECASE))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an offline positioning report bundle.")
    parser.add_argument("input", type=Path, help="Path to positioning report JSON")
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--echarts", type=Path, default=DEFAULT_ECHARTS)
    parser.add_argument("--strict", action="store_true", help="Refuse to render when validation warnings exist")
    args = parser.parse_args()

    try:
        raw = load_json(args.input)
        schema_errors = validate_against_schema(raw)
        semantic_errors, warnings = validate_report(raw)
        errors = schema_errors + semantic_errors
        if errors or (args.strict and warnings):
            for message in errors:
                print(f"ERROR: {message}", file=sys.stderr)
            if args.strict:
                for message in warnings:
                    print(f"WARNING: {message}", file=sys.stderr)
            return 1
        data = normalize_report(raw)
        report_html = render_html(data, args.template, args.echarts)
        report_markdown = render_markdown(data)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        if args.out.is_symlink():
            raise OSError("output directory must not be a symbolic link")
        args.out.mkdir(parents=True, exist_ok=True)
        atomic_write(args.out / "positioning-report.html", report_html)
        atomic_write(
            args.out / "positioning-report-data.json",
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        )
        atomic_write(args.out / "positioning-report.md", report_markdown)
    except OSError as exc:
        print(f"cannot write report bundle: {exc}", file=sys.stderr)
        return 2
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(json.dumps({
        "ok": True,
        "output_dir": str(args.out.resolve()),
        "files": ["positioning-report.html", "positioning-report-data.json", "positioning-report.md"],
        "warnings": warnings,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
