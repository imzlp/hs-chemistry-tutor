# 规范化学概念模型（chem-concept-v1）

本文件说明 `data/canonical/` 的职责、字段语义和教学系统使用边界。模型的目标
不是把化学写成一句“标准答案”，而是让每个概念都具备明确的定义、范围、条件、
例外、证据来源和待复核状态。

## 1. 实体划分

### concept（规范概念）

文件：`data/canonical/concepts.jsonl`
主键：`concept_id`（形如 `chem_...`）

一个 concept 表示一个可独立教学、检索和评估的化学概念。它可以由多条教材
出现记录合并而来，但不能把不同概念仅因为名称相近就强行合并。

核心字段：

- `canonical_name`：规范名称；
- `aliases`：无歧义的别名；
- `concept_type`：概念、性质、过程、方法、表示、应用、历史、安全或跨学科；
- `definition`：定义及边界；
- `core_ideas`：适合教学拆分的核心命题；
- `representations`：化学式、方程式和记号；
- `examples` / `non_examples`：正例与反例；
- `relations`：前置、关联和易混概念 ID；
- `teaching`：学生解释、教师提示、教学顺序和类比；
- `misconceptions`：错误认识及纠正；
- `assessment`：常见题型、陷阱和生成提示；
- `provenance`：教材出现记录、指纹、书籍和章节；
- `quality`：审核状态、质量标记、修订记录和开放问题。

### occurrence（教材出现记录）

文件：`data/canonical/occurrences.jsonl`
主键：`occurrence_id`，等于原始 `kp_id`

occurrence 表示“某个教材位置出现了这个知识点”。它保留原始名称、教材引用、
定义摘要、教材范围和来源指纹。一个 concept 可以有多条 occurrence；因此：

```text
kp_id != concept_id
```

不要把 `kp_id` 当作唯一概念 ID，也不要在合并概念时删除 occurrence。

### relation（关系）

文件：`data/canonical/relations.jsonl`

每条关系保留来源 occurrence、来源 concept、关系类型、原始目标标签、解析状态
和目标 concept。关系类型目前包括：

- `prerequisites`：学习该概念前应掌握的内容；
- `related`：同层或跨主题关联，不表示严格先后。

`resolution_status`：

- `resolved`：唯一映射到当前规范概念；
- `unresolved`：当前概念表没有可唯一映射的节点；
- `ambiguous`：存在多个候选节点；
- `self_reference`：来源标签指向自身，不能作为有效前置边；
- `external_prior`：明确属于当前概念表之外的前置知识。

`external_prior` 不是“找不到就算外部”。只有经过判断、确实属于初中课程、
其他学科或当前课程表未覆盖的前置知识才使用。

### confusable pair（易混概念对照）

文件：`data/canonical/confusable-pairs.jsonl`

易混关系不是普通 `related`。每一对都包含：

- `dimensions`：比较维度；
- `distinction`：决定性区别；
- 双向的 `relations.confusable` ID。

教学系统应把“易混”用于诊断和追问，而不是只输出“A 和 B 不同”。

### review queue（复核队列）

文件：`data/canonical/review-queue.jsonl`

只要 concept 还有开放问题，就进入队列。问题代码包括：

- `formula_extraction_unverified`；
- `equation_extraction_unverified`；
- `boundary_extraction_unverified`；
- `unresolved_relation`；
- `ambiguous_relation`；
- `self_referential_relation`；
- `ambiguous_alias_omitted`；
- `scope_inferred_from_subtopics`（来源缺少可用 scope，按 subtopics 推断）；
- `scope_generic`（来源缺少可用 scope 和 subtopics，只保留概念类型级别说明）；
- `external_prior_relation`（属于外部前置知识，仍建议人工确认其教学定位）。

队列中的概念不是“不可用”，而是“不能被当成已审定的标准答案”。

### review sheet（全量复核工作表）

文件：`data/canonical/review-sheet.jsonl`

每个规范概念一行，记录字段完整性、scope 是否具体、已解析/未解析关系数量、
易混关系数量、问题代码和复核优先级。它用于证明所有 507 个概念都被同一套
规则检查过，不是只抽查了部分知识点。

### relation gap（关系缺口）

文件：`data/canonical/relation-gaps.jsonl`

