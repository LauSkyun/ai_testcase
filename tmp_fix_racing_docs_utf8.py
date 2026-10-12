from pathlib import Path

from docx import Document


REQ_DIRECT_REPLACEMENTS = {
    57: """奖池状态定义：
status_value = ((今日+昨日奖池累计收入) - (今日+昨日奖池累计支出)) / (今日+昨日奖池累计收入)
当累计收入 ≤ 0 时，status_value 直接视为 0，奖池状态判定为“正常”，避免除零异常。
status_value < -10%：低水位；-10% ≤ status_value ≤ 10%：正常；status_value > 10%：充裕。今日/昨日统计口径统一按 GMT+5.5 自然日 00:00 切日，与排行榜时间口径一致。阈值均支持后台配置。""",
    59: """奖池充裕：
仅当 3 个选项都至少有 10 人真实下注，且至少存在 1 个真实下注人数≥1 的候选选项时生效。
服务端先确定唯一 target_option：取真实下注人数最多的选项；若并列则取真实下注金额最高；仍并列则按固定车型顺序 Supercar > Sports > Pickup > ATV > Monster 取第一个。
命中奖池干预后，winner 从合法候选中抽样：target_option 概率固定为 70%；其余 non_target 且真实下注人数≥1 的候选平分剩余 30%；若仅有 1 个 non_target 合法候选，则其独占 30%；若不存在 non_target 合法候选，则 target_option 概率直接为 100%。合法候选中不允许出现 0 人真实下注选项。
服务端仍按正常流程生成 3 个选项的 base_luck，再额外为 target_option 生成 interference_index ∈ [1.03, 1.08]，为 non_target 生成 interference_index ∈ [0.97, 1.00]，最终 final_luck = base_luck × interference_index。
两个隐藏路段一律从“已知路段以外的剩余 4 种地形”中无放回抽取。干预场景下，不按完整 5 种地形的 Top2 直接套权重，而是只对剩余 4 种候选地形按本轮 winner 选项的 V×K 从高到低重新排序：rank1/rank2 权重各 35%，rank3/rank4 权重各 15%。先抽第 2 段，抽中后从候选池移除，再对剩余候选按剩余权重归一化抽取第 3 段。若某个 rank 存在并列，则按固定地形顺序 Expressway > Highway > Desert > Dirt > Bumpy 取靠前者。""",
    61: """奖池低水位：
规则同“充裕”，但 target_option 的确定规则改为：取真实下注人数最少且真实下注人数≥1 的选项；若并列则取真实下注金额最低；仍并列则按固定车型顺序 Supercar > Sports > Pickup > ATV > Monster 取第一个。
命中奖池干预后的 winner 抽样规则与“充裕”完全一致：target_option 固定 70%，其余 non_target 合法候选平分 30%；若不存在 non_target 合法候选，则 target_option 为 100%。若不存在任何真实下注人数≥1 的合法候选，则本轮直接走 3.7.2 的 NO_BET_VOID 流程。
target_option 的 interference_index ∈ [1.03, 1.08]，non_target ∈ [0.97, 1.00]。两个隐藏路段同样从剩余 4 种地形中无放回抽取，并只按剩余 4 种候选的 V×K 排名给权重：rank1/rank2 各 35%，rank3/rank4 各 15%。""",
    72: """与自研游戏保持一致：补贴侧重开最大赔付选项，制裁侧重开最小赔付选项。接口定义：服务端每轮封盘后调用自动化接口，传入轮次 ID、用户标签、新用户/预流失标记、奖池状态、各选项真实下注人数/金额、各选项预计赔付、配置版本号。
接口返回 intervention_type、target_option、winner_policy、target_interference_range、non_target_interference_range、是否覆盖下层逻辑。预计赔付 = 下注金额 × actual_odds（包含 gamma 后的最终赔率）。
target_interference_range 合法默认值为 [1.03,1.08]，non_target_interference_range 合法默认值为 [0.97,1.00]；两者都必须落在 [0.80,1.20] 内，且下界≤上界。服务端收到非法区间、空区间、负值或越界值时，一律视为放行并记录告警日志；接口超时 >300ms 或返回空，则视为放行。
补偿机制：若自动化接口连续 3 轮返回非法数据或连续 3 轮超时，则自动熔断 10 分钟，期间本玩法统一走“放行”逻辑，同时向运营后台与告警群推送 trace_id、round_id、错误类型和原始返回体摘要。""",
}


