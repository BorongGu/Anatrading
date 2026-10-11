# 同伴相对价格变化 A：有界纯函数合同与验收提案

日期：2026-10-11。状态：[独立复审](../reviews/2026-10-11-peer-relative-review.md) 于 05:00 UTC 关闭 R1—R5，05:19 UTC 通过限定实现；预先八例与资源结果见 [验收记录](../qualification/peer-relative-research.md)。公式与研究取舍见 [030](../research/030-peer-relative-research.md)。本计划优先于 030 的接口摘要，范围只含一个函数及测试，不改 Store、pair/universe、HTTP/UI、采集、成员发现或 B/C。

## 1. 对阻断项的逐项答复

| 项目 | 决定及落点 |
|---|---|
| R1 完整输入 | 接受建议：每股一个完整不可变 Store query，支持公开与内部 OHLC 两种现有读取形状；不支持 cutoff/ordinal 裁剪、跨快照拼接或裸端点 dict。§2 固定计数/身份与可信边界。 |
| R2 异常与资格 | 接受完整正 OHLC 端点规则；§4 区分全局拒绝、局部空值、区间外披露、纯价格诊断。未知复权/闭合/可得时点不会封杀来源算术。 |
| R3 成员与品类 | 不据 `CN_A` 认证 A 股。§3 固定来源身份、品类/币种/日期体系的声明等级，以及腾讯字段映射。仅当前腾讯日线 strict/legacy 两版本，不扩其它来源。 |
| R4 精确输出与资源 | §5 固定 Fraction JSON、单位、异号、原因排序与异常枚举；辅助输入总 16 KiB，预算在扫描/计算前执行。 |
| R5 实测入口与清单 | §6 冻结八个真实案例和六道合成题，不看收益挑窗；用已有原件→获准 legacy→Store，算术/兼容/用户判断三项分别报告。 |

上表保留作者的修改决定；独立批准及实现问题的关闭证据以评审记录为准。

## 2. 函数、完整查询和可信边界

签名冻结为 `peer_relative_report(queries, group_descriptor, target, start_date, end_date)`。所有输入只读；输出为 JSON-compatible dict；无文件、数据库、网络、时钟、环境变量或新依赖。`queries` 必须是 list/tuple，4～50 项；不接生成器/迭代器。a/b 必须为严格 ISO 日，`a<b`。target 是 descriptor 的规范 symbol，恰好一次；不在此入口猜证券代码。

每项 query 必需 `snapshot_id,batch_id,query_id,selection,manifest,metadata,rows,unlocated,counts,batch_checks`。公开 query 另有既有 quality/unlocated_quality/totals；内部版本有且仅有 `read_projection='daily_ohlc_input_v1'`。这些投影标识不改变来源 query 身份。未知顶层字段拒绝；嵌套源 metadata/contract/tokens 保留既有来源字段，不设通用删除过滤器。

完整 selection 的键及语义沿用 Store：`snapshot_id,mode,cutoff,ordinal_start,ordinal_end,fields,versions`；mode 必须 retrospective，三个裁剪字段均 None，fields 必须完整既有 `open,high,low,close,volume,amount` 顺序，versions 等于 manifest.versions。a/b 独立用于分析，不重写 selection。

