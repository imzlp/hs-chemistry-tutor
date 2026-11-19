# 高中化学知识指南

这是一个可直接部署到 GitHub Pages 的纯静态教学原型。根目录的 `index.html`
在浏览器中读取规范概念、教材出现记录、公式/方程审核和关系处置台账，
提供学生视角、教师视角与证据边界展示。

## 目录

```text
index.html                  教学原型入口（静态，运行时 fetch JSONL）
app.css                     原型样式与响应式布局
app.js                      概念树、搜索、详情和审核状态交互
favicon.svg                 原型图标
data/
  manifest.json             教材清单
  explicit/*.jsonl          教材原始出现记录 (kp-explicit-ai-v1)
  teaching/*.jsonl          教材教学辅助记录 (kp-teaching-v1)
  canonical/
    concepts.jsonl          规范概念（唯一概念层）
    occurrences.jsonl       教材出现记录到规范概念的映射
    relations.jsonl         前置/关联关系的解析结果
    confusable-pairs.jsonl  人工整理的易混概念对照
    review-sheet.jsonl      全部规范概念的系统化复核工作表
    review-queue.jsonl      仍需复核的规范概念
    relation-gaps.jsonl     未解析/外部/歧义关系聚合
    manifest.json           模型统计与质量状态
  review/
    formula-review.jsonl            概念范围内化学式逐条审核
    formula-review-manifest.json    化学式审核统计与限制
    equation-review.jsonl           高中化学方程逐条审核
    equation-extraction-review.jsonl 方程抽取问题逐概念复核
    relation-review.jsonl           关系标签逐条处置台账
    textbook-locator.jsonl          教材逐条待核验定位台账
    manifest.json                   方程与抽取审核统计
    textbook-locator-manifest.json  教材版本与 ISBN 阻塞状态
  schema/
    chem-concept-v1.schema.json
    chem-confusable-pair-v1.schema.json
    chem-formula-review-v1.schema.json
    chem-equation-review-v1.schema.json
    chem-equation-extraction-review-v1.schema.json
    chem-relation-review-v1.schema.json
    chem-textbook-locator-v1.schema.json
docs/
  canonical-model.md
  content-quality-audit.md
  equation-review.md
  formula-review.md
  textbook-verification.md
scripts/
  build_canonical_model.py
  build_formula_review.py
  build_equation_review.py
  build_textbook_locator.py
  validate_canonical_model.py
  apply_content_overrides.py
  formula_utils.py
  equation_balance.py
  formula_content_overrides.json
  equation_review_catalog.json
  equation_extraction_review.json
  equation_content_overrides.json
  relation_review_catalog.json
  canonical_confusable_pairs.json
```

## 数据分层

- `data/explicit` 和 `data/teaching` 保留教材出现记录及其 `kp_id`，是来源层；
- `data/canonical` 是面向教学系统的规范概念层，使用 `concept_id`；
- 一个规范概念可以对应多条教材出现记录，不能把 `kp_id` 当作唯一概念 ID；
- `data/canonical/review-queue.jsonl` 明确列出仍需人工复核的概念；
- `data/review/formula-review.jsonl` 逐概念记录化学式语法、表示类型和角色，
  不把概念范围内出现的化学式自动当作中心物质；
- `data/review/equation-review.jsonl` 区分机器原子/电荷校验与结构审查；
- `data/review/equation-extraction-review.jsonl` 保留方程抽取问题的逐概念处置；
- `data/review/relation-review.jsonl` 对每个关系标签给出映射、外部前置、自引用
  或真实缺口的显式结论；
- `data/review/textbook-locator.jsonl` 逐条保留页码，但不伪造版本、ISBN 或原文；
- `human_verified=false`、`evidence_status=ai_textbook_summary_unverified`
  表示当前只是机器辅助审校，不是专家审定。

模型字段、关系状态和教学使用边界见
[`docs/canonical-model.md`](docs/canonical-model.md)，数据质量基线见
[`docs/content-quality-audit.md`](docs/content-quality-audit.md)。方程复核边界见
[`docs/equation-review.md`](docs/equation-review.md)，化学式审核规则见
[`docs/formula-review.md`](docs/formula-review.md)，教材定位状态见
[`docs/textbook-verification.md`](docs/textbook-verification.md)。

## 教学原型

当前原型已经接入以下数据层：

- `data/canonical/concepts.jsonl`：按规范概念展示定义、边界、教学步骤、
  易错点、考法和证据；
- `data/review/formula-review.jsonl`：展示化学式的类型、角色和规则修订状态；
- `data/review/equation-review.jsonl`：展示方程情境、介质、条件、机器校验和
  结构审查状态；
- `data/canonical/relations.jsonl` 与 `relation-review.jsonl`：可点击跳转已解析
  关系，同时显式列出未解析、歧义、自引用和外部前置缺口；
- `data/review/textbook-locator.jsonl` 的边界由页面统一说明：页码来自 AI 摘要，
  出版社、版次、ISBN 和原文仍未核验。

原型支持学生/教师视角切换。教师视角额外显示备课提示、命题提示、开放问题、
高优先级复核概念和内部记录 ID；学生视角不展示教师备课内容，但始终保留
“未人工审定”的证据提示。学习进度只保存在浏览器 `localStorage`，不是服务端
学习记录。

## 更新与校验

在仓库根目录执行：

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

覆盖文件会先写入来源层的 explicit/teaching 记录，再重建规范概念层。
不要手工修改 `data/canonical/*.jsonl`；它们应始终由脚本重新生成。
若来源没有可直接使用的 `definition.scope`，构建脚本会按概念类型和
`subtopics` 生成候选范围，并在 `quality.issue_details` 中留下
`scope_inferred_from_subtopics` 复核标记；不会把推断文本伪装成教材原文。

## 本地预览

```bash
python3 -m http.server 8000
# 打开 http://127.0.0.1:8000
```

请通过 HTTP 服务访问；直接双击 `index.html` 会因浏览器限制无法 fetch JSONL。

## 使用边界

当前数据适合做检索、课程编排、错题诊断和教学文案生成的候选底座，不应直接
作为自动答疑的唯一事实来源。754 条概念范围内化学式已完成机器语法与角色
分类，其中 10 个概念的 24 条记录经过规则修订；122 条方程中 105 条通过
原子/电荷机器校验，17 条只做结构审查；1371 个关系标签已逐条处置，但仍有
776 个标签属于真实未审阅缺口，865 条关系边尚未解析。573 条教材定位记录的
出版社、版次、ISBN 和原文仍为空。上述内容仍需高中化学教师逐项复核后才能
用于正式教学。
