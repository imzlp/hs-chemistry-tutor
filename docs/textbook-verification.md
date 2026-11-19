# 教材版本、ISBN 与逐条定位台账

更新日期：2026-11-19

## 1. 当前结论

仓库目前没有五本教材的封面、版权页、版次页、ISBN 页或可引用的印刷原文。
因此本轮只能建立“逐条待核验定位台账”，不能把现有 AI 摘要页码升级为已核验
教材引用。

当前状态：

```text
verification_status = unverified_ai_summary_pages_only
review_status = unverified
human_verified = false
evidence_status = ai_textbook_summary_unverified
publisher = null
edition = null
isbn = null
quote = null
quote_locator = null
```

已生成的定位范围：

- 5 本教材；
- 562 条 occurrence；
- 573 条 `textbook_refs` 定位记录；
- 每条记录同时关联 `locator_id`、`occurrence_id`、`concept_id`、书籍、章节、
  小节、AI 摘要页码和来源类型。

## 2. 数据文件

```text
scripts/build_textbook_locator.py                   生成逐条定位台账
data/review/textbook-locator.jsonl                  573 条待核验定位记录
data/review/textbook-locator-manifest.json           教材级统计与阻塞输入
data/schema/chem-textbook-locator-v1.schema.json     严格 JSON Schema
```

每条记录都保留 AI 摘要所声称的页码，但同时标记：

```json
{
  "page_ranges_inherited_from_ai_summary": true,
  "verification_status": "unverified_ai_summary_pages_only"
}
```

这不是“页码为空”，而是“页码存在，但只达到 AI 摘要声称级别”。教学系统若
直接把它显示成教材页码，会制造虚假的可追溯性。

## 3. 为什么不能现在补 ISBN

教材名称不足以唯一确定版本。至少还缺：

- 出版社；
- 版次或印次；
- 出版年份；
- ISBN；
- 册次与模块对应关系；
- 封面或版权页扫描；
- 与当前章节、页码对应的印刷本或正式电子版。

在没有版权页证据时填写 ISBN 属于猜测，不能进入知识库。当前实现选择保留
`null`，并在 manifest 中记录 0 条已验证元数据。

## 4. 升级为已核验引用的条件

一条 locator 只有同时满足以下条件，才允许改变状态：

1. 有可追溯的教材实体或正式电子版；
2. 从版权页确认出版社、版次、印次、出版年份和 ISBN；
3. 建立 PDF 页与印刷页码的映射；
4. 在指定页找到支撑该知识点的原句；
5. 记录原文 `quote` 和可复查的 `quote_locator`；
6. 由第二名复核者独立确认；
7. 将 `verification_status`、`review_status`、`human_verified`、`verified_at`
   和 `verified_by` 一并更新；
8. 重新运行严格校验。

仅有出版社官网书目信息，仍不足以证明具体页码和原文。

## 5. 下游使用规则

当前台账可用于：

- 给编辑分配逐条核验任务；
- 统计每本教材、每章、每节的待核验引用；
- 把概念追溯到 occurrence 和 AI 摘要页码；
- 在界面上明确显示“页码未核验”。

当前台账不可用于：

- 生成“教材第 X 页原文为……”的答案；
- 作为版权引用或考试命题依据；
- 证明某个定义句确实出现在指定页码；
- 证明五本教材的具体版本。

## 6. 复现

```bash
python3 scripts/build_textbook_locator.py
python3 scripts/validate_canonical_model.py --strict-schema
```

校验器会逐条比对 locator 与 occurrence 的书籍、章节、小节和页码，并拒绝任何
在缺少证据时填写的出版社、版次、ISBN、原文或复核人。