- rows/unlocated 都须 list/tuple；counts 的 selected_rows/unlocated_rows/batch_rows/batch_unlocated_rows 必需且为非负真 int（拒绝 bool）。分别等于对应列表长度，batch_rows 等于两表合计，batch_unlocated_rows 等于 unlocated 长度；不能以“不详数量”补齐漏传行。
- 每股 rows+unlocated≤20,000、全调用≤200,000。**先检查所有列表长度和总预算，再建 ordinal 集合、日期分组或 Fraction**，不能按 a/b 先裁行。零行完整快照可返回端点缺失，不补记录。
- 每行必需 ordinal/label/tokens/values/checks；ordinal 为正真 int，在每股全部两表中唯一。rows 的 label 为非空规范 ISO 日或不规范但非 None 的待诊断值；unlocated 的 label 必须 None。tokens/values 为 dict；checks 为有 name/outcome 的有限 list/tuple，outcome 仅 pass/fail/not_evaluated。OHLC 键即使不可得也要显式 None。公开 locator/source_label 可有，投影缺少它们不能伪造；追溯统一用 snapshot/batch/ordinal。
- 必需的 64 位小写十六进制 IDs 为 raw_sha256、source_contract_id、batch/snapshot/query；只检查形式及直接对应关系：selection.snapshot_id=query.snapshot_id、selection.versions=manifest.versions、metadata.raw_sha256=manifest.raw_sha256，descriptor 的 snapshot/query 与该股 query 一致。源版本只接受 manifest qualification=`source_evidence_retrospective_only`。沿用 Store 给出的身份，**不在本函数重算 contract/batch/snapshot/query 哈希链**。
- **身份一致性不证明数据真实性。** query_id 只认证 selection，不能发现调用者同步伪造行、计数与哈希；完整性可信边界是现有 Store 未经修改的读取结果。真实调用须先由 Store 每次验证原件。纯函数不声称自己检查了磁盘字节，不接受额外 `verified=True` 升格。合成测试可构造一致输入，其结论只属于合成。
- analysis_id 绑定 §5 的版本引用与有界 descriptor，不重遍历/序列化全部源行做第二个输入哈希。公开附加 totals/quality/locator 与内部 marker 不进入身份；两种可信 Store 读取共享相同来源 ID。篡改载荷却保留旧 snapshot/query 属违反可信输入边界，不承诺凭 analysis_id 识别这种伪造；真实资格验收必须走 Store。

源载荷来自已受来源预算限制的 Store；只检查本函数实际读取的必要容器/字段类型，不建立递归源对象验证器。OHLC 输入仅 str/Decimal/真 int/None，bool/float/其它类型属于 invalid_query；字符串和整数十进制表示最长 128 字符，Decimal 最多 128 个系数位且指数绝对值≤128；超限先记端点 `invalid_price`，再考虑 decimal_value，不能构造百万位 Fraction。tokens 原文本仍由来源保存，不回显到错误消息。

## 3. 有界 group descriptor 与来源映射

descriptor 精确键：`schema_version,group_name,group_axis,selection_date,membership,selection_basis,scope,evidence_refs,members,events`。schema_version=1；group_axis 仅 `business_peers|listing_board|explicit_sample`；membership 固定 `current_members_retrospective`；selection_date 为严格 ISO 日，晚于 a/b 合法且披露。组名/选择依据为非空文本。银行/白酒只表示当前业务样本，科创板保持 listing_board。

members 精确键：`symbol,snapshot_id,query_id`。规范 symbol 与 `symbol_identity` 一致，一股一 query；重复别名、同证券不同版本、重复 snapshot、成员数量/集合不匹配全部拒绝。继续保留 source_claim/declared 级别，没有永久证券 ID 时不宣称跨批发行人识别。

scope 位于 **group 顶层并明确适用于全部成员**，不逐股复制；精确键为 `asset_type,share_class,price_currency,daily_label_basis`，每项为 `{value,evidence_status}`。要求值分别 `stock,A_share,CNY,CN_exchange_date`，evidence_status 仅 `declared|assumed`；共用顶层非空 evidence_refs，引用须支持该组选择及共同适用声明。**声明不改源 metadata 的 unknown，也不授予已认证资格。** 不接 `verified/known` 升格。原来源/声明/传入负证据若明确 B 股、ETF/指数、外币或异步市场，返回 scope_conflict；完全没有声明返回 invalid_descriptor。不能按代码段猜品类，也不能凭 SH/SZ 后缀认证；900901.SH 负例携带已知 B 股证据，另测只有 `market=CN_A` 且无 descriptor 时输入不足。

证据引用固定 `{source_id,version,declared_by}`，三者为非空文本；declared_by 仅 `selection_record|source_document|user_declaration|project_test`。引用是可追溯声明，不做联网验证。名单顺序无意义，规范按 symbol 排序；引用、events 按完整 canonical 内容排序，完全重复项拒绝。

