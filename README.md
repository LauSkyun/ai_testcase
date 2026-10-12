# RAD

RAD 是一个面向游戏需求文档与数值文档的审查脚本。它会读取 `.docx` 文件，提取正文、表格、图片，并结合文本模型与视觉模型生成结构化审查报告，帮助在需求评审、测试设计前尽早发现歧义、冲突、缺失和高风险项。

审查时，`[001]`、TBD、待配置、待填写、示例值以及概率、倍率、阈值、上下限等具体配置值未填，默认视为团队正常配置流程，不单独生成风险、Top Blocker、质量备注或扣分项。只有文档能直接证明规则/公式冲突、结算矛盾、除零、死锁，或不依赖具体配置值仍无法执行时，才报告对应的实际冲突。

## 你现在最可能要用的命令

```powershell
python review.py --input requirements --game 小鸡 --output reports --require-model
```

默认 `--review-mode fast` 只跑一次主分析；如果要在发给策划/测试前做二次校验，可使用：

```powershell
python review.py --input requirements --game 小鸡 --output reports --review-mode strict --require-model
```

如果你只是想先验证解析流程，不连模型也可以运行：

```powershell
python review.py --input requirements --game 小鸡 --output reports --extract-only
```

如果要执行阶段一公平基线（冻结同一份 Primary，只比较 Qwen / DeepSeek Secondary），先加载包含命名供应商变量的环境，再运行：

```powershell
. .\env.local.ps1
python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-provider deepseek --secondary-repeats 2 --output reports
```

该命令对 5 款游戏共执行 `5 × 2 × 2 = 20` 次 Secondary 调用，不重新解析文档或图片，也不重新调用 Primary。

阶段二比较同一个 Qwen 的旧协议与新协议时，固定一个命名供应商，只改变 prompt/profile：

```powershell
. .\env.local.ps1
python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile baseline --secondary-profile phase2 --secondary-repeats 2 --output reports
```

阶段三 V1.1 Correction 收敛验证只调用 Qwen Secondary，冻结 Primary 并输出 challenge/correct 旁路工件：

```powershell
. .\env.local.ps1
python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile phase3_v1_1 --secondary-repeats 2 --output reports
```

`phase3_v1_1` 冻结 V1 Challenge 规则，只收敛 Correction 的 drop/downgrade/clarify/narrow/split/abstain 处置一致性；不生成 Candidate、不修改 Pipeline，评分、评分理由、Top 3、severity 和 blocking 均由 Primary 哈希锁定。正式执行外部回放前仍需单独获得调用授权。

阶段三 V1.2 在 V1.1 上增加逐 finding 固定目标账本，并在人工确认 Correction 后由系统重算评分：

```powershell
. .\env.local.ps1
python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile phase3_v1_2 --secondary-repeats 2 --output reports
```

模型仍无权直接输出评分、severity 或 blocking。只有 V1.2 Correction 通过协议准入且人工 `target_correct/accurate/supported/safe_to_apply` 全部确认后，系统才确定性应用 drop/downgrade/clarify/narrow/split，重建 Top 3，并按最终 findings 统一重算 `document_quality_score` 与 `score_reason`。

阶段三 V1.3 冻结 V1.2 的 Correction 与评分链路，只收敛 Challenge 复跑稳定性：

```powershell
. .\env.local.ps1
python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile phase3_v1_3 --secondary-repeats 2 --output reports
```

V1.3 要求每个 Primary finding 固定检查 `duplicate / multiroot / evidence_mismatch / unsupported / compatible_interpretation / overstated` 六类信号，并由系统校验固定决策矩阵、类型优先级和动作映射。正式执行新的 10 次外部回放前仍需单独获得调用授权。

## 快速开始

### 1. 安装依赖

```powershell
python -m pip install -r requirements.txt
```

### 2. 配置环境变量

PowerShell:

```powershell
Copy-Item env.example.ps1 env.local.ps1
# 修改 env.local.ps1 中的占位值
. .\env.local.ps1
```

CMD:

```cmd
copy env.example.cmd env.local.cmd
rem 修改 env.local.cmd 中的占位值
call env.local.cmd
```

当前脚本依赖的环境变量如下：

- `AI_BASE_URL`
- `AI_API_KEY`
- `AI_MODEL`
- `AI_VISION_BASE_URL`
- `AI_VISION_API_KEY`
- `AI_VISION_MODEL`
- `AI_WIRE_API`
- `AI_VISION_WIRE_API`
- `AI_SEED`（可选，仅当模型服务支持 seed 时填写）
- `AI_PROVIDER_<名称>_BASE_URL` / `API_KEY` / `MODEL` / `WIRE_API` / `SEED`：仅冻结 Primary 的 Secondary 公平基线使用，例如 `AI_PROVIDER_QWEN_*`、`AI_PROVIDER_DEEPSEEK_*`

其中视觉模型变量可与文本模型拆分配置；如果未拆分，会回退复用文本模型地址或密钥。

### 3. 运行审查

默认建议用 `--game` 指定要分析的游戏名。`requirements/` 既支持旧的平铺 `.docx`，也支持新的 `requirements/<项目名>/*.docx` 文件夹组织方式；脚本会优先按项目文件夹分组，并将结果输出到 `reports/`：

```powershell
python review.py --input requirements --game 小鸡 --output reports --require-model
```

测试多款游戏时，可以自动分组生成多份独立报告：

```powershell
python review.py --input requirements --auto-group --output reports --require-model
```

## 常用命令

完整帮助：

```powershell
python review.py --help
```

只做文档解析，不调用模型：

```powershell
python review.py --input requirements --game 小鸡 --extract-only
```

跳过图片识别，只做文本审查：

```powershell
python review.py --input requirements --game 小鸡 --skip-images --require-model
```

限制送审图片数量：

```powershell
python review.py --input requirements --game 小鸡 --image-limit 10 --require-model
```

指定单个文档：

```powershell
python review.py --input "requirements\\musee游戏Racing.docx" --output reports --require-model
```

按游戏名匹配文档：

```powershell
python review.py --input requirements --game Racing --output reports --require-model
```

严格模式（主分析 + 综合校验器，适合重要需求或低置信报告）：

```powershell
python review.py --input requirements --game 小鸡 --output reports --review-mode strict --require-model
```

测试目录中多款游戏并分别生成报告：

```powershell
python review.py --input requirements --auto-group --output reports --extract-only
```

批量对比多次运行的报告稳定性（调试阶段使用）：

```powershell
python report_debug_summary.py --reports-root reports 20260720_145550 20260722_104757
```

该命令支持直接传入多次“全游戏”运行目录，会按输入文档签名自动把同一款游戏配对比较，并同时检查报告工件、原始模型 JSON、finding 必填字段、图片状态、candidate 采用情况、issue_id 修复数、评分与 Top Blockers 漂移。

## 参数说明

