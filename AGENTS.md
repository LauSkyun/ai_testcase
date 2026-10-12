# AGENTS.md

本文件用于约束在 `D:\project\script\ai_agents\RAD` 内工作的代理行为。目标是让后续代理在不反复翻代码的情况下，能快速完成运行、排查、文档维护与小规模功能调整。

## 项目定位

- 这是一个游戏需求文档审查工具，输入通常是 `.docx` 需求文档、数值文档或混合文档。
- CLI 入口是 `review.py`。
- 核心流程在 `rad_review/`。
- 默认输入目录是 `requirements/`，支持旧的平铺 `.docx` 和新的 `requirements/<项目名>/*.docx` 项目文件夹样式。
- 默认输出目录是 `reports/`。

## 首选运行命令

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

加载 PowerShell 环境变量：

```powershell
. .\env.local.ps1
```

标准运行命令：

```powershell
python review.py --input requirements --game 小鸡 --output reports --require-model
```

严格校验命令（主分析 + 综合校验器）：

```powershell
python review.py --input requirements --game 小鸡 --output reports --review-mode strict --require-model
```

无模型排查命令：

```powershell
python review.py --input requirements --game 小鸡 --output reports --extract-only
```

多款游戏测试分组命令：

```powershell
python review.py --input requirements --auto-group --output reports --extract-only
```

查看参数帮助：

```powershell
python review.py --help
```

调试阶段批量对比多份已生成报告：
```powershell
python report_debug_summary.py --reports-root reports 20260720_145550 20260722_104757
```

## 环境变量约定

优先参考：

- `env.example.ps1`
- `env.example.cmd`

关键变量：

- `AI_BASE_URL`
- `AI_API_KEY`
- `AI_MODEL`
- `AI_VISION_BASE_URL`
- `AI_VISION_API_KEY`
- `AI_VISION_MODEL`
- `AI_WIRE_API`
- `AI_VISION_WIRE_API`
- `AI_SEED`（可选，模型服务支持 seed 时用于稳定复跑）

工作要求：

- 涉及模型接入、参数名、默认行为的改动时，必须同步更新 `README.md` 与对应的 `env.example.*`。
- 如果视觉模型回退逻辑、文本模型回退逻辑发生变化，也要同步更新说明文档。

## 代码结构

- `review.py`：参数解析、实例化 `ReviewAgent`、输出 CLI 结果。
- `rad_review/agent.py`：主流程调度，串联解析、图像分析、文本审查、strict 校验、调试工件缓存与报告写出。
- `rad_review/docx_reader.py`：发现文档、解析段落/表格、提取图片、写出 manifest。
- `rad_review/model_client.py`：兼容 OpenAI 风格的文本与视觉接口。
- `rad_review/prompts.py`：提示词与消息构造。
- `rad_review/report.py`：审查结果归一化、稳定化、Markdown/JSON 输出。
- `rad_review/run_logger.py`：运行日志封装。

## 目录处理规则

- `requirements/` 是默认输入目录；若用户未特别说明，优先假设从这里读取 `.docx`。
- 输入目录同时兼容两种样式：旧的平铺文件名方式，以及新的 `requirements/<项目名>/*.docx` 项目文件夹方式；若存在项目文件夹，优先按第一层项目文件夹分组。
- 如果 `requirements/` 同时存在多款游戏文档，优先使用 `--game <游戏名>` 跑单款游戏，或用 `--auto-group` 测试批量分组；不要默认把多款游戏混成一份报告。
- `reports/` 是生成目录，包含时间戳子目录与 `latest/` 快照。
- `--auto-group` 的批次根目录必须生成 `group_run_summary.json`，记录每款游戏的完成、警告或失败状态。单款 primary 模型在重试耗尽后失败时，应记录失败并继续下一款，禁止让整个批次提前中断；批次最终返回非零退出码。
- `strict` 模式除最终 `review_report.*` 外，还会额外生成 `review_report_pre_audit.*`，用于比较综合校验前后的差异。
- `strict` 模式还会生成 `review_report_diff.*`，用于快速查看评分变化、阻塞项变化以及问题的新增/移除/调整。
- `reports/.cache/image_analysis/` 是图片解析缓存目录，用于减少同一图片复跑时的视觉模型波动；单款运行和 `--auto-group` 全游戏批次都必须复用这个报告根目录缓存，禁止把缓存落到时间戳子目录。
- 单次运行目录内的 `model_artifacts/` 保存文档 hash、review/audit messages 和原始模型响应，便于比较同一文档多次分析的差异。
- `report_debug_summary.py` 只读取这些已生成的报告目录，用于调试阶段检查工件完整性、原始模型 JSON、finding 必填字段、图片状态、candidate 诊断与问题漂移；传入多次全游戏目录时应按输入文档签名配对同一款游戏，不应因不同游戏混在汇总中而跳过稳定性比较；它不应修改历史报告内容。
- `reports/`、`reports/latest/`、`__pycache__/`、`.tmp_docx_classify/` 都应视为运行产物区域，除非任务明确要求，否则不要手工改里面的历史结果。
- 如果任务涉及结果验证，优先新跑一份时间戳目录，不要直接修补旧报告。

## 修改约束

- 优先保持 Windows 友好，命令示例默认提供 PowerShell 版本。
- 涉及 CLI 参数的变更时，必须同时检查 `review.py`、`README.md`、`AGENTS.md`、`env.example.ps1`、`env.example.cmd`。
- 涉及输出文件名、输出目录结构、运行日志字段的变更时，必须同步更新 `README.md`。
- 新增功能若会影响“忘记运行命令”的场景，应优先补充到 `README.md` 的“你现在最可能要用的命令”或“常用命令”部分。
- 涉及“当前输入文档独立分析”“跨文档结论判定”之类的审查规则时，主实现必须落在 `rad_review/prompts.py` 和 `rad_review/report.py`；`AGENTS.md` 只记录维护约束，不作为唯一行为来源。

