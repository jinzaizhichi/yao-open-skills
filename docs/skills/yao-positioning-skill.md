# Yao Positioning Skill

`yao-positioning-skill` 是一套证据驱动的定位诊断系统。它面向个人 IP、课程、产品、服务、公司品牌和企业再定位，把用户输入、市场研究、竞品比较、优势诊断和定位建议组织成一条可追溯的决策链。

## 适合什么时候用

- 需要形成一句话定位、差异化标签和品类表达。
- 需要理解目标用户当前如何看待主体与竞品。
- 需要比较直接竞品、间接替代、现状方案、不行动和行业标杆。
- 需要判断个人优势、产品能力或品牌资产能否成为可证明优势。
- 需要为公司品牌、产品发布、个人专家品牌或课程设计定位路线。
- 需要输出带证据、风险和验证计划的可视化定位报告。

## 理论基础

系统以《定位》的心智、品类、阶梯、聚焦、再定位和品牌延伸风险为主轴，并组合以下方法：

- 现代产品定位：竞争替代、独特属性、价值映射、最佳匹配用户和市场类别。
- 课程营销：目标人群、关键痛点、结果承诺和独特机制。
- 证据治理：事实、自述、推断、假设与建议分层，来源接受六项可信度检查。
- D6 优势诊断：用户相关、竞争稀缺、证据充分、可防守、战略匹配和表达聚焦。

## 输入方式

1. **引导问答**：Agent 每轮提出 1 至 3 个阻塞问题，并给出示例。
2. **附件资料**：公司介绍、产品资料、访谈记录、销售材料、合同边界等。
3. **官网与 URL**：官网、产品页、价格页、竞品页面与权威公开来源。
4. **混合输入**：将问答、附件和网址统一整理为 `intake-brief.json`。

系统先确认定位对象、决策目的、产品或服务、市场边界、目标用户假设和可核验来源。六项信息满足后进入正式研究。

## 主流程

1. 整理输入并运行准备度校验。
2. 选择本地、标准或深度研究模式。
3. 建立主张清单、竞争集合和证据台账。
4. 研究用户需求、竞品心智位置和市场空位。
5. 运行 D6 优势诊断与否决规则。
6. 生成 2 至 3 个定位选项并进行压力测试。
7. 形成一句话定位、推荐理由、风险和反证条件。
8. 生成 HTML、JSON、Markdown 三件套并执行成品审校。

## 输出物

- `positioning-report.html`：离线可视化报告，包含顶部固定导航、图表与打印样式。
- `positioning-report-data.json`：主张、来源、需求、竞品、优势、方案和验证计划的结构化事实源。
- `positioning-report.md`：无脚本降级版和长期审计记录。

## 质量与边界

- 信息未达到研究门槛时，系统继续补充资料。
- 关键主张需要权威、直接、及时且适配目标市场的证据。
- 推荐结论必须连接需求证据、竞争证据和能力证据。
- 证据不足的字段显示“证据不足”，图表不填充虚构值。
- 法律、财务、医疗等专业结论需要对应专业人员复核。
- 真实客户输入、人物案例、评测输出和生成报告不进入公开仓库。

## 系统说明报告

- [定位 Skill 系统说明报告](../../skills/yao-positioning-skill/reports/positioning-skill-system-overview-2026-07-16/index.html)

报告系统性介绍定位 Skill 的原理、理论、六层架构、AI 工作流、能力特点、使用边界、个人与公司场景、质量控制和演进方向。

## 入口文件

- [Skill 入口](../../skills/yao-positioning-skill/SKILL.md)
- [目录说明](../../skills/yao-positioning-skill/README.md)
- [理论体系](../../skills/yao-positioning-skill/references/theory-system.md)
- [输入与准备度门槛](../../skills/yao-positioning-skill/references/intake-and-readiness-gate.md)
- [竞品研究方法](../../skills/yao-positioning-skill/references/competitor-research-method.md)
- [来源可信度策略](../../skills/yao-positioning-skill/references/source-credibility-policy.md)
- [AI 工作流](../../skills/yao-positioning-skill/references/ai-workflow.md)
- [报告契约](../../skills/yao-positioning-skill/references/report-contract.md)
- [报告渲染脚本](../../skills/yao-positioning-skill/scripts/render-report.py)