events 为可空列表，每项精确键 `{symbol,snapshot_id,start_date,end_date,kind,evidence_refs}`；成员/版本必须存在，日期有效且与闭区间 [a,b] 相交，引用非空。kind 仅 `halt|corporate_action_unresolved|scope_conflict`；不接“已查无公司行动/已解决/已认证”正资格。start_date=end_date 可描述单日行动；halt 起止均指停牌日期，不能用复牌日当最后停牌日。events 空表示无已提供事件，**公司行动覆盖仍 unknown**，不是已核无事件；事件改变进入身份。scope_conflict 为负证据，不能被声明覆盖。

仅支持 manifest.contract.format_id=`tencent-daily-capture-v1`、version=`1`、capture_version 为 `public-market-capture-v1` 或 `public-market-legacy-reconstruction-v1`；metadata.source=tencent、period/requested_period=1d、response_branch=day、requested_adjustment=none，source_token_mapping.source_date=source_date。none 映射为 `unadjusted_request`，qualification 固定 `request_declared_semantics_unverified`；其余原字段、legacy flags 与未知源单位原样保留在输入身份/限制中。已知 adjusted 声明矛盾拒绝；非腾讯/BaoStock/通达信/Sina 本片统一 unsupported_source，绝不套用名字相似的字段。首片无需扩大证券主数据或复权系统。

descriptor 包含所有 events/refs 的 canonical UTF-8 JSON **总量≤16,384 字节**，单文本≤1,024 字符、每个 refs≤16、events≤64、members≤50，最大深度 8；只允许 schema 指定的键、内建 JSON 类型，bool 不代替整数。预算检查先于完整序列化/哈希，遇到超限即停止；拒绝未知字段、循环、自定义对象和无限迭代器。

已独立构造 50 股完整必需字段、四项共享 scope 和一条引用的 canonical 描述：**9,755 字节**，在 16 KiB 内尚余 6,629 字节。50 股边界因此可实际表示；极长说明仍可因总字节限制被拒绝，上限不保证任意附加说明组合都能放入。

## 4. 日期定位、异常作用域与状态

可靠日期规则只针对本片腾讯合同：label 与 tokens.source_date 都以严格 ISO 解析，禁止替换斜杠、补零或猜 compact 日期。两者都合法且一致时为合格位置；只有合法 label 且原日期缺失/非法，仍是日期完整性未知，不能掩盖原声明。label 不合法/None，但 source_date 合法时，只将其用于异常范围判断，**不得修复为有效端点**。两者合法但相异，位置视为未知，不能挑一个在区间外的日期排除它。

| 输入情形 | 固定行为 |
|---|---|
| metadata quarantine、batch known_negative_sample fail | 整调用 ValueError known_negative_source，无诊断基准。 |
| metadata/manifest/descriptor 已知身份、品类、市场或调整矛盾；batch 对应检查 fail | 整调用拒绝，见 §5。 |
| 行级 code/证券/市场/调整冲突可靠定位于 [a,b]，或日期未知 | 该成员 local_source_conflict，整组 comparison=null；保留各成员其它独立端点事实，冲突成员自身变化也置空。 |
| 行级冲突及普通坏行可靠定位于 a 之前或 b 之后 | 只计 outside_interval 异常，不变更该固定区间算术。 |
| 日期完全未知或两个日期声明矛盾 | 该成员 endpoint_integrity_unknown，整组 comparison=null；不能按 ordinal 推断未来，也不算删异常子集。 |
| source_date 可靠且等于 a/b，但 label 不合法/None | 端点 unlocated_endpoint；与同日好行共同构成候选重复，若≥2 同时给 duplicate_endpoint；comparison=null。 |
| 有确切位置的区间内部普通数值坏行/重复、已知停牌缺行 | 只列路径异常/事件，合格端点仍可算；不填补、不变每日收益。 |
| 已提供 halt 覆盖 a 或 b，源仍有同日合格正 OHLC | 保留来源算术但 status=diagnostic_only，附 halted_endpoint_source_value；该标签不能被称最新可交易收盘。若该端点实际缺失，仍按 missing_endpoint 使比较为空。 |
| 精确端点缺失、重复、缺 OHLC、范围/正值/包含关系或显式价格检查失败 | 该端点失败，成员变化为空，整组 comparison=null；无回退。 |
| 只有量额失败/单位未知、count_saturated、早于请求 start 上下文、coverage=unverified | 保留限制与计数，不阻断端点价格算术。 |
| 调整语义/日历/闭合/known_at/公司行动覆盖未知 | status=source_price_comparison_only，经济收益资格始终 false。 |
| 区间内已提供 corporate_action_unresolved，且来源无冲突、端点合格 | comparison 可保留，但 status=diagnostic_only，全组禁止作经济表现结论；事件按成员披露。 |