REQ_TAIL_LINES = [
    "3.7 统一补充规则",
    "3.7.1 赔率、Gamma 与展示口径补充",
    "下注阶段前端显示 display_odds，封盘前允许实时变化，但下注区、下注确认弹窗、下注记录页都必须显示文案：“赔率实时变化，结算以封盘赔率为准”。",
    "封盘瞬间服务端冻结 odds_snapshot，字段至少包含 round_id、option_id、base_odds、gamma、actual_odds、snapshot_time。封盘后 display_odds 不再变化，结算统一以 odds_snapshot 中的 actual_odds 为准。",
    "actual_odds = base_odds × gamma，base_odds = max((B_total × (1-r)) / W, 1.02)。其中 B_total 为参与本轮赔率计算的真实下注总额，r=0.05。",
    "W=0 的选项只保留 display_history_odds 供前端展示，不参与 winner 概率归一化、不参与 actual_odds 计算、不参与赔付；其 odds_snapshot.actual_odds 记为 null。若本轮全部选项 W=0，则直接走 NO_BET_VOID。",
    "正常开奖的 winner 概率公式显式定义为：对所有 W>0 的候选计算 wi = 1 / actual_odds_i，再归一化为 pi = wi / Σw。服务端按 p1/p2/p3 抽取 winner。示例：o1/o2/o3 = 2.0/4.0/5.0，则 w=0.5/0.25/0.2，概率分别为 52.63% / 26.32% / 21.05%。",
    "若本轮仅 1 个选项有真实下注，则 gamma=1，不触发膨胀。示例：A/B/C 真实下注额 = 1000/500/500，B_total = 2000，若 A 中奖，则 base_odds = max((2000×0.95)/1000, 1.02)=1.90，gamma=1，actual_odds=1.90。",
    "新手引导默认演示赔率改为 1.90，并显著标注“演示局，不代表真实赔率，正式结算以封盘赔率为准”。若后续接后台配置，字段名统一为 guide_demo_odds，缺省值也为 1.90，不再使用 3.3 作为默认演示赔率。",
    "3.7.2 下注、扣款、发奖与幂等",
    "下注请求成功后立即扣款并写入订单流水；若下注接口返回失败、超时未落单或轮次已封盘，则不得扣款。",
    "客户端每次下注请求必须携带 round_token 与 client_nonce（UUIDv4）；round_token 由服务端按“轮次ID+用户ID”签发。幂等键 = (round_id, user_id, option_id, round_token, client_nonce)。",
    "相同幂等键重复提交时，服务端必须返回同一笔订单结果，不允许重复扣款；封盘后的请求统一返回 BET_CLOSED，前端 toast“本轮下注已截止”。",
    "开奖确认后立即按 odds_snapshot.actual_odds 发奖；未中奖不返还下注额；若本轮被判定为 NO_BET_VOID 或风控流局，则原路退还全部下注并标记 settlement_status = VOID。",
    "若封盘时三个选项真实下注金额均为 0，则本轮状态直接记为 NO_BET_VOID：不生成 winner_option、不播放赛跑动画、不产生赔率快照与返奖，仅弹出“本轮无人下注，已跳过开奖”，3 秒后进入下一轮。",
    "3.7.3 异常恢复、重连与热更",
    "玩家断线重进时以服务端轮次状态为准：未封盘恢复下注页；已封盘未开奖展示“等待开奖结果”；已开奖则跳过动画直接展示结果弹窗。结算中退出、刷新或重复进入时，以 server_order_id 拉取同一份结算结果，不允许重复结算。",
    "配置热更仅对新开轮次生效；进行中轮次绑定创建时配置快照。服务端重启后按轮次快照恢复，快照至少包含下注数据、赔率、随机种子、base_luck、interference_index、干预决策、结果状态。",
    "3.7.4 新手引导",
    "新手引导为纯前端演示局，不触发真实扣款、奖池注入、发奖与风控；演示页中所有赔率与返奖文案仅用于教学。",
    "3.7.5 下注记录页面",
    "字段：轮次ID、下注时间、已知地形、三个车型、本人下注车型/金额、display_odds_at_click、locked_actual_odds、开奖结果、返奖金额、结算状态、server_order_id。",
    "下注记录主列表默认展示 locked_actual_odds，并标注“结算赔率”；若用户点开详情，可额外看到下注点击时的 display_odds_at_click，用于解释封盘前赔率波动。",
    "胜率统计口径：车型只要在该轮被抽为 3 个可选车型之一即记为参与场次；winner_option 记为胜，其余记负，与是否有真实下注无关。",
    "3.7.6 服务端权威与开奖动画交互",
    "赔率、地形随机、车型随机、base_luck、interference_index、干预决策、开奖结果、奖池、排行榜统计、MAX 可下金额均由服务端计算并推送，客户端仅展示。",
    "图片 4-6、8-11 中出现的“X.X/Y.Y”双值字段属于旧版 UI 样机占位，不作为当前版本开发与验收依据；正式实现统一验收单值 speed_display = V × K × final_luck 的排序与结果。",
    "开奖协议最少字段：round_id、winner_option、finish_order[3]、terrain_sequence[3]、per_segment_finish_time[3][3]、final_luck_snapshot[3][3]、odds_snapshot_version、settlement_status。",
    "开奖顺序以 final_luck 和 terrain_sequence 计算出的原始分段时间为主。奖池干预（WEIGHTED_TARGET_70）场景下，若按原始时间计算出的 winner 与抽样 winner 不一致，服务端可在合法 interference_index 区间与隐藏地形权重内最多重抽 20 次；仅当时间差 ≤ 0.03s 时，才允许做一次不超过 0.03s 的微调修正。若 20 次仍无法满足，则回退为按原始时间结果开奖并记录审计日志。自动化/白名单或新用户优化等 FORCE_TARGET_WIN 场景不走该回退分支，服务端必须输出 target_option 为最终 winner。",
    "开奖动画阶段从 5 秒调整为 7 秒，要求完整展示三段赛道推进与最终名次落定。除返回按钮和音效按钮外，其余交互按钮全部置灰。",
    "3.7.7 MAX 与按钮规则",
    "MAX 有效下注额 = min(当前用户余额, 1000000 - 当前轮次该选项已下注真实金额)。每位玩家每轮只能选择 1 个车型下注；首次成功下注后，其余 2 个车型下注按钮立即置灰。",
    "MAX 金额由服务端在界面刷新、余额变化、收银台返回、下注成功后实时重算并下发；MAX 有效下注额 < 10 宝石时按钮置灰，不允许点击。",
    "所有下注金额均为宝石整数；MAX 计算结果若出现非整数，统一向下取整到整数宝石。",
    "3.7.8 假数据展示防穿帮",
    "目标展示人数 = max(10, floor(真实人数 × 1.35))；目标展示金额 = max(500, floor(真实金额 × 1.35))。前端每 5 秒刷新一次目标值，每 1 秒向目标值线性逼近，并叠加受控随机增量（人数 ±2，金额 ±50）。",
    "最终展示值必须满足“真实值 ≤ 展示值 ≤ 目标值”。若真实值上升则展示值只能单调不减追赶；若真实值下降，则先冻结当前展示值 3 秒，再在接下来的 5 秒内线性过渡到新目标。",
    "自动化验收补充：必须提供 6 组回放数据集，覆盖真实值突增、突降、长时间不变、频繁抖动、弱网补帧、轮次切换 6 类极端场景。验收脚本按秒采样，校验展示值边界、单调性、回跳上限、过渡时长和 FPS，不再只依赖人工观察。通过阈值固定为：越界次数=0、展示值回跳≤2人/50宝石、单次过渡完成时长≤8秒、平均 FPS≥55、P95 FPS≥48、连续运行30分钟额外内存增长≤20MB。",
    "3.7.9 奖池风控与干预计数",
    "单轮预计赔付必须同时满足：≤ 本轮真实总下注的 300%，且 ≤ 当前奖池余额 + 2000000 宝石；奖池安全水位低于 -500000 宝石时触发风控熔断。",
    "硬性赔付上限：单注最大赔付 = 5000000 宝石，单轮最大赔付 = 10000000 宝石。若任一候选结果超过硬上限，则直接触发风控流局并原路退还全部下注。",
    "风控执行顺序：1）封盘并冻结 odds_snapshot；2）计算各方案预计赔付；3）若任一方案超硬上限则本轮流局；4）若未超硬上限但奖池安全水位 < -500000，则忽略所有干预，强制选择预计赔付最小且真实下注人数≥1的选项为 winner；5）若不存在真实下注人数≥1 的候选，或连最小赔付方案也超边界，则流局；6）其余场景按 自动化/白名单 > 用户优化 > 奖池干预 > 正常开奖 执行。",
    "生产环境的奖池干预最低参与门槛默认是“3 个选项真实下注人数均 ≥ 10”；测试/预发环境允许通过配置项 intervention_min_real_bettor_count 将门槛降到 1，并允许 GM 注入 mock_real_bet_count/mock_real_bet_amount 回放同一套分支逻辑，避免验收阶段必须堆真实用户。",
    "组合验收矩阵至少覆盖 6 组：自动化+奖池、自动化+新用户、自动化+奖池+风控、新用户+奖池、白名单+风控、奖池+弱网恢复。每组都要校验最终命中的 winner_policy、winner_option、trace_id、odds_snapshot_version 与 settlement_status。",
    "3.7.10 结果弹窗昵称截断",
    "TOP3 昵称最多展示 8 个中文字符或 16 个英文/数字字符，超出部分以“...”截断；点击头像或长按昵称时展示完整昵称。",
    "3.7.11 弱网验收标准",
    "客户端下注请求超时时间 = 5 秒；超时后提示“网络异常，请检查下注记录”，禁止自动重试。恢复后客户端主动拉取最新轮次状态和个人下注记录，与服务端订单表对齐后刷新 UI。",
    "弱网恢复接口至少返回：round_id、round_status、winner_option、finish_order、odds_snapshot、server_order_id、settlement_status、refund_amount（如流局）。拿到返回后客户端必须完成余额对齐、按钮状态恢复、结果弹窗去重、订单列表去重和 UI 全量刷新。",
    "3.7.12 干预数值统一口径",
    "正常开奖时先为每个选项独立生成 base_luck ∈ [0.90, 1.10]，再按分支乘以 interference_index 得到 final_luck = base_luck × interference_index。文档中“Luck 乘子区间”均指 interference_index 区间，不直接覆盖 base_luck。在正式写入开奖结果前，一律使用 target_option 表示干预目标；只有最终 winner 落库后才允许使用 winner_option 字段名。",
    "有利地形直接采用 Racing数值文档 中的 Top2 车型排序：先对目标车型计算 5 种地形的 V×K，再移除已知路段地形，只对剩余 4 种候选重排 rank1-rank4，并按 35%/35%/15%/15% 分配隐藏路段权重。",
    "3.7.13 配置表蓝图",
    "必须提供以下配置表及默认值：terrain_weight_config（stage_slot, terrain_rank, weight，默认 hidden_slot_2: rank1=35, rank2=35, rank3=15, rank4=15；hidden_slot_3 沿用剩余候选的归一化权重）；vehicle_advantage_config（terrain_id, top1_vehicle_id, top2_vehicle_id, rank3_vehicle_id, rank4_vehicle_id, rank5_vehicle_id, computed_by=V×K）；payout_config（rake_rate=0.05, gamma_alpha=0.05, gamma_beta=1.5, gamma_cap=2.0）；intervention_config（pool_low=-10%, pool_high=10%, target_prob=70%, non_target_total_prob=30%, target_range=[1.03,1.08], non_target_range=[0.97,1.00], intervention_min_real_bettor_count_prod=10, intervention_min_real_bettor_count_test=1）；risk_control_config（single_max_payout=5000000, round_max_payout=10000000, pool_floor=-500000）。",
    "所有配置项都必须声明字段名、类型、默认值、可配范围、生效维度（全局/轮次）、是否支持热更；未声明的配置不得进入开发。",
    "3.7.14 自动化/白名单接口字段定义",
    "请求字段最少包含：round_id、config_version、pool_status、candidate_options、real_bet_count_by_option、real_bet_amount_by_option、estimated_payout_by_option、user_tags、new_user_flag、churn_risk_flag。",
    "响应字段最少包含：intervention_type、target_option、winner_policy、target_interference_range、non_target_interference_range、override_lower_layers、trace_id。winner_policy 当前只允许 WEIGHTED_TARGET_70、FORCE_TARGET_WIN 或 FORCE_MIN_PAYOUT。",
    "若自动化接口返回非法 winner_policy、非法 target_option、非法区间或 trace_id 缺失，服务端统一按“放行”处理，并写入 automation_fallback_log；连续 3 轮异常触发 10 分钟熔断。"
]