- `--input`, `-i`：输入的 `.docx` 文件，或包含多个 `.docx` 的目录，默认是 `requirements`
- `--output`, `-o`：输出目录，默认是 `reports`
- `--game`：按游戏名从输入目录中筛选相关 `.docx`，例如 `小鸡`、`Racing`；支持 `requirements/<项目名>/*.docx` 的目录样式
- `--auto-group`：按项目文件夹或文件名自动分组多款游戏，并为每款游戏生成独立报告
- `--review-mode`：分析模式，`fast` 为一次主分析，`strict` 为主分析后增加综合校验，`benchmark` 保留确定性调试工件供多次复跑对比
- `--extract-only`：仅解析文档并写出提取产物，不调用 AI
- `--skip-images`：提取图片但不送视觉模型分析
- `--image-limit`：限制参与视觉分析的图片数量，默认 `100`
- `--timeout`：模型请求超时时间，单位秒，默认 `600`
- `--model-retries`：文本模型遇到超时、网络错误、HTTP 5xx/429 等瞬时故障时，在首次失败后自动重试的次数，默认 `3`（即最多请求 `4` 次）；设为 `0` 可关闭重试
- `--max-context-chars`：发送给文本模型的最大上下文长度，默认 `120000`
- `--log-echo`：同时把运行日志回显到标准错误
- `--require-model`：缺少 `AI_BASE_URL`、`AI_API_KEY`、`AI_MODEL` 时直接报错退出
- `--secondary-replay-from`：从单款 `dual_pass` 历史目录或全游戏批次目录冻结并回放 Secondary，不调用 Primary/视觉模型
- `--secondary-provider`：命名 Secondary 供应商；供应商 A/B 时重复传入两个不同名称，同模型协议 A/B 时只传一个名称并配合 `--secondary-profile`
- `--secondary-profile`：Secondary 协议 profile，可选 `baseline` / `phase2` / `phase3_v1` / `phase3_v1_1` / `phase3_v1_2` / `phase3_v1_3`；V1.3 在 V1.2 固定账本上增加 Challenge 六类穷举检查与固定决策矩阵
- `--secondary-repeats`：每款游戏、每个 Secondary 的重复次数，阶段一最少且默认是 `2`
- `--secondary-benchmark-finalize`：校验已填写的盲测人工标注，并把有效新增率、重复率、高价值新增数写回基准汇总
- `--secondary-benchmark-reprocess`：仅用已保存的 Secondary 原始响应重建整批结果与指标，不发起任何模型请求；用于修复 JSON 解析失败，或在指标算法升级后重算同一批次
- `--secondary-reprocess-profile`：重处理保存响应时应用 `baseline`、`phase2`、`phase3_v1`、`phase3_v1_1`、`phase3_v1_2` 或 `phase3_v1_3` 处理规则；phase3 只能处理由相同真实 profile 生成的保存响应，禁止跨 profile 伪装重处理

## 输出目录说明

每次运行会在 `reports/<时间戳>/` 生成一套产物，并刷新 `reports/latest/`：

- `review_report.md`：Markdown 审查报告
- `review_report.json`：结构化 JSON 结果
- `review_report_pre_audit.md` / `review_report_pre_audit.json`：仅 `strict` 模式生成，保留综合校验前的主分析版本，方便直接对比校验前后差异
- `review_report_diff.md` / `review_report_diff.json`：仅 `strict` 模式生成，汇总评分变化、Top Blockers 变化、问题增删改和新增备注，方便快速判断校验器是否有效
- `extraction_manifest.json`：解析清单，含文档、表格、图片元数据
- `extraction_context.md`：送给模型的文档上下文
- `run.log`：本次运行日志
- `assets/`：从 `.docx` 中提取出来的图片资源
- `model_artifacts/`：确定性调试工件，包含文档 hash、review messages、原始模型响应；`strict` 模式下还会包含 audit messages 与原始校验响应
- `group_run_summary.json`：仅 `--auto-group` 批次生成，记录每款游戏的 `completed` / `warning` / `failed` 状态、失败原因、日志及报告路径
- `reports/.cache/image_analysis/`：跨单次运行与 `--auto-group` 全游戏批次复用的视觉解析缓存；缓存键包含视觉模型名、提示词 hash 与图片内容 hash
- `report_debug_summary.py`：调试阶段批量读取多个 `reports/<运行目录>/`，检查产物完整性、原始模型 JSON、finding 必填字段、candidate 诊断与图片状态，并按同一款游戏比较评分、Top Blockers 和共同/漂移问题
- `reports/secondary_benchmarks/<时间戳>/`：冻结 Primary 的 Secondary A/B 公平基线产物，不参与普通报告的 `latest/` 刷新

使用 `--auto-group` 时，会在 `reports/<时间戳>/<游戏名>/` 下分别生成每款游戏的同名产物，并将整组结果刷新到 `reports/latest/`。某款游戏的 primary 文本模型在重试耗尽后失败，会记录到批次根目录的 `group_run_summary.json` 并继续下一款，不会中断整个批次；批次最终返回非零退出码。`dual_pass` 的 secondary 在重试耗尽后仍沿用已有降级逻辑，保留并输出 pipeline 报告。视觉解析缓存始终复用 `reports/.cache/image_analysis/`，不会再落到各时间戳目录，确保相同图片复跑时共享输入保持稳定。

## 目录结构

```text
RAD/
├─ review.py
├─ rad_review/
│  ├─ agent.py
│  ├─ docx_reader.py
│  ├─ model_client.py
│  ├─ prompts.py
│  ├─ report.py
│  └─ run_logger.py
├─ requirements/
├─ reports/
├─ quality_baselines/
├─ skills/
├─ env.example.ps1
├─ env.example.cmd
└─ requirements.txt
```

## 使用建议

- 首次接入新模型时，先运行一次 `--game <游戏名> --extract-only`，确认文档能正常解析。
- 如果 `requirements/` 同时放了多款游戏，优先按 `requirements/<项目名>/` 组织；运行时使用 `--game` 指定单款游戏，或用 `--auto-group` 做测试批量分析。
- 视觉模型不稳定时，可先使用 `--skip-images` 跑通主流程。
- 如果输出报告异常简短或超时，可适当增大 `--timeout`，或减小 `--max-context-chars`。
- 正式审查的文本模型请求默认在首次瞬时故障后重试 `3` 次，退避等待依次为 `2`、`4`、`8` 秒；可用 `--model-retries <次数>` 调整。HTTP 4xx 配置/鉴权错误（除 408、409、425、429 外）不会重试。
- `reports/` 与 `__pycache__/` 属于运行产物目录，通常不需要手工编辑。

## 已知说明

- 当前项目是 Windows PowerShell 场景优先，文档命令默认以 PowerShell 为主。
- 当前工作目录未检测到 `.git` 仓库；如果后续初始化 Git，再补充提交流程即可。
## 模型探活

切换 `AI_MODEL` 或 `AI_WIRE_API` 之后，建议先用最小请求验证文本模型路由是否可用，再跑正式审查：

```powershell
python review.py --probe-model --timeout 30
```

## Dual Pass 新诊断字段补充