## 占位符与配置值审查口径

- `[001]`、TBD、待配置、待填写、示例值、默认值，以及概率、倍率、阈值、上下限、最大/最小赔付等具体配置值未填，默认视为团队正常配置流程，不作为风险问题。
- 上述内容不得单独进入 finding、Top Blocker、缺失信息、质量备注、测试点或评分扣分项；不得仅因字段名涉及赔付、概率或倍率就包装成高风险。
- 只有当前文档直接证明已给规则或公式互相冲突、结算口径矛盾、出现除零/死锁，或主流程在不依赖具体配置值时仍不可执行，才审查该实际冲突；问题根因不得写成“占位符未填”。
- 调整此口径时必须同步更新 `rad_review/prompts.py`、`rad_review/reporting/` 下的确定性过滤规则和 `tests/test_report.py`；不得只修改本文件。

## 验证优先级

本项目优先使用以下方式验证：

1. `python review.py --help`
2. `python -m unittest discover -s tests -v`
3. `python review.py --input requirements --game 小鸡 --output reports --extract-only`
4. `python review.py --input requirements --auto-group --output reports --extract-only`
5. 若已配置模型，再执行 `python review.py --input requirements --game 小鸡 --output reports --require-model`

说明：

- 由于模型接口依赖外部服务，网络不可用或密钥缺失时，不应把纯模型问题误判为代码逻辑问题。
- 正式文本模型调用默认在首次瞬时故障后重试 `3` 次（最多请求 `4` 次），通过 `--model-retries` 配置；只重试超时、网络错误、HTTP 5xx、408、409、425、429 等可恢复故障。`dual_pass` 的 secondary 重试耗尽后继续使用 pipeline；primary 重试耗尽后由单款运行抛错，交给 `--auto-group` 记录并跳过。
- 在没有模型配置的环境里，至少保证 `--help`、`--game <游戏名> --extract-only` 和 `--auto-group --extract-only` 可用。

## 文档维护规则

- 用户可直接依赖 `README.md` 找到运行命令，因此 README 必须优先保证命令可直接复制使用。
- 文档默认使用中文，与当前项目使用习惯保持一致。
- 若新增脚本、入口命令、环境变量、输出工件或目录职责，必须同步更新本文件和 `README.md`。

## Git 与提交说明

- 当前目录未检测到 `.git` 仓库；不要默认假设可以执行 Git 提交、分支或日志命令。
- 如果后续该目录初始化为 Git 仓库，再遵循上层全局提交规范。
- 未明确要求时，不额外定义本项目自己的提交格式，避免与全局规范冲突。
## 模型探活

- 切换 `AI_MODEL` 或 `AI_WIRE_API` 后，优先先跑一次最小探活，再决定是否正式审查：

```powershell
python review.py --probe-model --timeout 30
```

- 这个命令不解析 `.docx`，只验证当前 `AI_BASE_URL`、`AI_API_KEY`、`AI_MODEL`、`AI_WIRE_API` 是否能完成最小文本请求。
- 当 `--review-mode fusion` 时，这个命令会分别验证 `AI_PRIMARY_*` 与 `AI_SECONDARY_*` 两套文本模型配置，而不是只探单一 `AI_*`。
- 探活输出应明确区分是 `primary` 还是 `secondary` 失败，并区分缺配置、超时和普通请求失败。
- 如果 `--probe-model` 成功，但正式审查仍失败，再优先排查长上下文、供应商稳定性、网关限流或上游流式转发问题。
## Claude 协议说明

- 若供应商要求某个文本模型“走 Claude 协议”，则把 `AI_WIRE_API` 设为 `claude`，不要再用 `responses` 或 `chat_completions`。
- `claude` 分支会调用 Anthropic 兼容的 `POST /v1/messages`，并使用 `x-api-key` / `anthropic-version` 请求头。
- 此时 `AI_MODEL` 应填写供应商要求的 Claude 侧模型名，不应继续沿用类似 `glm_model` 这样的本地占位名。
- 若视觉模型仍走 OpenAI 兼容接口，`AI_VISION_WIRE_API` 保持原配置即可。

## Fusion 模式补充

- `--review-mode fusion` 表示双模型主副融合评审。
- 主评审模型使用 `AI_PRIMARY_*`：
  - `AI_PRIMARY_BASE_URL`
  - `AI_PRIMARY_API_KEY`
  - `AI_PRIMARY_MODEL`
  - `AI_PRIMARY_WIRE_API`
  - `AI_PRIMARY_SEED`（可选）
- 副评审模型使用 `AI_SECONDARY_*`：
  - `AI_SECONDARY_BASE_URL`
  - `AI_SECONDARY_API_KEY`
  - `AI_SECONDARY_MODEL`
  - `AI_SECONDARY_WIRE_API`
  - `AI_SECONDARY_SEED`（可选）
- 视觉模型仍然沿用 `AI_VISION_*` 全局配置，不拆双份。
- `fusion` 模式下，最终评分默认沿用主评审模型；只有当副评审补进 `3` 个及以上唯一高风险问题时，才允许最终评分下调 `1` 档。
- `model_artifacts/` 会额外生成：
  - `primary_review_messages.json`
  - `primary_raw_model_response.txt`
  - `secondary_review_messages.json`
  - `secondary_raw_model_response.txt`
  - `fusion_merge_summary.json`

## Dual Pass 模式补充

