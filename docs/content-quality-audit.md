# 高中化学知识点数据质量审计

审计日期：2026-11-19
审计对象：`data/explicit/*.jsonl`、`data/teaching/*.jsonl` 及其规范概念层
数据规模：5 本教材，562 条 explicit，562 条 teaching，562 条 occurrence

## 一、当前结论

当前数据已经完成一轮“来源层纠错 + 规范概念层建模”，但还没有达到可以宣称
“无歧义、专家审定”的程度。

已经完成：

- 已修复 11 个 P0 事实错误、19 个 P1 内容问题和 38 个 P2 一致性问题；
- 101 个规范概念有基础内容覆盖，合并方程专项覆盖后共涉及 122 个概念级修订；
- 已把 562 条教材出现记录归并为 507 个规范概念；
- 已保留 `kp_id` 作为教材出现记录 ID，并生成稳定的 `concept_id`；
- 已生成 15 组易混概念对照，区分维度写入独立文件；
- 已生成复核队列和关系缺口清单，未完成的审核不会被隐藏；
- 已为 251 个概念中的 754 条化学式建立概念范围内的语法、类型和角色台账；
- 已对 56 组反应情境、122 条方程式建立逐条审核记录；
- 已对原 20 个方程抽取告警概念逐条复核并清除 `equation_extraction_unverified`；
- 已为 1371 个唯一关系标签建立逐条处置台账，明确保留 776 个真实缺口；
- 已生成 573 条教材定位记录，逐条标记页码和版本证据尚未核验。

仍然不能宣称：

- 没有教师逐概念签字确认；
- 没有教材出版社、版次、ISBN 和原文逐句定位；现有页码仍只是 AI 摘要声称；
- 方程式只完成部分原子/电荷机器复核，未认证反应条件、机理、状态符号和教材原文；
- 没有把 865 条未解析关系、29 条自引用关系和 1 条歧义关系变成可靠知识图谱；
- 关系审核台账虽然覆盖全部 1371 个标签，但其中 776 个仍是未找到合适规范概念的
  真实缺口，不能把“已建立台账”误写成“已全部解析”。

因此，所有规范概念当前都是：

```text
review_status = machine_reviewed
human_verified = false
evidence_status = ai_textbook_summary_unverified
```

## 二、数据分层

### 1. 来源层

`data/explicit/*.jsonl` 和 `data/teaching/*.jsonl` 保留教材摘要、教学讲解、
原始 `kp_id`、教材引用和原始质量标记。它们是“教材出现记录”，不是唯一概念。

### 2. 规范概念层

`data/canonical/concepts.jsonl` 使用 `concept_id`，把同一概念的多条教材出现
记录合并为一个可检索、可关联、可生成教学活动的对象。

`data/canonical/occurrences.jsonl` 保留每条 `kp_id` 到 `concept_id` 的映射，
因此不会因为合并概念而丢失教材出处。

### 3. 关系与复核层

`relations.jsonl`：来源层 `prerequisites` / `related_points` 的逐条解析结果。

`confusable-pairs.jsonl`：人工整理的易混概念对照，包含比较维度和决定性区别。

`relation-gaps.jsonl`：未解析、歧义、自引用和外部前置关系的聚合。

`review-queue.jsonl`：仍需人工处理的概念及问题代码。

## 三、已完成的重点修订

### P0 事实错误

本轮优先处理了会导致教学系统直接输出错误结论的问题，包括：

| 知识点 | 修订方向 |
|---|---|
| 氢键及其对物质性质的影响 | 明确氢键不是典型共价键，通常归入分子间作用力 |
| 脂肪族聚酰胺（锦纶） | 锦纶主链含酰胺键，不是聚酯；区分锦纶 66 与锦纶 6 |
| DNA 双螺旋结构 | 两条链反向平行，补充 A-T、G-C 配对 |
| 淀粉与纤维素结构 | 差异来自糖苷键、链构象和分子间作用力，不是单纯 n 值 |
| 铝及氧化铝的两性 | 铝与酸/碱反应生成盐和氢气；Al2O3 生成盐和水 |
| 乙醛银镜反应 | 修正久置银氨溶液的危险归因和安全操作 |
| 分子间作用力与氢键 | 删除晶体熔沸点的固定类型排序 |
| 化学电源与燃料电池 | 限定一次电池、效率和零排放的适用范围 |

完整清单以 `scripts/p0_content_overrides.json`、
`scripts/p1_content_overrides.json`、`scripts/p2_content_overrides.json` 为准。

本轮新增的 P0 修正包括鼠李糖分子式：`C6H12O5` 是鼠李糖，`C5H10O4`
是脱氧核糖，二者不能互换。该修正在概念 `kp_36b829a66fda` 对应的规范概念中
固化为回归检查。