- `candidate_merged_materialization_status`：用于判断副模型声明的 `candidate_lineage.merged` 是否真的进入最终 candidate。
- `candidate_merged_materialization_missing_ids`：用于暴露哪些 merged `candidate_issue_id` 声称存在但最终未落盘。
- `candidate_structurally_ready`：表示 candidate 是否已经通过结构、证据、追踪、命名等直出门槛。
- `candidate_blocked_only_by_editorial_judgment`：表示 candidate 在结构上已可用，但当前仍只因质量判断或 readiness 判断而未默认切换。
- `suggestion_level_conflict`：表示副模型把 `suggestion_level` 评成 `high`，但三个 readiness 已同时为 `true`，存在语义冲突。
- `suggestion_level_override_applied`：表示系统已将上述冲突视为“编辑性评语过重”，不再仅因 `suggestion_level = high` 阻断 candidate 切换。
- `candidate_contains_multiroot_kept_findings` / `candidate_multiroot_kept_titles`：用于暴露 candidate 中仍保留的多根因 kept 问题，便于继续拆分或改为分点展示。
- `candidate_high_signal_demotion_without_support` / `candidate_high_signal_demotion_titles`：用于暴露 candidate 是否在缺少明确兼容实现依据或反证时，下调了 primary 的高信号核心问题。
- `candidate_overcompressed` / `candidate_overcompressed_reason`：用于暴露 candidate 是否通过过度收缩问题数和大幅改写共享问题来显得更乐观。
- `ready_for_direct_output` 在 `dual_pass` 下表示“报告本身是否已经达到可直接输出给业务 / 产品 / 研发阅读的质量”，不表示文档里的产品问题已经全部确认完毕。

## Dual Pass 默认成稿语义（当前版本）

`dual_pass` 当前已经从“摘要页模式”收敛为“默认成稿 + 独立索引页”模式：

- `review_report.md` / `review_report.json`
  - 表示本次运行默认对外使用的最终报告
  - 可能来自 `pipeline`，也可能来自 `candidate`
- `review_report_index.md` / `review_report_index.json`
  - 表示 `dual_pass` 的摘要页 / 索引页
  - 用来说明本次默认采用了哪一份报告，以及为什么
- `review_report_pipeline.*`
  - 表示基于主模型报告 + 副模型补漏建议整理出来的管线版报告
- `review_report_candidate.*`
  - 表示副模型返回的候选成稿，经现有报告稳定化链路处理后的版本
  - 对 `candidate_lineage.kept` 映射的问题，副模型有证据支持的标题、严重度、阻塞级别和正文纠错会真正物化；无支持的高信号降级仍由 candidate 门槛阻断
- `secondary_review_advice.*`
  - 表示副模型对主模型质量、补漏、证据充分性和候选稿可用性的建议文档

`dual_pass` 下是否默认切到 `candidate`，不再只看副模型口头建议，而是看代码里的门槛规则是否同时满足：

- `candidate_report` 可成功解析并通过现有稳定化 / 完整性链路
- 当前运行没有额外 warning
- `quality_assessment.ready_for_direct_output = true`
- `candidate_readiness.ready_for_direct_output = true`
- 上述两个 readiness 结论彼此一致
- 系统归一化后的 `normalized_candidate_ready_for_direct_output = true`
- 若 `quality_assessment.suggestion_level = high`，则只有在三个 readiness 也未全部通过、或 candidate 尚未达到结构直出门槛时才阻断默认切换
- `traceability_status = complete`
- `lineage_coverage_complete = true`
- 不存在 `candidate_high_signal_demotion_without_support = true`
- 不存在 `candidate_overcompressed = true`
- 不存在 `unmapped_primary_issue_ids`
- 不存在 `unmapped_candidate_issue_ids`
- `candidate_added_materialization_status` 为 `none` 或 `complete`
- 最终 candidate 中不存在 `未命名问题`
- phase2 下所有 Secondary 新增项均通过字段、证据定位、Primary 去重、单根因与严重度依据准入
- phase2 下 Candidate 对 Primary Top 3 的保留率不低于 `2/3`
- phase2 下 Candidate 的 `document_quality_score` 与 `score_reason` 锁定为 Primary 结果

只要任一门槛不满足，默认最终报告就仍然回退为 `pipeline`，并把失败原因写入：

- `review_report_index.json` 的 `candidate_gate_failure_reasons`
- `model_artifacts/dual_pass_summary.json`

为降低副模型“过度重写”或“过度合并”导致的追踪困难，`dual_pass` 还新增了候选稿血缘字段：

- `candidate_lineage.kept`
- `candidate_lineage.added`
- `candidate_lineage.merged`
- `candidate_lineage.dropped`

其中 `candidate_lineage.kept` 在需要“吸收 missed finding 但不单独落盘”时，还应返回：

- `absorbed_missed_issue_ids`

索引页和调试工件会额外输出：

- `selected_report_owner`
- `candidate_recommendation_status`
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
- `lineage_coverage_complete`
- `unmapped_primary_issue_ids`
- `unmapped_candidate_issue_ids`
- `untitled_finding_issue_ids`
- `candidate_added_materialization_status`
- `advice_candidate_structure_mismatch`
- `advice_claimed_absorbed_but_materialized_separately`
- `advice_claimed_added_but_not_materialized`
- `materialized_missed_without_added`
- `normalized_candidate_ready_for_direct_output`
- `normalized_candidate_ready_reason`
- `trace_warning`
- `phase2_admission`
- `primary_top3_retention`
- `primary_top3_retention_gate_passed`
- `candidate_score_locked_to_primary`

其中：

- `traceability_status = complete` 表示 candidate 带有完整 lineage，且 primary/candidate 双向问题集合都能被血缘解释，可参与默认切换判断
- `traceability_status = partial` 表示 candidate 有 lineage，但血缘覆盖不完整，当前不允许默认切换
- `traceability_status = minimal` 表示 candidate 与 primary 基本同构，但 lineage 缺失，仅保留为可浏览候选稿
- `traceability_status = missing` 表示 candidate 相对 primary 存在明显结构变化，但 lineage 缺失，可读但不可追踪
- `readiness_conflict = true` 时，系统会把两个 readiness 标记统一降为 `false`
- `lineage_counts_raw` 表示副模型原始返回的 lineage 统计
- `lineage_counts_materialized` 表示最终 candidate 实际落盘后的 lineage 统计
- `lineage_coverage_complete = true` 表示 primary/candidate 的 issue_id 集合已被 `kept/added/merged/dropped` 完整覆盖
- `unmapped_primary_issue_ids` / `unmapped_candidate_issue_ids` 用于显式暴露“哪些问题未被 lineage 覆盖”
- `untitled_finding_issue_ids` 用于暴露最终 candidate 中仍未修复标题的问题
- `candidate_added_materialization_status` 用于判断副模型声明的 added 问题是否真的进入最终 candidate
- `advice_candidate_structure_mismatch = true` 表示副模型对 candidate 结构的说明与最终 candidate 实际落盘结果不一致，当前候选稿不可作为默认最终输出
- `advice_claimed_absorbed_but_materialized_separately` 用于暴露“lineage 声称已吸收，但候选稿仍单独落盘”的 missed issue
- `advice_claimed_added_but_not_materialized` 用于暴露“lineage.added 声称新增，但候选稿没有真正落盘”的 candidate issue
- `materialized_missed_without_added` 用于暴露“候选稿已独立落盘，但 lineage 未解释来源”的 missed issue
- `normalized_candidate_ready_for_direct_output` / `normalized_candidate_ready_reason` 表示系统在综合 readiness、traceability、lineage 覆盖、未命名问题等门槛后的最终直出结论
- `phase2_admission` 记录每个声称新增项的 `admitted/rejected` 状态与拒绝原因；被拒绝项只进入 advice，不进入 pipeline
- `primary_top3_retention_gate_passed = true` 表示本次 Candidate 至少保留 Primary Top 3 中的两个同根因问题
- `candidate_score_locked_to_primary = true` 表示 Secondary 没有取得改分权