- `--review-mode dual_pass` 是一个独立测试模式，不复用 `fusion` 的“第二份完整报告 merge”逻辑。
- `dual_pass` 使用 `AI_PRIMARY_*` 作为主模型，`AI_SECONDARY_*` 作为副模型；`--probe-model --review-mode dual_pass` 同样需要分别探活这两套文本模型配置。
- `dual_pass` 的共享输入底座是 `model_artifacts/shared_review_input.json`：
  - 主模型基于这份 shared input 产出首版报告。
  - 副模型基于同一份 shared input + 主模型首版报告做复核、补漏和候选成稿。
- `dual_pass` 第一阶段采用“双主报告 + 摘要页”：
  - `review_report.md` / `review_report.json`：摘要页与索引页
  - `review_report_pipeline.*`：沿现有整理管线生成的版本
  - `review_report_candidate.*`：副模型候选成稿
  - `secondary_review_advice.*`：副模型对主模型质量的建议文档
- `dual_pass` 额外写入的调试工件包括：
  - `model_artifacts/shared_review_input.json`
  - `model_artifacts/primary_review_messages.json`
  - `model_artifacts/secondary_review_messages.json`
  - `model_artifacts/primary_raw_model_response.txt`
  - `model_artifacts/secondary_raw_model_response.txt`
  - `model_artifacts/dual_pass_summary.json`

## Dual Pass 当前维护约定

- `dual_pass` 当前对外默认报告已经切换为 `review_report.md` / `review_report.json`，它表示“本次默认采用的最终报告”，不再固定表示摘要页。
- `dual_pass` 的摘要页 / 索引页改为：
  - `review_report_index.md`
  - `review_report_index.json`
- `review_report_pipeline.*` 仍表示主模型首版报告经过现有整理管线后的版本。
- `review_report_candidate.*` 仍表示副模型候选成稿经过现有稳定化与完整性校验后的版本。
- `secondary_review_advice.*` 仍用于承载副模型的质量评估、补漏建议、证据不足提醒和候选稿 readiness 说明。

- 是否默认采用 `candidate`，必须走代码门槛判断，当前至少包括：
  - `candidate_report` 可解析且合法
  - 当前运行没有额外 warning
  - `quality_assessment.ready_for_direct_output = true`
  - `candidate_readiness.ready_for_direct_output = true`
  - 两个 readiness 结论一致
  - 若 `quality_assessment.suggestion_level = "high"`，则只有在三个 readiness 未全部通过、或 candidate 未达到结构直出门槛时才阻断默认切换
  - `traceability_status = complete`
  - `candidate_high_signal_demotion_without_support = false`
  - `candidate_overcompressed = false`
- 任何门槛未通过时，默认最终报告必须回退为 `pipeline`，并把失败原因写入索引页和 `model_artifacts/dual_pass_summary.json`。

- 为降低副模型“过度重写 / 过度合并”带来的追踪困难，副模型返回应尽量带上 `candidate_lineage`：
  - `kept`
  - `added`
  - `merged`
  - `dropped`
- 若某个 `missed finding` 被吸收到 kept 问题而不再独立落盘，对应 kept 项还应显式带上：
  - `absorbed_missed_issue_ids`
- 相关统计和诊断会出现在：
  - `lineage_counts`
  - `traceability_status`
  - `readiness_conflict`
  - `candidate_structure_drift`
  - `candidate_block_reasons`
  - `candidate_block_reason_categories`
  - `candidate_high_signal_demotion_without_support`
  - `candidate_high_signal_demotion_titles`
  - `candidate_overcompressed`
  - `candidate_overcompressed_reason`
  - `lineage_counts_raw`
  - `lineage_counts_materialized`
  - `candidate_added_materialization_status`
  - `advice_candidate_structure_mismatch`
  - `advice_claimed_absorbed_but_materialized_separately`
  - `advice_claimed_added_but_not_materialized`
  - `materialized_missed_without_added`
  - `trace_warning`
- 若 `candidate_lineage` 缺失但 candidate 与 primary 基本同构，标记为 `traceability_status = minimal`，只保留为可浏览候选稿，不建议默认切换。
- 若 `candidate_lineage` 缺失且 candidate 相对 primary 出现明显结构漂移，标记为 `traceability_status = missing`，默认阻断 candidate 切换。
- 若两个 readiness 结论冲突，必须统一降为 `false`，并在建议文档与索引页显式记录。
- `lineage_counts_raw` 表示副模型原始声称的 lineage 数量；`lineage_counts_materialized` 表示最终 candidate 实际落盘后的数量，排查 candidate 漏落盘时优先看这两个字段是否一致。
- `candidate_added_materialization_status` 用于判断副模型声明的 `candidate_lineage.added` 是否真的进入最终 candidate。
- `advice_candidate_structure_mismatch` 用于判断副模型对 candidate 结构的说明是否与最终 candidate 实际落盘一致；若为 `true`，默认阻断 candidate 切换。
- `advice_claimed_absorbed_but_materialized_separately` / `advice_claimed_added_but_not_materialized` / `materialized_missed_without_added` 用于快速定位“lineage 声称”和“candidate 落盘结果”之间的协议漂移。
- `dual_pass` 下凡是副评审补充的问题，最终报告里都应显式带上：
  - `finding_source = secondary_reviewer`
  - `finding_source_label = 副评审补充`
  - `source_model = <副模型名>`

- 后续如果继续调整 `dual_pass` 的默认切换门槛、索引页字段或 lineage 协议，必须同步更新：
  - `README.md`
  - `AGENTS.md`
  - `tests/test_dual_pass.py`

## Dual Pass 当前收敛策略（2026-06）