NUM_APPEND_LINES = [
    "Top2 优势车型名单（按 V×K 排序）：",
    "Expressway：Top1=Supercar，Top2=Sports，Rank3=Pickup，Rank4=ATV，Rank5=Monster。",
    "Highway：Top1=Sports，Top2=Supercar，Rank3=Pickup，Rank4=ATV，Rank5=Monster。",
    "Desert：Top1=ATV，Top2=Pickup，Rank3=Monster，Rank4=Sports，Rank5=Supercar。",
    "Dirt：Top1=Pickup，Top2=ATV，Rank3=Monster，Rank4=Sports，Rank5=Supercar。",
    "Bumpy：Top1=Monster，Top2=ATV，Rank3=Pickup，Rank4=Sports，Rank5=Supercar。",
    "vehicle_advantage_config 字段定义：terrain_id、top1_vehicle_id、top2_vehicle_id、rank3_vehicle_id、rank4_vehicle_id、rank5_vehicle_id、computed_by、config_version。",
    "terrain_weight_config 默认值：hidden_slot_2.rank1=35，hidden_slot_2.rank2=35，hidden_slot_2.rank3=15，hidden_slot_2.rank4=15；hidden_slot_3 继承剩余候选归一化权重。",
    "隐藏路段干预配置示例：若目标车型为 Supercar 且已知路段为 Expressway，则剩余候选地形为 Highway、Desert、Dirt、Bumpy；按剩余 4 种地形的 V×K 重排后，rank1=Highway，rank2=Desert，rank3=Dirt，rank4=Bumpy，对应权重 35/35/15/15，并按无放回方式抽取两个隐藏路段。",
]