`dual_pass` 下凡是副评审补充的问题，最终报告 JSON/Markdown 中都应带：

- `finding_source = secondary_reviewer`
- `finding_source_label = 副评审补充`
- `source_model = <副模型名>`

## Dual Pass 当前收敛策略（2026-06）

- 这一期仅在 `--review-mode dual_pass` 下暂时停用单独的 `cross_document_issues` 展示区。
- `dual_pass` 输出仍保留 `cross_document_issues: []` 字段以保持 schema 兼容，但实际问题会回填到原来的 `dimensions[*].findings`。
- `review_report_pipeline.*` 目前只做“原维度补漏 + 备注保留”，不再做激进的跨区搬运、物理合并或基于副模型建议改分。
- `review_report_candidate.*` 会优先保持与主模型相近的结构、问题顺序和 issue 切分；本期不鼓励大幅重写或汇总式改写。
- 对 kept 问题，candidate 明确给出的标题、严重度、阻塞级别与正文修正必须同步物化，不能只更新说明文字而继续沿用 primary 的旧判断。
- `review_report_index.json` / `model_artifacts/dual_pass_summary.json` 会显式写出 `cross_document_section_disabled: true`，便于后续调试和对比。

## Dual Pass 模式补充

`dual_pass` 是一个独立测试模式，用于验证“主模型首版报告 + 副模型复核补漏 + 副模型候选成稿”的新链路：

```powershell
python review.py --input requirements --game Racing --output reports --review-mode dual_pass --require-model
```

这个模式会同时要求两套文本模型配置：

- `AI_PRIMARY_BASE_URL`
- `AI_PRIMARY_API_KEY`
- `AI_PRIMARY_MODEL`
- `AI_PRIMARY_WIRE_API`
- `AI_PRIMARY_SEED`（可选）
- `AI_SECONDARY_BASE_URL`
- `AI_SECONDARY_API_KEY`
- `AI_SECONDARY_MODEL`
- `AI_SECONDARY_WIRE_API`
- `AI_SECONDARY_SEED`（可选）

`--probe-model --review-mode dual_pass` 会和 `fusion` 一样，分别探活 `AI_PRIMARY_*` 与 `AI_SECONDARY_*`。

`dual_pass` 会额外生成以下产物：

- `review_report.md` / `review_report.json`
  - 本次门槛选择后的默认最终报告；Candidate 未通过时自动回退 Pipeline
- `review_report_pipeline.md` / `review_report_pipeline.json`
  - 基于主模型首版报告和副模型复核建议整理后的版本
- `review_report_candidate.md` / `review_report_candidate.json`
  - phase2 下由系统按 Primary Pipeline 与已准入增量确定性生成的候选报告
- `review_report_index.md` / `review_report_index.json`
  - 报告选择、协议门槛、追踪与回退原因索引
- `secondary_review_advice.md` / `secondary_review_advice.json`
  - 副模型对主模型报告的质量评估、补漏建议与备注
- `model_artifacts/shared_review_input.json`
- `model_artifacts/primary_review_messages.json`
- `model_artifacts/secondary_review_messages.json`
- `model_artifacts/primary_raw_model_response.txt`
- `model_artifacts/secondary_raw_model_response.txt`
- `model_artifacts/phase2_control_evidence_packet.json`
- `model_artifacts/dual_pass_summary.json`

`dual_pass` 的关键约束是：

- 主模型和副模型不共用同一份最终 messages
- 但它们必须共用同一份 `shared_review_input.json` 作为事实输入底座
- 副模型不再做第二份独立首审或候选成稿，只复核主模型结果、提供反证并输出结构化遗漏增量
- 当前生产 `dual_pass` 默认使用 `phase2` 协议：Secondary 是结构化补漏与反证审查者，Candidate 只允许保守物化通过硬准入的增量

## 阶段二：Qwen 同模型协议收敛

阶段二固定 `Qwen Primary + Qwen Secondary`，不重新选择模型。`baseline` 冻结阶段一提示词，`phase2` 增加 Delta 协议与确定性准入。

phase2 的每个 `missed_findings` 至少要提供：

- `candidate_issue_id`、唯一所属的 `audit_key`、`title`、`primary_dimension`
- `current_state`、`evidence`、`risk`、`suggestion`
- `severity`、`blocking`、`confidence`
- `independent_root_cause`、单元素 `root_causes`
- `primary_overlap_check.nearest_primary_issue_id / overlap / reason`
- `root_cause_count = 1`
- `fact_check.claim_type / source_rule_presence_checked / compatible_interpretation_checked / compatible_interpretation_exists / conclusion / reason`
- `missing_rule` 还必须提供可定位的 `fact_check.searched_locations`
- high、`block_dev`、`block_test` 还必须提供 `severity_basis`

为继续降低复跑漂移，phase2 使用 `coverage_schema_version = 2`，必须先生成固定 `coverage_ledger`，再据此生成 `missed_findings`。五个 `audit_key` 下固定拆成 12 个 control：实际结算公式、UI/配置映射、触发入口、终止/优先级、本金扣款节点、派奖到账节点、资金失败补偿、相对倍率上限、奖池负值下限、单局金额封顶、同指标统计窗口、正文/UI窗口一致性。audit/control 的数量、顺序、状态、数组字段、核验证据和理由都会经过确定性校验。每个 control 必须标记 `covered_by_primary / confirmed_add / advice_only / no_issue / not_applicable`，`confirmed_add` 与 `missed_findings` 必须按 `candidate_issue_id + audit_key + control_key` 双向一一对应，非 `confirmed_add` control 不得携带 candidate ID，每个 control 最多新增一个独立根因。

对不改变审查结论的纯协议漂移会做可追踪的安全归一化：`covered_by_primary` 中与 Primary ID 完全相同的冗余 candidate ID 会被清空；`not_applicable` 漏填核验证据时，会基于冻结共享输入补入实际文档名与“全文”。修复记录写入 `phase2_admission.coverage_ledger.protocol_repairs`，其他 ID 漂移、证据缺失或双向映射错误仍按硬失败处理。

V2 还会校验 `covered_by_primary` 引用的 Primary issue 是否真实存在并涉及同一 control。例如本金扣款节点不能引用假数据隔离、零赔付或开奖快照问题；奖池负值下限不能引用只讨论单局封顶的问题。无法证明同一控制面时账本硬失败，避免用不相关 Primary ID 隐藏真实漏项。benchmark 额外记录 `coverage_confirmed_control_keys` 与两次复跑的 `coverage_confirmed_control_overlap`。

`phase2_acceptance` 额外要求 `coverage_schema_v2_rate = 100%`。历史 V1 响应仍可解析和查看诊断，但在当前 phase2 处理链路中会以 `coverage_schema_version_too_old` 回退 pipeline，不能被误算为 V2 验收通过。