- 本期只在 `dual_pass` 内显式禁用 `cross_document_issues` 分区，不影响 `fast` / `strict` / `fusion`。
- `dual_pass` 产出的报告仍保留 `cross_document_issues: []` 以兼容 schema，但所有问题应回填到原维度 `dimensions[*].findings`。
- `merge_dual_pass_review_report()` 当前只允许做“原维度补漏 + 备注记录”，不要再在这条链路里做激进合并、跨区搬运或基于副模型建议改分。
- 副模型候选稿应尽量贴主模型的 `issue_id`、标题、维度、问题顺序与切分方式；只有确认主模型漏项时才新增 finding。
- 对 `candidate_lineage.kept` 映射的问题，若副模型明确修正标题、严重度、阻塞级别或正文判断，最终 candidate 必须物化这些修正；没有充分依据的高信号降级继续由 `candidate_high_signal_demotion_without_support` 门槛阻断。
- `review_report_index.json` 与 `model_artifacts/dual_pass_summary.json` 中的 `cross_document_section_disabled` 可视为这一期 dual_pass 收敛策略是否生效的快速检查点。
## Dual Pass 新诊断字段补充（P0/P1）

- 新增 `candidate_merged_materialization_status` / `candidate_merged_materialization_missing_ids`，用于判断副模型声明的 merged 问题是否真的进入最终 candidate。
- 新增 `candidate_structurally_ready`，用于表达 candidate 是否已经通过结构、证据、追踪、命名等直出门槛。
- 新增 `candidate_blocked_only_by_editorial_judgment`，用于区分“结构已可用，但当前仍仅因质量判断或 readiness 判断而未默认切换”的情况。
- 新增 `suggestion_level_conflict`，用于暴露“副模型把 `suggestion_level` 评成 `high`，但三个 readiness 已全部为 `true`”的语义冲突。
- 新增 `suggestion_level_override_applied`，用于标记系统是否已将这类 `suggestion_level` 冲突视为编辑性评语过重，并放行 candidate 默认切换。
- 新增 `candidate_contains_multiroot_kept_findings` / `candidate_multiroot_kept_titles`，用于暴露 candidate 中仍保留的多根因 kept 问题。
- 新增 `candidate_high_signal_demotion_without_support` / `candidate_high_signal_demotion_titles`，用于暴露 candidate 是否在缺少明确依据时下调了 primary 的高信号核心问题。
- 新增 `candidate_overcompressed` / `candidate_overcompressed_reason`，用于暴露 candidate 是否靠过度收缩问题数和大幅改写共享问题来变得更乐观。
- `ready_for_direct_output` 在 `dual_pass` 下表示“报告本身是否已达到可直接输出给业务 / 产品 / 研发阅读的质量”，不是“文档中的产品问题是否已经全部确认完成”。

## 阶段一公平基线：Secondary Replay

- 公平比较不同 Secondary 时使用 `--secondary-replay-from`，不得分别重跑两套完整 `dual_pass`。
- 回放必须复用同一份 `shared_review_input.json`、`primary_review_messages.json`、`primary_raw_model_response.txt` 与冻结后的 `frozen_primary_report.json`；禁止重新解析 DOCX/图片、调用视觉模型或调用 Primary。
- 命名供应商使用 `AI_PROVIDER_<名称>_*`，例如 `AI_PROVIDER_QWEN_*` 与 `AI_PROVIDER_DEEPSEEK_*`；回放不得要求修改当前激活的 `AI_PRIMARY_*` / `AI_SECONDARY_*`。
- 阶段一标准规模为 5 款游戏、2 个 Secondary、每个重复 2 次，共 20 次 Secondary 调用。`--secondary-repeats` 不得低于 2。
- 公开汇总和人工标注模板只允许显示 Variant A/B；A/B 必须在每批实验中随机分配，不能按 CLI 参数顺序固定映射，实际模型映射只写入 `_private/provider_mapping.json`。
- 人工标注前必须把完整 summary、manifest、frozen Primary、Secondary 原始 messages/响应、证据包、完整 advice、协议和准入诊断放在 `_private`。公开 `blinded/` 只保留已清除 profile/协议标识的报告与 advice；公开 summary、manifest 和 annotation template 不得出现 `protocol_profile`、`processing_profile`、`phase2_variant_ids`、证据包 ID、profile/model 名称或可直接识别 profile 的自动验收区块。
- 完整内部汇总固定为 `_private/secondary_benchmark_internal.json`，完整内部标注项固定为 `_private/human_annotation_internal.json`；公开标注模板只保留 A/B、待判断正文和当前 `change_type` 所需人工标签。added 使用原七项标签；phase3 challenge 使用 `target_correct/valid/evidence_locatable/actionable/should_split`；phase3 correction 使用 `target_correct/accurate/supported/safe_to_apply`。finalize 必须在人工判断锁定后，用公开标签回填内部标注项，再生成完整最终验收结果。
- 输出固定落到 `reports/secondary_benchmarks/<时间戳>/`，不得刷新或覆盖普通运行的 `reports/latest/`，也不得修改历史源报告。
- `secondary_benchmark_summary.json` 必须证明每款游戏的共享输入、Primary 原始输出、Primary messages、冻结 Primary report、Secondary messages 和 temperature 一致，并记录预期/完成/失败调用数。
- `human_annotation_template.json` 必须覆盖每个 Secondary 声称新增的问题，并预留 `valid`、`duplicate`、`unsupported`、`overstated`、`understated`、`multiroot`、`actionable` 字段。
- 人工盲标完成后使用 `--secondary-benchmark-finalize` 校验所有字段；调用未全部配对、公平性不变量未通过或存在任何空标注时必须失败，全部完成后生成 `human_annotation_results.json` 并回写汇总人工指标。
- 盲标既可直接填写生成模板，也可在同目录用 `human_annotation_decisions.json` 按 `annotation_id` 提交判断；决策文件有重复 ID、未知 ID 或缺少标签时必须拒绝收口。
- 任一回放失败时继续完成其他配对，最终标记 `all_calls_paired = false` 并返回非零退出码。
- 模型已成功返回但 JSON 解析失败时，必须保留原始响应；可用 `--secondary-benchmark-reprocess` 在零模型调用条件下用保存的原始响应重建整批结果和指标，不得因此重新请求任何已完成配对。
- 修改回放 CLI、产物结构、公平性不变量或盲测字段时，必须同步更新 `README.md`、`AGENTS.md`、`env.example.ps1`、`env.example.cmd` 与 `tests/test_secondary_benchmark.py`。

