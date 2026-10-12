# Secondary 公平基线对照摘要

## 实验完整性

- 预期 Secondary 调用：10
- 已完成：10
- 失败：0
- 全部可配对：是
- Primary 调用：0
- 视觉调用：0
- 公平性不变量：通过
- 对照变量：single_profile
- 仅预定变量不同：是

## 盲测说明

公开产物仅显示 Variant A / B。完成人工标注前不要打开 `_private/provider_mapping.json`。

## 变体汇总

| 变体 | 完成/预期 | Candidate 通过率 | 声称/准入新增 | 最低 Top3 保留率 | 原始/准入字段完整率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 10/10 | 0.0% | 1.60/0.00 | 100.0% | 100.0%/- |

## 人工验收状态

当前为 `pending_human_annotation`。只有完成 `human_annotation_template.json` 后，才能计算有效新增率、重复率和高价值新增数，并决定是否切换默认 Secondary。