如果模型漏填顶层 `coverage_schema_version`，但五个 audit 的顺序和全部十二个 control 的名称、数量、顺序完全符合 V2 固定结构，系统可安全推断为 V2，并记录 `inferred_coverage_schema_version:2_from_complete_control_shape`。任何 control 缺失、改名、换序或多余时禁止推断；旧 V1 五格账本仍按 V1 回退。

V2 benchmark 的新增稳定性根键优先使用固定的 `audit_key + control_key`，不再依赖模型临时生成的 issue ID 或宽泛标题分类。缺失规则允许用“精确文档名 + 全文”作为负向检索范围；“未明确说明”不得误判成“明确说明”。扣款时点、派奖时点和失败补偿是三个独立 control，不能在归一化阶段互相去重。

确定性准入还会阻断已观察到的 control 越界：扣款时点混入幂等/断线恢复、资金失败补偿混入奖池负值下限或熔断、单局封顶混入数值表公式错误。原文已给出点击消耗货币、结算后余额增加或复用既有中台处理流程时，Secondary 不得继续按“规则完全缺失”高风险直出；这类内容最多进入 advice。

硬准入失败的新增项写入 `phase2_admission.results` 和 advice，不进入 pipeline。`phase2_admission.coverage_ledger` 会记录完整率、确认方向、双向映射和错误；账本不完整或不一致时，所有 Secondary 新增都停止物化，Candidate 强制回退 pipeline。构建 Candidate 前会同步移除被拒绝项及对应 `candidate_lineage.added`，并记录 `candidate_inputs_sanitized = true`；因此单个内容准入失败不会连带否决其余合格 Candidate，但清洗标记不能绕过账本协议门槛。Top 3 保留不足、评分未锁定、追踪不完整或清洗失败时同样强制回退 pipeline。

phase2 会固定按“结算/赔率/公式与UI数值 → 状态机 → 资金与经济边界 → 其他验收缺口”的顺序扫描。只有确认两条规则无法由同一实现同时满足时才允许声明直接冲突；存在“提前结束 + 最大次数兜底”等兼容解释时只能进入 challenge/advice。

阶段二 V2.1 在十二个 control 之上增加确定性证据包。运行器会从冻结的 `shared_review_input` 与 Primary 报告中，为每个 control 生成最多两条原文候选、最多两条 Primary 覆盖候选、定义和禁止混写范围，并固定按“原文状态 → 反证 → Primary 覆盖 → 最终状态”决策。证据包带有 SHA-256 `evidence_packet_id`；Secondary 必须在 `review_notes` 回显 `protocol_profile=phase2_v2_1; evidence_packet_id=<hash>`。benchmark 记录 `coverage_protocol_revision`、`coverage_evidence_packet_id`、`coverage_evidence_packet_echoed` 和变体级回显率；V2.1 验收要求回显率为 100%，历史 V2 响应不受该门槛影响。

每次 V2.1 回放还会把实际证据包写入 `model_artifacts/phase2_control_evidence_packet.json`。保存响应重处理必须复用原始 `secondary_review_messages.json`，禁止用当前 Prompt 重建历史消息；未包含 V2.1 标识的历史 phase2 消息记录为 `coverage_protocol_revision=phase2_legacy`，其回显检查显示 `legacy_not_required`。派生目录若复制到不属于实际协议的陈旧证据包，会在重处理时移除，原始批次不受影响。

2026-08-07 的 V2.1 外部方向性回放位于 `reports/secondary_benchmarks/20260807_102514`。10/10 Secondary 调用成功且证据包回显率为 100%，但 V2 schema 率为 90%、ledger 完整率为 98%、ledger 合法率为 60%、Candidate 门槛通过率为 50%，高价值新增复跑重合率仅 12.5%。人工盲标的 11 个声称新增中 10 个有效；准入后保留 7 个，其中 6 个有效，另有 1 个“已有 MAX_MUL 仍推定必须设置绝对金额封顶”的证据不足且严重度夸大项。因此 V2.1 验收失败，不能进入下一阶段。

当前 `phase2` 已迭代为 V2.2 delta-only：Secondary 只返回十二 control 的 `coverage_ledger`、`missed_findings`、反证和质量意见，不再返回 `candidate_report`、`candidate_lineage` 或 `candidate_readiness`。系统以 Primary pipeline 为骨架，只追加通过确定性准入的增量，并生成完整 lineage、锁定 Primary 评分与 Top 3；诊断字段 `candidate_generation_mode=deterministic_primary_plus_admitted_delta` 用于证明 Candidate 不是模型自由重写。Secondary 对 Primary 的原始质量评价保存在 `primary_quality_assessment`，不会被当作系统 Candidate 的结构 readiness。

V2.2 的 `phase2` Prompt 使用独立的 compact delta baseline，不再继承 Primary 的评分量表、六维完整报告要求、通用 checklist 或“优先输出 8–15 个问题”的数量目标；没有成立的新增时允许返回零新增。冻结的 `baseline` profile 仍保留阶段一原提示词，不随 V2.2 漂移。`missed_findings` 使用完整嵌套类型模板，尤其要求 `fact_check.searched_locations` 始终为字符串数组、布尔字段使用 JSON 布尔值，以减少可预防的 schema 漂移。

普通 `dual_pass` 与 benchmark 都会落盘 V2.2 证据包，并要求 `review_notes` 最后一项精确回显 `protocol_profile=phase2_v2_2; evidence_packet_id=<hash>`。V2.2 还会按模型原始顶层字段执行白名单检查：只允许质量评价、schema、ledger、missed findings、反证、合并建议和备注；返回 `candidate_report`、`candidate_lineage`、`candidate_readiness` 或其他额外顶层字段，本次 `phase2_protocol_gate` 即失败，所有 Secondary 增量停止物化并回退 Pipeline。每个 control 的 reason 必须依次包含 `source_state`、`counterevidence`、`primary_coverage`、`final`，且 `final` 必须与 control status 一致、`primary_coverage` 必须与是否 `covered_by_primary` 一致；缺段、乱序或结论不一致均按 ledger 硬失败。

对不改变新增结论的 V2.2 格式漂移允许确定性修复：枚举值后的括号/句子说明可提取其规范枚举；`no_issue/advice_only + same_control` 只有在真实 Primary ID 被程序验证为同一 control 时才归一化为 `covered_by_primary`。若非物化 control 的 same-control 引用被证明无效，则只保留程序验证为同一 control 的 Primary ID；全部无效时清空引用并改回 `not_covered`，再按已声明的 `source_state` 保守落为 `no_issue` 或 `advice_only`。`not_applicable` 中误写的 `source_state=not_applicable`、`primary_coverage=not_applicable` 可分别归一化为 `missing`、`not_covered`。这些修复只消除非物化账本元数据对其他 confirmed_add 的连带否决，全部写入 `coverage_ledger.protocol_repairs`；confirmed_add 及其证据、映射和准入门槛不受放宽。