def rewrite_tail(document: Document, start_index: int, lines: list[str]) -> None:
    while len(document.paragraphs) < start_index + len(lines):
        document.add_paragraph("")
    for offset, text in enumerate(lines):
        document.paragraphs[start_index + offset].text = text
    while len(document.paragraphs) > start_index + len(lines):
        last = document.paragraphs[-1]
        last._element.getparent().remove(last._element)


def append_unique_lines(document: Document, lines: list[str]) -> None:
    existing = {paragraph.text for paragraph in document.paragraphs}
    for line in lines:
        if line not in existing:
            document.add_paragraph(line)


def main() -> None:
    requirements_dir = Path("requirements")
    req_path = next(path for path in requirements_dir.glob("*.docx") if path.name.startswith("musee"))
    num_path = next(path for path in requirements_dir.glob("*.docx") if path.name.startswith("Racing"))

    req_doc = Document(str(req_path))
    for index, text in REQ_DIRECT_REPLACEMENTS.items():
        req_doc.paragraphs[index].text = text
    rewrite_tail(req_doc, 73, REQ_TAIL_LINES)
    req_doc.save(str(req_path))

    num_doc = Document(str(num_path))
    append_unique_lines(num_doc, NUM_APPEND_LINES)
    num_doc.save(str(num_path))

    print(req_path)
    print(num_path)


if __name__ == "__main__":
    main()