固定检查名分类：身份为 `source_code,instrument_identity,declared_instrument,declared_venue`；调整为 `source_adjustflag,source_adjustment,declared_adjustment`；价格为 `numeric.open/high/low/close,ohlc_bounds,nonnegative_prices`；位置为 `label,duplicate_label,source_date_range`。结构 `structure` fail：批次拒绝，行级按日期作用域处理，区间内为 local_source_conflict。tokens.code/source_code 若提供需与规范证券声明一致；tokens.adjustflag/source_adjustment 若提供且与未复权请求有已知矛盾，按调整冲突处理，不忽略。

source_order fail 仅说明来源顺序；日期显式后可算端点，保留异常。数量相关 `numeric.volume,numeric.amount,source_quantity_decimal,nonnegative_amount,zero_volume_amount,conditional_price_bounds,conditional_price_bounds_cent,standard_units,source_units_and_coverage` 不作价格资格。任何未认识的 **fail**：批次 `unsupported_source_check` 拒绝；行级区间内/未知使 `unclassified_source_failure` 并关闭比较，区间外仅披露。未知 pass/not_evaluated 保留，不提升资格。

实现复核补明：上述位置/价格/source_order 检查只支持行级作用域；若批次出现这些 fail，本片没有逐端点定位依据，统一 `unsupported_source_check` 拒绝，不能因已认识名称而忽略。metadata 及 interpretation 的已知 daily_label_basis 反证与品类/币种反证同样返回 scope_conflict。

显式行级 source_date_range=fail 在 [a,b] 内或日期未知时属于 local_source_conflict，区间外只披露。它不同于腾讯正常的 metadata.request_range_mismatch：后者明确表示合法的较早上下文，仍不阻断价格。辅助预算在递归入口累计 JSON 节点的编码字节下界，再作实际 UTF-8 计数，防止共享无环列表在拒绝前指数展开。

端点 OHLC 同时检验规范 values 与存在的 OHLC token：存在 token 若非法或与 values 数值不同，则 endpoint_price_check_failed；不能把失败 token 换成干净 values。校验完整正 OHLC、low≤open/close≤high；不修改旧 daily_bars，也不把其全批 daily_coverage 布尔量直接用于本区间。

## 5. 精确输出、失败与分析身份

最小返回键固定：`method_id,analysis_id,parameters,group,members,coverage,comparison,status,reasons,limitations`。method_id=`peer-relative-source-v1`；parameters={target,start_date,end_date}；group 为规范 descriptor。members 按 symbol 排序，每项为 `{symbol,role,snapshot_id,batch_id,query_id,endpoints,source_change,reasons,anomalies}`，role=target/peer。端点按 start/end：`{date,ordinal,close_token,close_exact,reasons}`；无法唯一定位时 ordinal/close 均 null。close_token 为源精确文本，close_exact 为 decimal_text；投影以同一 row.tokens.close 取得 token。只引用源行身份，不制造投影缺失的 locator。

`source_change`、comparison 的 `peer_median/peer_mean` 单位 ratio；`median_difference_pp/mean_difference_pp` 单位 percentage_point。每个非空数为 `{numerator:"整数",denominator:"正整数",unit:"…"}`，约分、零=0/1，全程 Fraction。comparison 另有 `strict_sign_disagreement: bool`，仅两差乘积<0 为 true；零不算异号，绝无 epsilon。目标失败或任意选定成员不合格，comparison **整体 null**，不单独给同伴基准供误用。