V2.2 benchmark 额外统计 `phase2_protocol_gate_pass_rate`、`phase2_delta_only_compliance_rate` 和 `deterministic_candidate_generation_rate`，三项均必须为 100%，否则 `phase2_acceptance` 不得通过。

当前阶段二方向性验收将 `high_added_root_overlap_min` 调整为 25%。该指标用于观察同一冻结输入两次回放的高价值新增根因重合，不替代 schema/ledger 100%、人工准入准确率、有效新增数量、证据与单根因等质量门槛；只有全部门槛同时通过才可进入下一阶段。

2026-08-07 的 V2.2 外部批次为 `reports/secondary_benchmarks/20260807_115514`：5 款 × 2 次共 10 次 Qwen Secondary 全部首次成功，Primary/视觉调用为 0。最终零调用验收批次为 `reports/secondary_benchmarks/20260807_115514_reprocessed_20260807_123154`，保存的原始响应、消息和证据包均保持不变。协议回显、delta-only、确定性 Candidate、schema、ledger 完整/合法及 Candidate 门槛均为 100%，Top 3 最低保留率为 66.67%，高价值新增复跑重合率为 50%。人工标注后 18 个准入新增全部有效，准入准确率 100%，高价值新增 13 个，准入重复、证据不足、夸大和多根因均为 0；最终 `phase2_acceptance.status=passed`、`eligible_for_next_stage=true`。

2026-08-14 已完成冻结 V2.2 与冻结 baseline 的同期盲测：原始批次 `reports/secondary_benchmarks/20260814_103002` 共 5 款 × 2 profile × 2 次，20/20 配对完成，Primary/视觉调用为 0；19 格首次成功，1 格在 600 秒超时后重试成功。最终零调用验收批次为 `reports/secondary_benchmarks/20260814_103002_reprocessed_20260814_115005`。V2.2 声称新增 17 项，人工确认 17/17 有效；确定性准入 15 项，15/15 有效，高价值 12 项，重复、证据不足、夸大和多根因均为 0；ledger、协议、delta-only、确定性 Candidate 与 Candidate 门槛均为 100%，高价值复跑重合率为 37.5%。冻结 baseline 仅 10/19 有效，有效率 52.63%，重复率 21.05%，证据不足 6 项、夸大 9 项、多根因 8 项。最终 `phase2_acceptance.status=passed`、`eligible_for_next_stage=true`，V2.2 继续冻结为生产基线，后续不再调该 Prompt。

本批首次汇总在人工标注前暴露了 protocol profile，已通过同一批响应的随机重新编号盲标副本补救并在决策锁定后解盲。当前工具已经正式分离 public/private：人工标注前，完整 summary、manifest、冻结 Primary、原始 messages/响应、证据包、协议和准入诊断只写入 `_private`；公开目录仅保留 A/B、清除身份字段的报告/advice 和精简标注模板。finalize 锁定人工判断后才生成完整最终验收结果。

阶段三已完成默认报告原子化防线：不同显式 issue ID、不同决策对象或仅有弱语义相似的 finding 不再自动物理合并；弱相似 pair 只进入 `dedupe_diagnostics`。真正重复时保留一套完整的 `current_state/risk/suggestion`，只补充同一问题的 evidence，避免逐字段无限串接。对 Primary 原生多对象 finding，系统先按可识别的独立现状与建议确定性拆分；宽泛汇总的全部对象若已被更窄 finding 覆盖，则移出默认 finding 并保留完整 transform 诊断；无法在不猜测的前提下安全拆分时，移入 `finding_atomicity_review_queue`，在 Markdown 的“原子化待人工拆分队列”中展示，但不计入正式 finding。默认 finding 因此不会继续保留 atomicity suspect。报告 JSON 写入 `atomicity_transform_diagnostics`、`finding_atomicity_status`、`finding_atomicity_suspect_count` 和 review queue。Primary Prompt 同时保留“一条 finding = 一个决策对象、一个主修复动作、一个验收闭环”的硬规则，冻结的 phase2 V2.2 Secondary Prompt 未修改。

阶段三 `phase3_v1` 已作为独立 Secondary replay profile 落地，不复用 phase2 Candidate 合并链路。V1/V1.1 模型顶层只允许 `challenge_findings`、`correction_shadows`、`review_notes`；V1.2/V1.3 额外且必须包含 `target_coverage_ledger`，V1.3 每行还必须包含 `challenge_checks`。返回 Candidate、模型评分、missed finding 或其他字段会触发协议硬失败。每个 challenge 必须指向冻结 Primary 中真实存在的 `target_issue_id`，使用可定位证据并明确 `keep/split/clarify/demote/drop/merge_evidence` 动作；`multiroot` 必须给出至少两个具备独立决策对象、证据、责任人和验收标准的拆分项。

2026-08-17 完成 `phase3_v1` 的 10 次方向性回放与 35 条人工验收：Challenge 21/21 有效，目标、证据、有效率和可执行率均为 100%；Correction 目标与证据支持率均为 100%，但人工准确率仅 71.43%（10/14），未达到 90% 门槛。失败集中在“本应删除或降级的问题仍被改写并保留”，因此 V1 Challenge 继续冻结，新增 `phase3_v1_1` 只收敛 Correction 处置策略，不降低验收门槛。

`phase3_v1_1` 要求每条 Correction 先输出 `correction_disposition=drop/downgrade/clarify/narrow/split/abstain`、`source_provenance` 和四项布尔 `semantic_checks`。处置必须与 Challenge 的 `recommended_action` 一致：已由兼容解释闭环且无剩余问题时只能 drop/abstain；downgrade 必须同步重写 risk 并标记保护字段仍需人工复核；参考图、竞品截图或未知来源不能驱动产品机制改写；abstain 只保留 Challenge，不进入人工 Correction 队列。系统会把 drop 保存为删除处置预览，而不是生成另一条 wording finding。

`phase3_v1_2` 冻结 V1.1 的 Challenge/Correction 事实规则，新增与 Primary finding 一一对应、顺序固定的 `target_coverage_ledger`。每个目标必须明确 `pass/challenge/abstain`，只有 `challenge` 可以生成同目标的唯一 challenge/correction；账本缺项、乱序、重复、状态与 challenge 不一致时协议硬失败。稳定性新增目标决策重合率至少 80%、Challenge/Correction 重合率至少 50% 的阶段门槛。

2026-08-19 完成 V1.2 的 10 次 Qwen 回放与 26 条人工验收：15/15 Challenge、11/11 Correction 均达到 100% 目标正确、证据支持和人工准确；11 条人工批准 drop 已确定性应用，两份 777 报告由 C 重算为 B。但 Challenge 复跑重合率只有 22.22%，低于 50% 门槛，且不一致项全部被人工判定有效，说明问题是选择召回不稳定而不是误报。因此新增 `phase3_v1_3`，不调整人工或稳定性门槛，不改 V1.2 Correction/评分规则。

`phase3_v1_3` 在每个 target ledger 行增加固定 `challenge_checks`。六类信号状态只能为 `confirmed/rejected/uncertain`；至少一项 confirmed 必须 challenge，无 confirmed 但存在 uncertain 必须 abstain，全部 rejected 才能 pass。多项 confirmed 时固定按 `duplicate > multiroot > evidence_mismatch > unsupported > compatible_interpretation > overstated` 选择唯一类型，动作固定映射为 `merge_evidence/split/clarify/drop/drop/demote`。漏项、非法状态、decision 不符合矩阵、类型不符合优先级或动作不符合映射都会触发协议硬失败。