## 阶段二：Qwen 同模型 Secondary 协议收敛

- 当前生产主线保持 `Qwen Primary + Qwen Secondary`；普通 `dual_pass` 默认使用 `phase2` Secondary profile。
- `baseline` 必须冻结阶段一原提示词，供同模型旧/新协议 A/B；不得因继续修改 phase2 而同步漂移。
- 同模型协议 A/B 使用一个 `--secondary-provider qwen` 和两个 `--secondary-profile baseline/phase2`；两边必须使用相同 endpoint、model、wire API、seed、temperature 和 frozen Primary，唯一变量只能是 prompt/profile。
- phase2 Secondary 的职责是结构化补漏、反证和纠错，不是自由重写第二份报告；Candidate 必须以 Primary 为骨架。
- phase2 `missed_findings` 必须包含唯一所属的 `audit_key`、可定位证据、独立根因、单元素 `root_causes`、最近 Primary 问题去重说明、单根因计数与 `fact_check`；high/block_dev/block_test 必须提供 `severity_basis`。
- `fact_check` 必须显式记录 claim type、原文规则检查、兼容解释检查和 confirmed 结论；missing_rule 还要记录已检查的可定位范围。存在合理兼容解释时，不得把问题按 direct conflict 物化。
- phase2 使用 `coverage_schema_version=2`，先输出固定五项 audit、十二个 control 的 `coverage_ledger`，再生成新增问题；数量、顺序、合法状态、数组字段、核验证据和理由均须确定性校验，`confirmed_add` 与 `missed_findings` 必须按 candidate ID + audit key + control key 双向一一对应，每个 control 最多新增一个独立根因。账本不合法时禁止物化 Secondary 新增并强制 Candidate 回退；`candidate_inputs_sanitized` 不得绕过账本门槛。benchmark 记录 ledger 完整率、合法率、confirmed audit/control key 及复跑重合率。
- phase2 V2.1 必须基于冻结 `shared_review_input` 和 Primary 报告生成十二张确定性 control 证据卡；每张卡最多保留两条原文证据候选和两条 Primary 覆盖候选，并提供 control 定义与禁止混写范围。Secondary 固定按“原文状态 → 反证 → Primary 覆盖 → 最终状态”决策，不得跳步。
- V2.1 证据包必须带 SHA-256 `evidence_packet_id`，Secondary 必须在 `review_notes` 回显 `protocol_profile=phase2_v2_1; evidence_packet_id=<hash>`。benchmark 必须记录协议修订、包 ID、单次回显结果与变体回显率；V2.1 的 `phase2_acceptance` 要求回显率 100%，历史 V2 回放不得因缺少该字段被追溯判失败。
- V2.1 每次回放必须落盘 `model_artifacts/phase2_control_evidence_packet.json`。保存响应重处理必须读取并复用原始 `secondary_review_messages.json`，禁止用当前 Prompt 重建历史消息或改写真实 message hash；历史 phase2 消息标记为 `phase2_legacy` 且不追溯要求 V2.1 回显。复制进派生目录但与实际协议不符的陈旧证据包必须移除。
- 当前生产 phase2 协议为 V2.2 delta-only。Secondary 只负责输出固定十二 control 的 coverage ledger、missed findings、反证与质量意见；禁止要求或使用模型生成的 `candidate_report`、`candidate_lineage`、`candidate_readiness`。
- phase2 Prompt 必须使用独立的 compact delta baseline，不得继承 Primary 的评分量表、六维完整报告要求、通用 checklist 或 8–15 个问题数量目标；允许零新增。`baseline` profile 必须继续冻结阶段一完整提示词，不能因 phase2 迭代而漂移。
- V2.2 必须向模型提供完整的 `missed_findings` 嵌套字段和 JSON 类型模板；`fact_check.searched_locations` 必须为字符串数组，布尔字段必须为 JSON 布尔值，不得只给顶层字段名或使用模糊自然语言替代类型契约。
- V2.2 Candidate 必须由系统以 Primary pipeline 加已准入 Secondary 增量确定性生成，自动生成 kept/added lineage，并继续锁定 Primary 评分、评分理由和 Top 3。建议文档与摘要必须记录 `candidate_generation_mode=deterministic_primary_plus_admitted_delta`；模型对 Primary 的原始质量评价单独保存在 `primary_quality_assessment`。
- V2.2 不得放宽 coverage ledger、同 control Primary 引用、证据、单根因或严重度准入门槛。系统确定性生成 Candidate 只能消除重写漂移，不能掩盖或修复 Secondary 的跨 control 映射错误。
- 普通 `dual_pass` 与 benchmark 均必须落盘实际 `phase2_control_evidence_packet.json`，并精确校验 `review_notes` 最后一项的 `protocol_profile=phase2_v2_2; evidence_packet_id=<hash>`。回显缺失、位置错误或不匹配时 `phase2_protocol_gate` 硬失败，Secondary 增量不得进入 Pipeline/Candidate。
- V2.2 必须基于模型原始顶层字段按白名单检查 delta-only；返回 `candidate_report`、`candidate_lineage`、`candidate_readiness` 或其他未允许字段，即使为空对象也视为协议违规并回退 Pipeline。解析器后补的兼容默认字段不得误判为模型原始返回。
- V2.2 每个 control 的 reason 必须按 `source_state → counterevidence → primary_coverage → final` 顺序完整输出；状态枚举、顺序或 `final` 与 control status 不一致时 ledger 硬失败。
- V2.2 `phase2_acceptance` 必须额外要求 `phase2_protocol_gate_pass_rate=100%`、`phase2_delta_only_compliance_rate=100%`、`deterministic_candidate_generation_rate=100%`。
- 当前阶段二 `high_added_root_overlap_min=0.25`；该稳定性门槛只降低高价值根因复跑重合率的最低要求，不得联动放宽 schema、ledger、协议、人工准确率、有效新增数、证据、单根因或严重度门槛。
- 历史 V2/V2.1/V2.2 保存响应离线重处理时必须继续按原始 messages 识别真实协议修订，直接复用每格已保存的 `phase2_control_evidence_packet.json`，禁止用当前 Prompt 或当前证据卡代码重新计算包 ID、追溯改写协议身份；协议证据包 ID、message hash 和回显结论必须保持不变。历史消息识别为 legacy 时应移除不属于实际协议的陈旧证据包。
- phase2 可安全归一化不改变新增结论的账本格式漂移：清空 `covered_by_primary` 中与 Primary ID 完全相同的冗余 candidate ID；基于冻结共享输入为 `not_applicable` 补入漏填的实际文档名/全文证据；V2.2 中仅当真实 Primary ID 经程序证明属于同一 control 时，把非物化的 `no_issue/advice_only + same_control` 归一化为 `covered_by_primary`；若非物化 control 的 same-control 引用被程序证明无效，则过滤无效 Primary ID，全部无效时清空引用、改回 `not_covered`，并按已声明的 `source_state` 保守落为 `no_issue` 或 `advice_only`；`not_applicable` 中不改变结论的 `source_state=not_applicable`、`primary_coverage=not_applicable` 分别归一化为 `missing`、`not_covered`。所有归一化必须记录在 `coverage_ledger.protocol_repairs`；`confirmed_add`、candidate 映射、证据和严重度不得借此放宽。
- phase2 V2 的 `covered_by_primary` 必须引用真实存在且涉及同一 control 的 Primary issue；跨控制面引用必须以 `primary_control_mismatch` 拒绝，禁止用假数据隔离、零赔付、开奖快照等不相关问题覆盖本金扣款节点。
- 当前 phase2 生产与回放处理必须要求 `coverage_schema_version>=2`；历史 V1 响应可解析但必须以 `coverage_schema_version_too_old` 回退，不得计入 V2 合法率。`phase2_acceptance.coverage_schema_v2_rate` 必须为 100%。
- 仅当五个 audit 与十二个 control 的名称、数量和顺序完全匹配 V2 固定结构时，允许对漏填的顶层版本号做安全推断，并记录 `inferred_coverage_schema_version:2_from_complete_control_shape`；部分 controls 或近似结构不得推断。
- phase2 新增项进入 pipeline 前必须逐项经过确定性准入。缺字段、证据无法定位、与 Primary 重复、多根因、事实核验未确认、低置信或严重度依据不足时，只写入 advice，不允许物化。
- phase2 单根因检查必须把扣款与派奖、奖池负值下限与单局赔付封顶分别处理；统计时间窗口只有在对象、指标、范围和执行阶段一致时才能判冲突；已有倍率上限/MAX_MUL/强制0倍等相对边界时，除非证明其不参与结算或与公式冲突，否则不得直接判“最大赔付完全缺失”。
- V2 benchmark 的稳定根键优先使用固定 `audit_key + control_key`；不得继续用临时 issue ID 或 `CORE_BET_CONFIG_MISMATCH` 等宽泛分类衡量十二个 control 的复跑重合。精确文档名加“全文”可作为 missing_rule 的负向检索范围，“未明确说明”不得触发已有明确规则门槛。
- phase2 control 隔离必须阻断：扣款时点混入幂等/断线恢复、资金失败补偿混入奖池负值下限/熔断、单局封顶混入数值表公式错误。原文已给出点击消耗货币、结算后余额增加或复用中台统一流程时，不得继续以“完全缺失”高风险物化。
- phase2 `machine_multiroot` 只统计准入后仍由 Secondary 引入的多根因 finding；Primary 既有混合问题被 Candidate 保守保留时单独记录 `preserved_primary_multiroot_finding_count`，不得作为 Secondary 新增质量失败。
- 只有一份 requirement/numeric 文档时可把 evidence 的通用文档别名安全解析为真实文件名；多份同类文档时不得猜测。
- phase2 Candidate 的评分和评分理由锁定为 Primary；Secondary 不拥有改分权。
- phase2 Candidate 每次必须保留 Primary Top 3 中至少两个同根因问题；低于 `2/3` 时强制回退 pipeline。
- phase2 Candidate 构建后应优先锁定并回指 Primary Top 3，避免模型只改写标题就造成保留率误判。
- 构建 phase2 Candidate 前必须移除准入失败的 missed finding、candidate finding 和对应 lineage.added；成功清洗后，单个坏新增不应连带否决其余合格 Candidate。清洗状态记录为 `candidate_inputs_sanitized`。
- 诊断至少写出 `phase2_admission`、`phase2_admission.coverage_ledger`、`candidate_inputs_sanitized`、`primary_top3_retention`、`primary_top3_retention_gate_passed`、`candidate_score_locked_to_primary` 与逐项拒绝原因。
- `--secondary-reprocess-profile phase2` 只允许对已保存响应做离线准入重算，不得改变原始响应的真实 `protocol_profile` 或 prompt hash。
- 离线重处理历史基准必须由工具自动复制到 `<原目录>_reprocessed_<时间戳>` 派生目录，并写出 `reprocess_manifest.json`；禁止原地覆盖输入基准和唯一历史证据。
- benchmark 人工指标必须同时提供准入前/准入后的有效率、重复率、高价值数和有效召回率，避免通过少报问题虚增准确率。
- phase2 benchmark 必须生成 `phase2_acceptance`，把机器门槛、人工门槛、稳定性、阻断原因和 pending 项显式化；任何机器门槛已失败时状态不得仅显示为 pending，只有全部门槛通过才允许 `eligible_for_next_stage = true`。
- 阶段二回退测试必须覆盖 Secondary 502 重试耗尽、超时、非法 JSON、Top 3 丢失、准入拒绝和 `--auto-group` 继续下一款。
- 修改 phase2 prompt、准入门槛、协议 profile、公平性校验或诊断字段时，必须同步更新 `README.md`、本文件、`tests/test_dual_pass.py` 与 `tests/test_secondary_benchmark.py`。

