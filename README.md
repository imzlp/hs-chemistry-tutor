# 高中化学知识指南

这是一个可直接部署到 GitHub Pages 的纯静态知识库。根目录的 `index.html`
在浏览器中读取 `data/` 下的 JSONL 并展示教材知识点。

## 目录

```text
index.html                  前端（静态，运行时 fetch JSONL）
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
  schema/
    chem-concept-v1.schema.json
    chem-confusable-pair-v1.schema.json
docs/
  canonical-model.md
  content-quality-audit.md
scripts/
  build_canonical_model.py
  validate_canonical_model.py
  apply_content_overrides.py
  canonical_confusable_pairs.json
```

## 数据分层

- `data/explicit` 和 `data/teaching` 保留教材出现记录及其 `kp_id`，是来源层；
- `data/canonical` 是面向教学系统的规范概念层，使用 `concept_id`；
- 一个规范概念可以对应多条教材出现记录，不能把 `kp_id` 当作唯一概念 ID；
- `data/canonical/review-queue.jsonl` 明确列出仍需人工复核的概念；
- `human_verified=false`、`evidence_status=ai_textbook_summary_unverified`
  表示当前只是机器辅助审校，不是专家审定。

模型字段、关系状态和教学使用边界见
[`docs/canonical-model.md`](docs/canonical-model.md)，数据质量基线见
[`docs/content-quality-audit.md`](docs/content-quality-audit.md)。

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

## 使用边界

当前数据适合做检索、课程编排、错题诊断和教学文案生成的候选底座，不应直接
作为自动答疑的唯一事实来源。方程式配平、电荷守恒、状态符号、教材原文定位
和实验安全仍需高中化学教师逐项复核后才能用于正式教学。