V1.3 除 V1.2 门槛外，还要求 Challenge checks 完整率/合法率 100%、Challenge target 重合率至少 50%、六类检查状态重合率至少 80%；原完整 Challenge 语义键重合率 50% 门槛继续保留，不能通过缩减统计口径放行。

V1.2 模型阶段继续保持 advice-only/shadow-only，评分及风险信号仍由 Primary 锁定。人工 finalize 后，仅四项人工标签全为 true 的 Correction 才进入 `review_report_human_approved.*`：drop 删除原 finding；downgrade 固定执行 `高→中→低` 与 `阻塞开发→阻塞测试用例设计→建议优化`；clarify/narrow 只改允许的正文；split 继承原风险等级。系统随后从最终 findings 重新生成 `top_blockers`，并用统一评分函数重算评分和理由，允许 C/D 在高风险被删除后提升到 B/A，也允许最终风险结构要求的反向变化。原始锁定报告不覆盖，完整审计写入 `phase3_human_apply_summary.json`。

人工确认前 correct 固定为 shadow-only：系统从冻结 Primary 取出真实 `before`，只保存模型建议的 `after_preview`，并写入 `applied_to_report=false`。`overall_evaluation`、`document_quality_score`、`score_reason`、`top_blockers`、`severity`、`blocking` 在模型输出任意嵌套层级出现都会拒绝该项。每次调用在 `_private/calls/<Variant>/<游戏>/repeat_<N>/model_artifacts/` 额外生成：

- `secondary_challenge_advice.json` / `.md`
- `secondary_correction_shadow.json` / `.md`
- `phase3_replay_summary.json`

V1.2/V1.3 完成人工收口并存在安全修正时还会生成 `review_report_human_approved.json/.md` 与 `phase3_human_apply_summary.json`；这些文件是人工批准后的新报告，不覆盖冻结 Primary 证据。

`phase3_replay_summary.json` 记录协议回显、冻结 Primary hash、challenge/correct 准入/拒绝/abstain 数、Correction disposition 统计、稳定键与基线锁；正式报告仍为 `primary_locked`，不生成 `review_report_candidate.*`。保存响应可用 `--secondary-benchmark-reprocess` 零调用重放，必须复用原始 messages 和完全相同的真实 profile。

Phase3 人工模板按 `change_type` 使用不同必填字段：challenge 必填 `target_correct / valid / evidence_locatable / actionable / should_split`；correction 必填 `target_correct / accurate / supported / safe_to_apply`。`phase3_acceptance` 要求协议与 Primary 基线锁 100%、直接物化率 0、challenge 目标/证据正确率 100%、人工有效率至少 80%、correct 目标/证据支持率 100%、人工准确率至少 90%。人工标注未完成时只能显示 `pending_human_annotation`。

V2.2 对历史响应保持只读兼容：离线重处理仍按原消息识别真实的 `phase2_v2_1`，不得重建 Prompt 或改写 message hash。`reports/secondary_benchmarks/20260807_102514_reprocessed_20260807_111924` 已在零模型调用条件下完成 10/10 重处理，V2.1 包 ID 与回显率保持不变；确定性 Candidate 将门槛通过率提高到 60%，但 ledger 合法率仍为 60%，不会以系统组装掩盖模型的跨 control 映射或结构错误。

保存响应重处理必须直接复用每格已落盘的 `phase2_control_evidence_packet.json`，禁止根据当前代码重新计算包 ID。若历史消息已降为 legacy，则删除不属于实际协议的陈旧证据包。该保真规则由自动化测试覆盖，避免 Prompt 或证据卡实现升级后把真实历史回显误判为失败。

单根因准入进一步区分资金与经济控制面：扣款事务和派奖事务必须分开；奖池负值下限和单局赔付封顶必须分开。统计时间冲突必须证明对象、指标、范围与执行阶段一致；车辆胜率/赔率与用户下注金额榜不能仅因窗口不同判冲突。原文已有倍率上限、MAX_MUL、强制0倍等相对赔付边界时，不得直接新增“最大赔付完全缺失”，除非能证明现有边界未参与实际结算或与公式冲突。

阶段二 `machine_multiroot` 只统计准入后仍由 Secondary 新增的多根因问题。Secondary 对 Primary 既有混合问题的编辑性提醒单独计入 `preserved_primary_multiroot_finding_count`，不会因 Candidate 按协议保留 Primary 骨架而误判为新增质量失败。

若当前输入中只有一份 requirement 或 numeric 文档，准入层可以把 evidence 开头唯一的“需求文档 /”“数值文档 /”安全解析为真实文档名；存在多份同类文档时禁止猜测。phase2 Candidate 的 Top 3 直接锁定并回指 Primary Top 3，Secondary 只能在其后追加，不得重排或删除。

模型响应中的字符串内未转义引号会先走受限 JSON 修复再解析；原始响应始终保留，基准回放可在零模型调用下重处理。

同模型旧/新协议公平盲测：

```powershell
. .\env.local.ps1
python review.py `
  --secondary-replay-from reports/20260731_105856 `
  --secondary-provider qwen `
  --secondary-profile baseline `
  --secondary-profile phase2 `
  --secondary-repeats 2 `
  --output reports `
  --timeout 600 `
  --model-retries 3
```

离线评估新准入规则时，直接执行：

```powershell
python review.py --secondary-benchmark-reprocess reports/secondary_benchmarks/<派生目录> --secondary-reprocess-profile phase2
python review.py --secondary-benchmark-finalize reports/secondary_benchmarks/<派生目录>
```

该过程不调用模型，也不会原地改写输入基准；程序会自动创建 `<原目录>_reprocessed_<时间戳>` 派生目录，并写出 `reprocess_manifest.json`。汇总会同时给出声称新增、准入新增、拒绝原因、ledger 完整率/合法率/confirmed audit key 重合率、准入后人工有效率、有效召回率、最低 Top 3 保留率与最终字段完整率。

phase2 benchmark 的 `secondary_benchmark_summary.json` 还会输出 `phase2_acceptance`：逐项列出完成率、公平性、字段完整率、ledger 完整/合法率、Candidate/Top3、结构漂移、稳定性和人工质量门槛。人工标注未完成时相应检查为 pending；任一已知机器门槛失败时状态立即为 `failed`。只有 `status = passed` 且 `eligible_for_next_stage = true` 才允许进入下一阶段回放。

## 阶段一：冻结 Primary 的 Secondary 公平基线

阶段一不能分别重跑两套完整 `dual_pass`，否则两次 Primary 自身波动会污染 Qwen Secondary 与 DeepSeek Secondary 的差异。回放命令固定复用历史目录中的：

- `model_artifacts/shared_review_input.json`
- `model_artifacts/primary_review_messages.json`
- `model_artifacts/primary_raw_model_response.txt`
- 由上述原始响应一次性解析并冻结的 `frozen_primary_report.json`