## 阶段二同期盲测结论与阶段三边界（2026-08-14）

- 同期盲测原始批次为 `reports/secondary_benchmarks/20260814_103002`，最终零调用验收批次为 `reports/secondary_benchmarks/20260814_103002_reprocessed_20260814_115005`；20/20 Secondary 调用配对，Primary/视觉调用为 0。
- 当前冻结 `phase2_v2_2` 相对冻结 baseline 的人工有效新增率为 100%（17/17）对 52.63%（10/19）；V2.2 准入后 15/15 有效、高价值 12 个、重复/证据不足/夸大/多根因均为 0，高价值复跑重合率 37.5%。
- 最终 `phase2_acceptance.status=passed`、`eligible_for_next_stage=true`。V2.2 Prompt、十二 control、准入门槛与确定性 Candidate 作为生产基线冻结，阶段三不得原地修改该 profile。
- 下一次人工盲测前必须先分离 public/private benchmark 汇总；人工完成前，公开产物不得出现 `protocol_profile`、`processing_profile`、`phase2_variant_ids` 或能直接解码 profile 的验收区块，完整内部状态只能保存在 `_private`。
- 阶段三新增独立 profile 时，现有 `added` 自动物化链路视为已完成基线；剩余范围只允许先做 advice-only `challenge`，再做 shadow-only `correct`。在新的人工验收前，`challenge/correct` 均不得改写 Primary finding、评分、评分理由或 Top 3。