coverage 固定 `{selected_member_count,selected_peer_count,valid_member_endpoint_count,valid_peer_endpoint_count,target_endpoints_valid}`；valid 表示该股双端点及本区间来源资格合格，分母永不缩小。来源区间未知、局部身份冲突的成员不计 valid。顶层 status 仅三种：`source_price_comparison_only|diagnostic_only|unavailable`；经济收益/日历/PIT/总收益等资格写 limitations，全部 false/unknown，不存在 qualified=true。

报告原因完整去重，按此固定优先顺序排列，第一项为主原因：`local_source_conflict,unclassified_source_failure,endpoint_integrity_unknown,duplicate_endpoint,unlocated_endpoint,missing_endpoint,missing_ohlc,invalid_price,invalid_ohlc,endpoint_price_check_failed,corporate_action_unresolved,halted_endpoint_source_value`。多原因同时保留，目标/同伴和 start/end 归属在成员层；不靠输入顺序决定主原因。普通内部/外部异常另计数并列 `{ordinal,scope,codes}`，scope=inside_interval/outside_interval/unknown，按 ordinal 排序；相同 ordinal 合并 codes，不静默截断，最大受源行预算约束。正常非端点行不复制进输出。

结构类全部稳定 ValueError(code)，不回显数据、不泄漏 TypeError/KeyError。按正常验证流程 fail-fast；以下只是枚举分类，不要求为错误优先级扫描全体成员或建立通用验证调度器：

1. 结构/预检：`invalid_queries,member_limit,invalid_query,research_row_limit,universe_row_limit,invalid_dates,invalid_target`。
2. 辅助输入：`auxiliary_input_limit,invalid_descriptor,descriptor_source_mismatch,duplicate_member,scope_conflict`。
3. 源结构：`invalid_selection,full_query_required,invalid_source_id,source_identity_mismatch,invalid_counts,invalid_source_ordinal,invalid_source_checks,unsupported_source,unsupported_period`。
4. 全局资格：`known_negative_source,source_identity_conflict,source_adjustment_conflict,source_structure_failed,unsupported_source_check`。

一个非法调用若同时含多种结构错误，返回首先遇到的相应枚举即可，不承诺重排非法输入仍选同一错误；合法报告的成员、原因与身份必须顺序无关。没有结构/全局错误则进入 §4 空值报告。descriptor 未提供 scope 属 invalid_descriptor；明确 scope 反证属 scope_conflict。

analysis_id=SHA256(canonical JSON)，只绑定 method_id、固定规则版本 `peer-relative-eligibility-v1`、a/b/target、完整规范 descriptor、按 symbol 排序的 `{symbol,snapshot_id,query_id}`。不同新快照即使端点同价也不同 ID；成员/输入顺序重排不改变 ID。可靠未来普通数值变化只要求过去数值不变，不能要求整个 ID 不变；新全局反证或日期未知可以关闭资格。依赖可信 Store 的不可变版本，不声称对人为改写同一 ID 的载荷作重新认证。

## 6. 预先固定的验收清单

### 真实入口及八个案例

只用 029 的现存每股 640 行原件：原银行/白酒选择版本 `anatrading-two-sector-pilot-2026-10-11`，科创板对应 2026-10-11 追加清单，不替换成员。原件和具体 snapshot/manifest/hash 索引留仓库外；读价计算前先冻结私有验收清单版本并记录所用 30 个 query IDs。允许完成既有 legacy 重建后导入 Store，必须保留 legacy/头信息未知；第三片导入资格未完成就将真实阶段记 blocked，先做合成，不能伪装新抓取或为本任务重复下载。