### 规范概念层修订

`scripts/canonical_content_overrides.json` 对 101 个规范概念应用了基础内容
修订；`scripts/equation_content_overrides.json` 提供 30 个方程相关修订项，
合并后共覆盖 122 个概念。重点是：

- 给定义补充适用条件、例外和边界；
- 把“所有、唯一、一定、完全”等绝对化表述改为可检验的条件句；
- 区分“物质类别”与“具体性质”、“反应限度”与“反应速率”、“盐析”与“变性”；
- 将教师讲解中的课堂组织语与学生端解释分开；
- 对高风险概念补充“不能推出什么”的边界说明。

本轮额外收口了硝酸钝化、氢氧燃料电池的电解质环境、抗坏血酸抗氧化机理、
纤维素水解与炭化的区别、糖类检验条件、醇的断键位置、苯的物理性质，以及
高分子和键长的范围边界。`validate_canonical_model.py` 已把这些高风险修订
固化为回归检查，防止重建时静默回退。

重建时还发现并清理了“修正了定义、旧讲解仍保留错误”的跨字段冲突，例如金属
腐蚀的固定速率排序、肽键被说成蛋白质唯一的共价键、长周期新增元素全部为金属、
铁合金只按含碳量分类、分散系分类只依据粒径，以及取代反应一定生成无机小分子。
这些冲突既可能出现在 `core_ideas` 或 `teaching_sequence`，也可能出现在类比中，
因此本轮把概念级覆盖扩展到这些字段，并加入回归断言。

## 四、当前模型统计

```json
{
  "source_occurrences": 562,
  "canonical_concepts": 507,
  "manual_merge_groups": 37,
  "confusable_pairs": 15,
  "review_sheet_rows": 507,
  "review_sheet_priorities": {
    "high": 28,
    "medium": 479
  },
  "relations": {
    "resolved": 977,
    "unresolved": 865,
    "external_prior": 228,
    "self_reference": 29,
    "ambiguous": 1
  },
  "relation_gaps": {
    "labels": 927,
    "relations": 1123
  },
  "relation_review": {
    "labels": 1371,
    "reviewed_mappings": 32,
    "reviewed_gap_labels": 35,
    "partially_self_referential_labels": 10,
    "unreviewed_gap_labels": 776
  },
  "review_queue": 495,
  "blocking_concepts": 0,
  "scope_inferred_from_subtopics": 75,
  "formula_reviews": 754,
  "equation_reviews": 122
}
```

方程与教材定位的独立统计：

```json
{
  "equation_review": {
    "review_sets": 56,
    "equations": 122,
    "machine_mass_charge_checked": 105,
    "structural_reviewed": 17,
    "canonical_concepts_covered": 76,
    "source_occurrences_covered": 85
  },
  "formula_review": {
    "formula_reviews": 754,
    "canonical_concepts_with_formulas": 251,
    "unique_formula_strings": 164,
    "curated_concepts": 10
  },
  "textbook_locator": {
    "source_occurrences": 562,
    "locator_rows": 573,
    "publisher_verified": 0,
    "edition_verified": 0,
    "isbn_verified": 0,
    "quote_verified": 0
  }
}
```

`review_queue` 很大并不代表所有概念都“错误”。它同时包含：

- 来源关系标签尚未找到规范概念节点；
- 已审核公式/方程仍保留教材原文和精确页码未核验的证据缺口；
- 条件、例外和例子由机器抽取，需要教师确认；
- 75 个概念的 scope 由 subtopics 推断，尚未逐条对照教材原文；
- 别名存在歧义，已从公开别名表中移除；
- 来源关系指向自身，不能作为有效前置边。

未解析关系不会被强行塞进 `external_prior`。只有当前规范概念表确实没有独立
节点、且属于前置课程知识时，才标记为 `external_prior`。
外部前置关系会以独立的 `external_prior_relation` 问题代码进入复核队列，
不会和真正的内部关系缺口混在一起计数。

## 五、主要剩余风险

### 1. 知识图谱仍不完整

当前有 977 条关系已解析，但仍有 865 条未解析、29 条自引用和 1 条歧义。
主要原因是来源层使用自由文本标签，而规范概念表不一定存在同名节点。典型
缺口包括“化学平衡移动原理”、
“氧化还原反应配平”、“勒夏特列原理”、“交联反应”等。

这些缺口会保留在 `relation-gaps.jsonl`。关系审核台账覆盖全部 1371 个标签，
其中 776 个标签仍是未找到合适规范概念的真实缺口；教学系统不能把“已建立
标签台账”误写成“关系已经全部解析”。

### 2. 化学式与方程式只完成机器复核

