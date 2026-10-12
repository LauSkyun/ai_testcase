# Secondary 公平基线对照摘要

## 实验完整性

- 预期 Secondary 调用：20
- 已完成：0
- 失败：20
- 全部可配对：否
- Primary 调用：0
- 视觉调用：0
- 公平性不变量：通过
- 仅 Secondary 供应商变量不同：是

## 盲测说明

公开产物仅显示 Variant A / B。完成人工标注前不要打开 `_private/provider_mapping.json`。

## 变体汇总

| 变体 | 完成/预期 | Candidate 通过率 | 平均声称新增 | 平均 Top Blocker 保留率 | 字段完整率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 0/10 | - | - | - | - |
| B | 0/10 | - | - | - | - |

## 人工验收状态

当前为 `pending_human_annotation`。只有完成 `human_annotation_template.json` 后，才能计算有效新增率、重复率和高价值新增数，并决定是否切换默认 Secondary。