## 阶段三报告原子化约束（2026-08-14）

- 一条 finding 必须对应一个可独立关闭单元：一个决策对象、一个主要根因、一个主修复动作和一个验收闭环。
- 同一问题的重复描述可以合并 evidence 并保留一套完整表述；不得把不同配置对象、不同流程节点、不同责任方或不同验收方式仅因同属一个主题而合并。
- `findings_share_semantic_signature` 只可作为疑似重复诊断，不能单独触发物理合并。不同非空显式 issue ID 是强拆分信号；只有受控根因、同一原子对象和强证据同时成立时才可覆盖。
- `merge_duplicate_findings` 不得再逐字段无条件串接 `current_state/risk/suggestion`；真正重复时以最佳完整条目为主，只合并同一问题的互补 evidence。
- `.md`、`.docx`、`.pdf`、`.txt`、`.xls/.xlsx` 文档名都要参与证据识别；仅引用同一文档不足以证明两个 finding 是同一问题，还应核对章节、段落、表格或图片定位。
- 报告 JSON 必须保留 `dedupe_diagnostics`、`atomicity_transform_diagnostics`、`finding_atomicity_status`、`finding_atomicity_suspect_count` 和 `finding_atomicity_review_queue`。可定位到各对象独立现状的多对象 finding 应确定性拆分；全部对象已由更窄 finding 覆盖的宽泛汇总应从默认 finding 移除；无法安全拆分的原始项必须进入 review queue 并在 Markdown 展示，不得继续作为正式 finding，也不得静默丢弃。
- dual pass 不得把多个已物化拆分项重新吸收到一个 Primary finding。`challenge/correct` 在人工验收前只能建议拆分或纠错，不得改写正式报告。
- Primary Prompt 可以增加原子化硬规则；冻结的 phase2 V2.2 Secondary Prompt、十二 control、准入门槛和确定性 added 链路不得因此修改。

## 阶段三：phase3_v1 / phase3_v1_1 / phase3_v1_2 / phase3_v1_3 Challenge/Correct 协议