| ID | 原固定 10 股组 / 目标 | a → b | 事先指定的验收目的，非收益预期 |
|---|---|---|---|
| R01 | bank / 600036.SH | 2026-09-28 → 2026-09-30 | 普通短区间，未知语义仍能做来源算术。 |
| R02 | baijiu / 600519.SH | 2026-09-28 → 2026-09-30 | 同窗口另一业务组；不与银行差值合并排名。 |
| R03 | star / 688111.SH | 2026-09-28 → 2026-09-30 | 混合上市板块轴标注，禁止称行业中性。 |
| R04 | star / 688981.SH | 2025-08-29 → 2025-09-09 | 中芯停牌完整位于内部，端点若齐可算并披露不可持续交易。 |
| R05 | star / 688981.SH | 2025-09-01 → 2025-09-09 | 已知停牌日为目标 a，必须 unavailable，不回退至 8/29；selected_peer_count 仍 9。 |
| R06 | star / 688012.SH | 2025-12-18 → 2026-01-05 | 中微停牌完整位于内部，判定同 R04。 |
| R07 | star / 688111.SH | 2025-12-18 → 2025-12-19 | 中微作为同伴缺 b，必须 unavailable，不删该同伴；目标若合格保留独立变化。 |
| R08 | bank / 600036.SH | 2025-01-02 → 2025-12-31 | 长区间公司行动覆盖未核，不承诺无事件；只能来源对照。 |

不先读收益选择以上日期。普通例若有未预见缺失，也按合同报告，不改日期凑成功。R04/R05 注入有原公告支持的 2025-09-01～08 halt；R06/R07 为 2025-12-19～31 halt；公告引用见 029。不伪造拆股负证据给真实公司；已知公司行动诊断路径用下列合成 S6 验证。

对 8 例的每一目标及九同伴，逐项回查两端所有原件候选：有效端点核 tokens/OHLC/日期/ordinal，缺失和重复核完整来源行而非只看派生表。记录 8 例固定总数、selected/valid/failed、全部原因和源限制；每例最多 20 个端点、总 160 个端点检查，重复候选仍须完整列明。私有价格与原件不提交。

### 固定六道算术/解释题

各题价格可由“起点 100、末价=100×(1+变化)”合成，OHLC 设为同一合法价；目标变化及九个同伴变化如下。正确答案在实现前已固定，题目不使用未来收益。

| ID | 输入 | 正确答案与考点 |
|---|---|---|
| S1 | 目标 +3%，同伴全部 +5% | 中位/均值差 −2pp；上涨却落后。 |
| S2 | 目标 −3%，同伴全部 −5% | 两差 +2pp；下跌但较抗跌，不代表赚钱。 |
| S3 | 目标 +5%，同伴 `[0,1,2,3,4,5,6,7,80]%` | 中位 +1pp、均值 −7pp、严格异号 true；保留极端成员。 |
| S4 | 目标 +10%，同伴全部 +5% | 两差 +5pp；4.7619% 属另一个比值定义，不是差。 |
| S5 | 与 S1 相同但一个同伴缺 b | comparison=null；selected=9、valid_peers=8，不得用剩八个重算。 |
| S6 | 目标原价 100→50、同伴不变，提供同日未处理拆股负证据 | 两差 −50pp 仅 diagnostic_only；不能解释为经济亏损 50%。 |

实现验收包括独立 Fraction oracle、严格失败/未来变动/身份/输入不变/资源边界以及真实 decoder→Store 两种读取形状等价测试，覆盖评审 §4 全部反例；另加“已知 halt 覆盖端点但源仍给合格正 OHLC”负例，必须 diagnostic_only 并保留 halted_endpoint_source_value，不能因有标签抹掉停牌。最大有界输入另测一次时间、输出字节和内存代理；不把上限当性能承诺。

“算术/来源兼容通过”要求逐项精确一致、负例行为符合合同、全部原件追溯完成。用户判断效果只在用户回来愿意作答后，按 S1～S6 每题一个固定问题、上述唯一答案、每题 0/1 分记录；未答则未验。先展示单股涨跌信息再展示报告的同题前后变化只能作个案可用性观察，存在提示/学习效应，不报告统计显著改进。预测/交易增量本次不验。

## 7. 当前实际状态

已按独立批准新增 `peer_relative_research.py` 与作者/反方测试；未改第三片 code/tests。170 项 A 专属测试及合计 473 项受影响回归通过，预先 8 例兼容与 50 股/200k 行合成资源验证通过，具体版本和测量方法见验收记录。未由本任务提交/推送。全仓联合回归另记；Windows、用户问答、预测与交易增量仍未验。实现通过不解冻 UI/B/C 或经济收益资格。