PowerShell 配置可像 `env.local.ps1` 一样从供应商表自动导出 `AI_PROVIDER_QWEN_*` 与 `AI_PROVIDER_DEEPSEEK_*`。当前激活的 `AI_PRIMARY_*` / `AI_SECONDARY_*` 不需要切换，回放只读取命名供应商配置。

标准命令：

```powershell
. .\env.local.ps1
python review.py `
  --secondary-replay-from reports/20260731_105856 `
  --secondary-provider qwen `
  --secondary-provider deepseek `
  --secondary-repeats 2 `
  --output reports
```

输出目录为 `reports/secondary_benchmarks/<时间戳>/`，关键产物包括：

- `benchmark_manifest.json`：人工标注前只公开实验规模、Variant、调用数及公开产物索引
- `secondary_benchmark_summary.json` / `.md`：人工标注前只公开 A/B、完成状态及不暴露 profile 的通用质量指标；完成 finalize 后才写入完整机器与人工验收结果
- `human_annotation_template.json`：公开盲测人工标注表，只保留 Variant A/B、问题正文和七个人工标签，不公开 audit/control、准入结果或协议字段
- `_private/provider_mapping.json`：唯一的 A/B 与供应商映射文件；A/B 每批随机分配，不能从命令参数顺序推断，完成人工标注前不要打开
- `_private/secondary_benchmark_internal.json`：完整 calls、公平性 hash、profile、协议与自动验收数据
- `_private/human_annotation_internal.json`：与公开 annotation ID 对齐的完整准入、audit/control 和事实核验字段
- `_private/frozen_inputs/<游戏>/model_artifacts/frozen_primary_report.json`：本批次所有 Secondary 共同使用的冻结 Primary
- `_private/calls/<A|B>/<游戏>/repeat_<序号>/model_artifacts/`：原始响应、原始 messages、证据包、完整报告、完整 advice 和回放诊断
- `blinded/<A|B>/<游戏>/repeat_<序号>/`：只包含清除 profile/协议标识后的 pipeline、candidate、默认报告和 advice，供人工盲审

程序会验证每款游戏所有调用的 shared input、Primary 原始响应、Primary messages、冻结 Primary report、Secondary messages 和 temperature 是否一致。任一调用失败时保留其失败记录，汇总标记为不可完整配对并返回非零退出码；不会伪装成已完成基线。

人工标注前，公开目录不得出现 `protocol_profile`、`processing_profile`、`phase2_variant_ids`、证据包 ID、profile 名称、模型名或可直接识别 profile 的自动验收区块。完整状态只保存在 `_private`；`--secondary-benchmark-finalize` 完成并锁定人工判断后，才使用内部汇总生成最终公开验收结果。

如果失败原因是模型已经返回内容、但 JSON 解析失败，或稳定性算法需要升级，修复代码后可执行以下命令重处理全部已保存原始响应。该操作不会新增外部调用，所有格仍使用原始响应：

```powershell
python review.py --secondary-benchmark-reprocess reports/secondary_benchmarks/<时间戳>
```

自动汇总的结构指标不等同于人工质量结论。只有在盲态下完成 `human_annotation_template.json` 的 `valid`、`duplicate`、`unsupported`、`overstated`、`understated`、`multiroot`、`actionable` 标注后，才能计算有效新增率、重复率和高价值新增数，并决定是否将 DeepSeek 设为默认 Secondary。

可以直接填写 `human_annotation_template.json`，也可以在同目录新增 `human_annotation_decisions.json`，按 `annotation_id` 提供七个布尔标签与 `reviewer_notes`，保留生成模板不变。填完所有标注后执行：

```powershell
python review.py --secondary-benchmark-finalize reports/secondary_benchmarks/<时间戳>
```

命令会先强制检查 20 次调用已全部配对且公平性不变量通过，再拒绝任何缺项；成功后生成 `human_annotation_results.json`，并更新 `secondary_benchmark_summary.json` / `.md` 的人工指标。整个过程仍只使用 Variant A/B，不读取私有映射，`0/20` 或任何部分失败批次都不能被误标成已完成。

如果当前使用 `--review-mode fusion`，这个探活命令会分别校验主评审模型的 `AI_PRIMARY_*` 和副评审模型的 `AI_SECONDARY_*`，并逐项输出各自的探活结果。
若其中一边缺配置、超时或请求失败，输出会明确标记是 `primary` 还是 `secondary` 出问题，以及对应的失败原因。

## Fusion 模式

`fusion` 模式会同时调用主评审模型和副评审模型：

- 主评审模型负责主评分、主结论、主 `top_blockers`
- 副评审模型只补充主报告里没有的新问题
- 默认沿用主评审模型评分
- 当副评审补进 `3` 个及以上唯一高风险问题时，最终评分下调 `1` 档

推荐命令：

```powershell
python review.py --input requirements --game Racing --output reports --review-mode fusion --require-model
```

`fusion` 模式需要单独配置两套文本模型环境变量：

- `AI_PRIMARY_BASE_URL`
- `AI_PRIMARY_API_KEY`
- `AI_PRIMARY_MODEL`
- `AI_PRIMARY_WIRE_API`
- `AI_PRIMARY_SEED`（可选）
- `AI_SECONDARY_BASE_URL`
- `AI_SECONDARY_API_KEY`
- `AI_SECONDARY_MODEL`
- `AI_SECONDARY_WIRE_API`
- `AI_SECONDARY_SEED`（可选）

视觉模型仍然复用现有全局配置：

- `AI_VISION_BASE_URL`
- `AI_VISION_API_KEY`
- `AI_VISION_MODEL`
- `AI_VISION_WIRE_API`

`fusion` 产物会额外写入：

- `model_artifacts/primary_review_messages.json`
- `model_artifacts/primary_raw_model_response.txt`
- `model_artifacts/secondary_review_messages.json`
- `model_artifacts/secondary_raw_model_response.txt`
- `model_artifacts/fusion_merge_summary.json`

最终 `review_report.json` / `review_report.md` 会标出：

- `review_mode = fusion`
- `primary_model`
- `secondary_model`
- 哪些问题来自“副评审补充”

这个命令不会解析 `requirements/` 下的 `.docx`，只会使用当前 `AI_BASE_URL`、`AI_API_KEY`、`AI_MODEL`、`AI_WIRE_API` 发一次最小文本请求。如果探活通过但正式运行仍失败，再优先怀疑长上下文、模型稳定性或网关限流问题。
## Claude 协议说明

当供应商要求“走 Claude 协议”时，不要再使用 `responses` 或 `chat_completions`，而是把文本模型配置改成：

```powershell
$env:AI_WIRE_API = "claude"
```

这会让 RAD 改走 Anthropic 兼容的 `POST /v1/messages` 协议，并使用 `x-api-key` / `anthropic-version` 头。

注意两点：

1. `AI_MODEL` 不能再写成项目内的占位名，例如 `glm_model`；要改成网站技术人员要求的 Claude 侧模型名，由他们在网关后面自动映射。
2. 如果只是视觉模型走 OpenAI 兼容接口，`AI_VISION_WIRE_API` 仍然保持原值，例如 `chat_completions`。

切完后先探活：

```powershell
python review.py --probe-model --timeout 30
```