- `phase3_v1` 是已完成人工基线的冻结历史 profile；`phase3_v1_1` 只收敛 Correction 处置策略，必须保持 V1 Challenge 规则不变。普通生产 `dual_pass` 继续使用冻结 `phase2_v2_2`，不得用 phase3 替换或原地修改 V2.2 Prompt。
- CLI 使用 `--secondary-profile phase3_v1_3` 执行当前 Challenge 稳定性方向回放；同一 Qwen 的协议对照可重复传入两个不同 profile，但人工完成前仍必须遵守 public/private 盲态隔离。
- V1/V1.1 顶层只允许 `challenge_findings`、`correction_shadows`、`review_notes`；V1.2/V1.3 额外且必须包含 `target_coverage_ledger`，V1.3 每行还必须包含 `challenge_checks`。出现 Candidate、模型评分、missed finding 或其他顶层字段时，`phase3_protocol_gate` 硬失败。
- `review_notes` 最后一项必须精确回显当前真实 profile 与 `primary_report_hash=<hash>`；V1/V1.1 或目标 Primary hash 任一不匹配时，本次全部 challenge/correct 拒绝，保存响应重处理也禁止跨 profile 解释。
- challenge 只质疑 Primary 已有 finding，必须绑定真实 `target_issue_id`、合法 challenge type、可定位 evidence、rationale 和明确建议动作。`multiroot` 只能建议 `split`，且至少给出两个 decision object 唯一、证据/责任人/验收闭环完整的拆分项。
- correct 固定为 shadow-only。系统从冻结 Primary 取真实 `before`，只生成 `after_preview` 并写 `applied_to_report=false`；不得进入 Pipeline、Candidate 或默认报告。
- `phase3_v1_1` Correction 必须提供 `correction_disposition=drop/downgrade/clarify/narrow/split/abstain`、合法 `source_provenance`、单一 `residual_issue` 和四项布尔 `semantic_checks`。不得继续使用 V1 的 `correction_type` 作为原始协议字段。
- V1.1 处置必须与 Challenge 动作一致：drop→drop/abstain，demote→downgrade/drop/abstain，split→split/abstain，keep→abstain。兼容解释已闭环且原判断不成立时只能 drop/abstain；禁止重新包装为 wording/clarify 问题。
- V1.1 downgrade 必须重写 risk 并标记 `protected_fields_need_human_review=true`，但不得输出 severity/blocking 的新值；drop 不得生成新 finding；abstain 不进入人工 Correction 队列。参考/竞品/未知来源只允许 drop、downgrade 或 abstain，禁止据此编造当前产品机制。
- `overall_evaluation`、`document_quality_score`、`score_reason`、`top_blockers`、`severity`、`blocking` 是 phase3 全层级保护字段；任何 challenge/correct 提议包含这些键都必须拒绝。
- V1.2 必须把冻结 Primary 的每个真实 finding 按固定顺序写入 `target_coverage_ledger`，数量、`target_order` 与 `target_issue_id` 必须完全一致。每项只能是 `pass/challenge/abstain`；只有 challenge 状态可生成同目标唯一 challenge/correction，状态、challenge type 或 action 不一致时整次协议失败。
- V1.3 冻结 V1.2 Correction、人工应用和评分重算规则，只收敛 Challenge 选择稳定性。每个 ledger 行必须穷举 `duplicate/multiroot/evidence_mismatch/unsupported/compatible_interpretation/overstated` 六类检查，状态只能为 `confirmed/rejected/uncertain`。
- V1.3 决策矩阵固定为：任一 confirmed→challenge；无 confirmed 且任一 uncertain→abstain；全部 rejected→pass。多项 confirmed 固定优先级为 `duplicate > multiroot > evidence_mismatch > unsupported > compatible_interpretation > overstated`；动作固定映射为 `merge_evidence/split/clarify/drop/drop/demote`。漏检、决策、优先级或动作不一致必须硬失败，禁止安全归一化替模型改结论。
- V1.3 的依据是 `20260818_104513` V1.2 回放：15/15 Challenge 与 11/11 Correction 人工有效，11 条 drop 全部可安全应用且两份 777 从 C 重算为 B，但 Challenge 复跑重合率仅 22.22%。因此不得通过降低人工质量门槛、删除有效 Challenge 或改用更宽松统计口径来解决稳定性问题。
- V1.2 模型阶段仍不得修改保护字段。只有 finalize 后人工对 Correction 的 `target_correct/accurate/supported/safe_to_apply` 四项全为 true，系统才写出独立的 `review_report_human_approved.*`；不得覆盖冻结的 `review_report.*`。
- 人工确认后的确定性处置规则：drop 删除 finding；downgrade 固定执行 `高→中→低` 及 `阻塞开发→阻塞测试用例设计→建议优化`；clarify/narrow 只能修改允许的 finding 正文字段；split 的拆分项继承原 severity/blocking。应用后必须从最终 findings 重建 Top 3，并调用统一 `stable_score()` 重算 `document_quality_score` 与 `score_reason`，禁止沿用已被删除的旧 blocker 或旧 C/D 评分。
- 评分重算的拥有者是系统规则，不是 Secondary。每次应用必须生成 `phase3_human_apply_summary.json`，记录修正 ID、风险数前后、评分/理由/Top3 前后及输出路径；没有人工确认时不得生成修改后的正式报告。
- 每格私有工件至少包括 `secondary_challenge_advice.*`、`secondary_correction_shadow.*`、`phase3_replay_summary.json`、原始 messages/response 与锁定后的 `review_report.*`；phase3 不得生成 `review_report_candidate.*`。
- `phase3_replay_summary.json` 必须证明 Primary report hash、保护字段 hash、评分、评分理由、Top 3、severity/blocking 全部未变，并记录逐项准入/拒绝/abstain 数、Correction disposition 统计和稳定键。
- 保存的 phase3 响应必须支持 `--secondary-benchmark-reprocess` 零模型调用重处理；禁止把 baseline/phase2 原始响应强制解释为 phase3。
- `phase3_acceptance` 通用机器门槛：调用完整、公平性通过、协议门槛 100%、Primary 基线锁 100%、人工前直接物化率 0、保护字段修改 0。V1.2 还要求目标账本完整/合法率 100%、目标决策重合率至少 80%、Challenge/Correction 重合率至少 50%。V1.3 继续保留全部 V1.2 门槛，并增加 challenge checks 完整/合法率 100%、Challenge target 重合率至少 50%、六类检查状态重合率至少 80%。人工门槛：challenge 目标与证据定位 100%、有效率至少 80%；correct 目标与证据支持 100%、准确率至少 90%。没有完成人工判断时状态只能是 pending，任何机器或稳定性门槛失败时状态必须是 failed。
- 修改 phase3 schema、Prompt、保护字段、工件、人工标签或验收门槛时，必须同步更新 `README.md`、本文件、`env.example.ps1`、`env.example.cmd`、`tests/test_phase3.py` 与 `tests/test_secondary_benchmark.py`。