`formula_validation` 已从“未处理”推进为：

```text
machine_classified_and_curated
```

754 条概念范围内的化学式已按分子式、缩合式、聚合物、通式、离子、元素符号
或指示剂通用记号分类，并记录其是否为中心物质、类别通式、对比物种等。这个
状态只表示语法和概念范围经过机器审核，不表示每个化学式都是该概念的中心
物质，也不表示教材使用完全相同写法。

`equation_validation` 为：

```text
partial_machine_mass_charge_and_structural_review
```

电化学、有机、无机与平衡情境的 122 条方程式已有逐条记录，其中：

- 105 条通过组成式层面的原子守恒和净电荷守恒；
- 17 条是聚合物或结构片段，只做结构审查，明确标为 `not_applicable`；
- 76 个规范概念已接入审核后的展示式；
- 原 20 个 `equation_extraction_unverified` 概念已完成逐条分类，确认其中
  9 个没有反应方程、9 个有真实方程、2 个为混合内容并已拆分。

机器校验不认证反应事实、条件、机理、状态符号、有效数字或教材原文。尤其是
电池半反应、有机反应条件和聚合物端基，仍必须按具体体系复核。

### 3. 证据不可逐句追溯

`data/review/textbook-locator.jsonl` 已把 562 条 occurrence 展开为 573 条
逐条定位记录，但所有出版社、版次、ISBN、原文和精确引文仍为 `null`。
现有页码只是 AI 摘要声称，不能证明具体定义句出现在指定页。正式上线前必须
取得教材实体或正式电子版，并逐条回填版权页与原文。

### 4. 教学层仍需教师复核

`teacher_notes` 保留课堂组织、类比和命题提示，适合教师备课，不应直接作为
学生端标准答案。`analogy.limitations` 已提示类比的边界，但仍需逐条检查类比
是否会诱导错误结论。

### 5. 高风险模块需要优先人工复核

- 电化学：原电池/电解池、阴阳极、盐桥、电极反应；
- 有机反应：取代/加成/消去、反应条件、同分异构；
- 糖类、蛋白质和核酸：结构层次、水解、变性与显色；
- 晶体结构：晶体类型、作用力、熔沸点比较；
- 实验安全：银氨溶液、浓硫酸、重金属盐、废弃物处理；
- 所有离子方程式和氧化还原方程式。

## 六、质量门禁建议

在接入自动答疑或自动生成题目之前，至少应满足：

1. 关键概念有人工审核记录，而不是只有 `machine_reviewed`；
2. 所有内部前置关系可解析，或有明确的 `external_prior` 说明；
3. 每个高风险概念都有条件、例外、反例和易混对照；
4. 高风险方程式通过配平、电荷、状态符号、条件和介质校验；
5. 教材引用可定位到版本、页码和原文；
6. 学生端解释不包含教师指导语、课堂组织和未限定范围的绝对化结论；
7. 对“所有、唯一、一定、完全、不可逆”等词建立自动回归检查。

## 七、复现方式

```bash
python3 scripts/apply_content_overrides.py \
  --overrides scripts/p0_content_overrides.json --write
python3 scripts/apply_content_overrides.py \
  --overrides scripts/p1_content_overrides.json --write
python3 scripts/apply_content_overrides.py \
  --overrides scripts/p2_content_overrides.json --write
python3 scripts/build_canonical_model.py
python3 scripts/build_formula_review.py
python3 scripts/build_equation_review.py
python3 scripts/build_canonical_model.py
python3 scripts/build_textbook_locator.py
python3 scripts/build_canonical_model.py
python3 scripts/validate_canonical_model.py --strict-schema
```

`validate_canonical_model.py` 会检查来源覆盖、概念 ID、别名唯一性、关系表
无损映射、复核队列、易混对照对称性、公式语法与概念覆盖、方程原子/电荷、
方程抽取审核、关系标签处置一致性、教材定位字段、JSON 重复键和四类审核台账的
严格 schema。

## 八、总结

这批数据已经从“分散的教材摘要”推进到“可追溯 occurrence + 规范 concept +
显式关系 + 易混对照 + 复核队列 + 公式/方程/关系三层审核 + 逐条教材定位台账”
的结构，
适合作为高中化学辅助教学系统的候选数据底座。

但它的正确性边界必须被系统显式继承：`machine_reviewed` 不是专家认证，
`resolved` 不是事实正确，公式分类不是物质身份认证，方程机器配平不是反应
事实认证，关系台账覆盖全部标签也不等于全部关系已解析，页码存在也不等于
教材原文已核验，`confidence` 更不是无歧义保证。正式教学上线前，仍应由高中
化学教师按明确教材版本完成逐概念、逐公式、逐方程和逐引文复核。