按目标标签聚合未解析、歧义、自引用和外部前置关系，便于课程设计者决定：

1. 新增规范概念；
2. 添加无歧义别名；
3. 标记为真正的外部前置；
4. 保留为待复核缺口。

## 2. definition 字段

`definition.statement` 是概念的正面陈述，不能只写“某物质很重要”这类空话。

`definition.scope` 说明该定义适用于哪些对象、课程阶段或场景。它不是教材
栏目名，也不应包含“本节”“考点”等编辑语。

来源没有可直接使用的 scope 时，构建脚本会按概念类型和 subtopics 生成候选
范围，并标记 `scope_inferred_from_subtopics`；如果连 subtopics 也不存在，
则标记 `scope_generic`。这两种情况都必须由教师确认，不能把推断文本当作
教材原文或已经核实的课程边界。

`definition.conditions` 是成立条件，例如温度、浓度、状态、催化剂、溶液酸碱性。

`definition.exceptions` 是明确的反例或例外。例：

- 共价化合物不一定由独立分子构成；
- 难溶不等于完全不溶；
- 盐析通常可逆，但不能绝对化为“永不改变活性”。

`definition.boundary_notes` 用于放置不属于条件或例外的边界提醒，例如：

- 氢键不是典型共价键；
- 胶体整体电中性，但胶粒可能带电；
- 晶体熔沸点不能按固定类型顺序比较。

边界说明必须能帮助学生判断“什么时候不能这样用”，不能只是重复定义。

## 3. teaching 字段

`teaching.student_explanation` 面向学生，应尽量做到：

- 先给定义，再给条件和例外；
- 不出现“教师应强调”“考点”“本节”等课堂元语言；
- 不把类比当作证明；
- 不用“所有、唯一、一定”替代条件。

`teaching.teacher_notes` 面向教师，可以包含教学顺序、追问、板书建议和易错点。
它不应被直接拼接成学生答案。

`teaching.teaching_sequence` 是建议的教学步骤，不是事实断言。

`teaching.analogy.text` 是类比，`analogy.limitations` 必须说明类比不能推出
什么。教学系统引用类比时必须同时展示限制。

## 4. misconceptions 与 assessment

`misconceptions[].statement` 描述学生可能持有的错误认识；
`misconceptions[].correction` 给出可验证的纠正；
`source_occurrence_ids` 保留该误区来自哪些教材出现记录。

`assessment` 只提供题型、陷阱和练习生成提示，不是标准题库。自动生成题目时
必须另行校验答案、评分点和方程式。

## 5. quality 字段

- `review_status`：当前为 `machine_reviewed`；
- `human_verified`：当前全部为 `false`；
- `evidence_status`：当前为 `ai_textbook_summary_unverified`；
- `quality_flags`：来自受控词表的分流标记；
- `corrections`：P0/P1/P2 或 C1 修订记录；
- `open_issues`：仍需处理的问题；
- `issue_details`：问题代码、严重程度和说明。

`machine_reviewed` 不是“专家已经确认”。`confidence` 是来源生成置信度，
不是化学事实正确率。`resolved` 只表示关系标签成功映射，不表示关系本身一定
符合教学逻辑。

## 6. 当前未完成项

- 931 条关系仍未解析；
- 1 条关系存在多个候选；
- 28 条来源关系为自引用；
- 197 条关系被标为外部前置；
- 77 个概念的 scope 由 subtopics 推断，已进入复核队列；
- 当前没有保留旧版统一占位 scope；
- 公式和方程式均未完成结构化验证；
- 教材引用仍缺少版本、ISBN、原文摘录和逐句定位；
- 所有概念都需要高中化学教师按指定教材版本复核。

## 7. 下游使用建议

1. 检索时优先使用 `concept_id`，展示时保留 `occurrence_id` 作为出处。
2. 生成学生答案前检查 `quality.open_issues`，不要把开放问题静默隐藏。
3. 生成方程式前先走独立的结构化校验器，不要直接复用 `representations` 文本。
4. 讲易混概念时读取 `confusable-pairs.jsonl`，展示比较维度和区别。
5. 讲解类比时同时展示 `analogy.limitations`。
6. 任何自动生成的结论都应附带来源 occurrence 和 `human_verified` 状态。
