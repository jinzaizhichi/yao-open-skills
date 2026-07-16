#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass


MAX_VISIBLE_TAGS = 4


TAG_LABELS = {
    "ai": "AI",
    "ai-security": "AI 安全",
    "allocation": "资源配置",
    "audit": "审查",
    "automation": "自动化",
    "bayesian": "贝叶斯",
    "business-model": "商业模式",
    "catalog": "目录",
    "charts": "图表",
    "competition": "竞争",
    "copyright": "版权",
    "dast": "DAST",
    "decision-analysis": "决策分析",
    "demand-analysis": "需求分析",
    "diagnosis": "诊断",
    "docx": "DOCX",
    "education": "教育",
    "evidence": "证据",
    "excel": "Excel",
    "expert-learning": "专家学习",
    "export": "导出",
    "first-principles": "第一性原理",
    "forecast": "预测",
    "game-theory": "博弈论",
    "governance": "治理",
    "headers": "文件头",
    "historical-behavior": "历史行为",
    "html": "HTML",
    "industry-analysis": "行业分析",
    "investment": "投资",
    "kelly": "凯利公式",
    "keywords": "关键词",
    "negotiation": "谈判",
    "notes": "笔记",
    "pdf": "PDF",
    "personalization": "个性化",
    "principal-contradiction": "主要矛盾",
    "product": "产品",
    "positioning": "定位",
    "prior-hygiene": "先验校验",
    "publishing": "发布",
    "reading-analytics": "阅读分析",
    "reporting": "报告",
    "research": "研究",
    "sast": "SAST",
    "security": "安全",
    "skills": "Skill",
    "strategy": "战略",
    "tutorials": "教程",
    "validation": "验证",
    "visual-reporting": "可视化报告",
    "visualization": "可视化",
    "visuals": "配图",
    "web-security": "网站安全",
    "weread": "微信读书",
    "word-cloud": "词云",
    "workflow": "工作流",
}


@dataclass(frozen=True)
class CatalogCategory:
    slug: str
    title: str
    short_title: str
    description: str


CATEGORIES = [
    CatalogCategory(
        slug="decision-strategy",
        title="决策与战略",
        short_title="决策",
        description="把不确定选择、资源配置、竞争反应和复杂局面整理成可复盘的行动报告。",
    ),
    CatalogCategory(
        slug="business-research",
        title="商业与研究",
        short_title="商业",
        description="用于商业模式、产品需求、行业学习和专家知识结构化。",
    ),
    CatalogCategory(
        slug="learning-content",
        title="学习与内容",
        short_title="学习",
        description="把主题、资料、阅读数据和学习者画像生产成教程、报告或可视化内容。",
    ),
    CatalogCategory(
        slug="engineering-governance",
        title="工程与治理",
        short_title="治理",
        description="面向安全审查、版权头、公开合集同步和 Skill 发布治理。",
    ),
]


CATEGORY_BY_SLUG = {
    "yao-bayesian-skill": "decision-strategy",
    "yao-business-skill": "business-research",
    "yao-copyright-skill": "engineering-governance",
    "yao-crux-skill": "decision-strategy",
    "yao-demand-skill": "business-research",
    "yao-doctor-skill": "engineering-governance",
    "yao-expert-skill": "business-research",
    "yao-gametheory-skill": "decision-strategy",
    "yao-interpreter-skill": "engineering-governance",
    "yao-kelly-skill": "decision-strategy",
    "yao-open-skills-sync": "engineering-governance",
    "yao-positioning-skill": "decision-strategy",
    "yao-tutorial-skill": "learning-content",
    "yao-websecurity-skill": "engineering-governance",
    "yao-weread-skill": "learning-content",
}


def tag_label(tag: str) -> str:
    return TAG_LABELS.get(tag, tag)


def visible_tag_labels(tags, limit: int = MAX_VISIBLE_TAGS):
    labels = [tag_label(tag) for tag in tags]
    visible = labels[:limit]
    has_more = len(labels) > limit
    return visible, has_more


def category_for_skill(skill) -> CatalogCategory:
    category_slug = CATEGORY_BY_SLUG.get(skill["slug"], "engineering-governance")
    return next(item for item in CATEGORIES if item.slug == category_slug)
