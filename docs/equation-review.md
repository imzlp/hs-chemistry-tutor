# 电化学与有机反应方程式复核

复核日期：2026-11-19

复核范围：电化学、有机化学中的 46 组反应情境，共 107 条方程式。

## 1. 结论

当前状态是“机器辅助复核”，不是专家审定，也不是教材原文认证。

```text
review_status = machine_reviewed
human_verified = false
evidence_status = ai_textbook_summary_unverified
```

完成情况：

- 93 条方程式通过组成式层面的原子守恒和净电荷守恒机器校验；
- 14 条聚合物、通式或结构片段方程式只做结构审查，不进行单一分子计量配平；
- 107 条均有明确的介质、条件、角色、教学说明、来源 occurrence 和来源页码；
- 107 条均保留 `source_verification.publisher/edition/isbn/quote/quote_locator = null`；
- 65 个规范概念接入审核方程；
- 20 个未覆盖概念仍保留 `equation_extraction_unverified`，没有被静默隐藏。

每条 `checks` 还显式记录：

```text
conditions = metadata_only
state_symbols = not_validated
```

即条件和状态符号只是随记录携带的教学元数据，没有被机器校验或人工签字确认。

机器校验不能证明：

- 该反应在指定条件下一定发生；
- 反应机理或电子转移步骤正确；
- 状态符号、浓度、温度、催化剂和电极材料已经逐条核实；
- 教材使用了完全相同的写法；
- 页码、版次、ISBN 或原文引文已经核验。

## 2. 数据文件

```text
scripts/equation_review_catalog.json             结构化方程式复核目录（非人工签字）
scripts/equation_balance.py                      保守的组成式原子/电荷校验器
scripts/build_equation_review.py                 生成逐条方程审核记录
data/review/equation-review.jsonl                107 条方程审核记录
data/review/manifest.json                        方程审核统计和限制
data/schema/chem-equation-review-v1.schema.json  严格 JSON Schema
```

`data/canonical/concepts.jsonl` 中已覆盖概念会获得：

- `representations.equations`：统一后的教学展示式；
- `quality.equation_review_ids`：对应的 `eqr_...` 审核 ID；
- `quality.equation_validation_status`：
  - `machine_mass_charge_checked`；
  - `structural_reviewed`；
  - `machine_and_structural_reviewed`；
  - `not_reviewed`；
- `quality.issue_details` 中的 `equation_textbook_evidence_unverified`。

## 3. 两层复核

### 3.1 `machine_mass_charge_check`

适用于可以用一个组成式表达的方程式。审核器解析元素、括号、下标、分数系数、电荷、电子和状态符号，并检查：

- 左右两侧每种元素的原子数；
- 左右两侧净电荷；
- 电子项是否按电荷计入。

审核记录保留原始 ASCII `machine_expression`，校验器必须能够重新计算。教学展示式与校验式分开，避免为了解析而破坏下标、电荷和结构式。

通过该项只表示“原子与净电荷计量自洽”，不表示反应事实已经认证。

### 3.2 `structural_review`

适用于：

- 加聚物和缩聚物；
- 含统计聚合度 `n` 的聚合物；
- 含 `R` 基的通式；
- 肽键、聚合物端基等结构片段；
- 不能把整条聚合物当作单一分子配平的表示。

这类记录会明确显示：

```text
mass_balance = not_applicable
charge_balance = not_applicable
machine_expression = null
```

不能把它统计成“已配平”或“已机器验证”。

## 4. 本轮修正

本轮确认并修正了以下高风险问题：

| 问题 | 处理 |
|---|---|
| 葡萄糖银镜反应的校验产物写成 `C6H13NO6` | 改为葡萄糖酸铵 `C6H15NO7` |
| 葡萄糖生物氧化使用 `C6H12O6(s)` | 改为细胞水溶液环境 `C6H12O6(aq)` |
| 甘氨酸与 HCl 产物未表现离子形式 | 改为 `[H3N+CH2COOH]Cl-`，并校验净电荷 |
| 燃烧式的水写成液态但未说明状态语境 | 明确表示冷却至常温后的聚集状态 |
| 燃料电池核心表述保留“通常 >80%” | 改为理论效率与实际效率分开 |
| 电解池核心表述写成电子经溶液离子导电 | 明确电子只走外电路，溶液由离子导电 |
| 析氢腐蚀把 O2 列入必要化学式 | 删除，并说明析氢/吸氧可竞争 |
| 电极反应书写残留截断的放电顺序 | 重写为受条件约束的定性工具 |
| 纤维素水解仍写“稀硫酸或酶” | 统一为较强酸并加热，或纤维素酶 |
| 原电池用镁铝氢氧化钠电池说明正极反应 | 改用燃料电池和 PbO2 正极活性物质 |
| 乙醇与钠被笼统归为“广义取代” | 明确断 O–H 键，不属于卤代烃式亲核取代 |
| 缩聚端基被说成引发剂残留 | 明确来自未反应官能团，受配比、转化率和封端方式影响 |

## 5. 使用规则

教学系统读取方程时必须同时读取：

- `conditions`；
- `medium`；
- `set_notes`；
- `ambiguity_notes`；
- 当前方程的 `note`；
- `quality.equation_validation_status`；
- `quality.issue_details` 中的证据缺口。

禁止：

- 只截取 `display` 而丢弃介质和条件；
- 把 `structural_reviewed` 显示为“已配平”；
- 把 `machine_mass_charge_checked` 显示为“教材原文已核验”；
- 把 `machine_reviewed` 显示为“教师审定”；
- 根据总反应反推唯一的一组电极反应而不说明介质。

## 6. 复现

```bash
python3 scripts/build_canonical_model.py
python3 scripts/build_equation_review.py
python3 scripts/build_textbook_locator.py
python3 scripts/build_canonical_model.py
python3 scripts/validate_canonical_model.py --strict-schema
```

第一次 canonical 重建提供概念与 occurrence 映射；方程审核生成后再重建一次，把审核方程写回规范概念层。
