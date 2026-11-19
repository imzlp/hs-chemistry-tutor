# 化学式概念范围审核（chem-formula-review-v1）

审核日期：2026-11-19

审核范围：`data/canonical/concepts.jsonl` 中 `representations.formulas`
非空的 251 个规范概念，共 754 条 concept×formula 记录、164 个不同化学式串。

## 1. 当前结论

当前状态是“机器语法分类 + 少量规则修订”，不是物质身份认证，也不是教材
原文认证。

```text
review_status = machine_reviewed
human_verified = false
evidence_status = ai_textbook_summary_unverified
formula_validation = machine_classified_and_curated
```

完成情况：

- 754 条记录全部通过受控语法检查；
- 730 条采用 `machine_syntax_and_role_classification`；
- 24 条记录、涉及 10 个概念采用 `curated_formula_context` 规则修订；
- 251 个含公式概念均关联 original occurrence 和教材摘要页码；
- 所有 `publisher/edition/isbn/quote/quote_locator` 仍为 `null`。

`formulas` 的语义是“该概念教材摘要或规范化讲解中出现过的化学式集合”，
不是“该概念中心物质的完整列表”。角色由独立的 `role` 字段表示。

## 2. 数据文件

```text
scripts/formula_utils.py                         化学式语法、类型和展示规则
scripts/formula_content_overrides.json             受控的概念级角色/修正目录
scripts/build_formula_review.py                   生成逐条化学式审核台账
data/review/formula-review.jsonl                  754 条 concept×formula 记录
data/review/formula-review-manifest.json          统计、来源状态和限制
data/schema/chem-formula-review-v1.schema.json    严格 JSON Schema
```

## 3. 类型与角色

当前 `formula_kind` 分布：

| 类型 | 数量 | 说明 |
|---|---:|---|
| `molecular_formula` | 703 | 可写成单一组成式的分子或物质 |
| `condensed_formula` | 35 | 结构简式或常用缩合表示 |
| `polymer_formula` | 5 | 含统计聚合度的聚合物表示 |
| `generic_formula` | 4 | 类别通式，如 `CnH2n+2` |
| `ion_formula` | 4 | 带电荷的离子式 |
| `element_symbol` | 2 | 元素符号本身 |
| `indicator_generic` | 1 | `HIn` 这类指示剂通用记号 |

`protected_placeholder` 也是支持的类型，但当前公式台账中没有占位符记录。
占位符在内容字段中必须原样保留，不能替换成猜测值。

当前 `role` 分布：

| 角色 | 数量 | 语义 |
|---|---:|---|
| `mentioned_species` | 730 | 只表示概念范围内提到的相关物种 |
| `representative_substance` | 13 | 该概念的代表性具体物质 |
| `contrast_example` | 6 | 用于对比或边界说明的物种 |
| `class_general_formula` | 4 | 代表一类物质的通式 |
| `indicator_equilibrium` | 1 | 指示剂平衡中的通用记号 |

`mentioned_species` 不自动等于中心物质。下游不能仅凭某化学式出现在
`formulas` 中，就断言“该概念就是这种物质”或“反应一定由它发生”。

## 4. 本轮修正

本轮重点修复了会直接改变含义的表示问题：

| 问题 | 处理 |
|---|---|
| 糖类概念把鼠李糖写成 `C5H10O4` | 鼠李糖改为 `C6H12O5`；`C5H10O4` 保留为脱氧核糖并明确区分 |
| `CnH` 被截断 | 恢复为 `CnH2n+2`、`CnH2n` 等完整通式 |
| 糖类通式缺少含氧形式 | 补充 `CnH2nO` 并限定为通式示意 |
| 淀粉/纤维素使用裸 `C6H10O5` | 统一为聚合物表示 `(C6H10O5)n` |
| `HIn` 被当作具体分子式 | 标为 `indicator_generic`，只用于指示剂平衡示意 |
| 钠与水概念混入 `CuSO4`、`Na2SO4` | 移除与中心反应无关的物种 |
| 受保护占位符被改写 | 原样保留，不猜测真实值 |

这些修正固化为回归约束；后续重建如果重新引入截断通式、裸聚合物单元或错误
糖类分子式，严格校验会失败。

## 5. 不能推出什么

公式记录不能证明：

- 该物质在教材指定页以同样写法出现；
- 该物质就是概念的唯一下定义对象；
- 该化学式对应的聚集状态、异构体或实验条件；
- 通式中的 `n`、`m` 有唯一数值；
- 离子式的电荷在指定介质中一定占主导；
- `HIn` 指某一个具体指示剂。

机器语法通过也不认证化学式一定存在或符合高中教材习惯写法。高风险公式仍需
教师结合教材原文复核。

## 6. 下游使用建议

1. 读取 `formula-review.jsonl`，按 `concept_id + formula` 使用，不要只取
   概念级 `formulas` 数组。
2. 显示化学式时优先使用 `display_formula`，同时保留原始 `formula` 供检索。
3. 解释通式、聚合物和指示剂时显示 `formula_kind` 与 `note`，避免把示意式
   说成具体分子。
4. 生成题目或反应式前检查 `role`，不要把 `mentioned_species` 当作中心物质。
5. 任何教材引用都必须继续查 `data/review/textbook-locator.jsonl`，并保留
   `human_verified=false` 与 `evidence_status=ai_textbook_summary_unverified`。

## 7. 复现与校验

```bash
python3 scripts/build_canonical_model.py
python3 scripts/build_formula_review.py
python3 scripts/build_equation_review.py
python3 scripts/build_canonical_model.py
python3 scripts/build_textbook_locator.py
python3 scripts/build_canonical_model.py
python3 scripts/validate_canonical_model.py --strict-schema
```

校验器会检查化学式语法、类型分类、显示形式、概念覆盖、原始 occurrence
覆盖、来源字段是否被伪造为空值以外的内容，以及公式台账与规范概念的双向
引用。
