# 腾讯日线公司行动候选：离线原串提取

2026-10-11。以下范围在编码前固定，已通过独立设计审查；实现及实际验收见[资格记录](../qualification/tencent-action-candidates.md)，限制与失败记录一并保留。

## 依据与目的

本次读了[029来源研究](029-automated-ashare-data.md)、[022源记录关联](022-source-action-window.md)、[120股数据资格](../qualification/expanded-daily-data.md)，并核对 `public_market.validate_capture`、`capture_rows` 与旧解码器。补充研究备忘第5.1节及独立普查发现：120份既有原件共76,724行，第6槽有469个非空对象，目标窗有343个。普查只认源对象与位置，没有认证实际经济事件、单位或漏报覆盖。本片不引入新的经济公式，也不把字段名解释为每股现金或已知事件日期。

## 固定入口和结果

新增独立模块 `anatrading.tencent_action_candidates`，入口 `extract_tencent_action_candidates(raw: bytes) -> dict`。输入仅为现有腾讯日线canonical capture包，调用 `validate_capture(raw, "tencent-daily-capture-v1")`；不接受裸response正文、路径或URL。沿用请求、证券回显、JSON、hash、11槽形状与最多640行限制，不改任何旧模块。

结果含 `method_id=tencent-action-candidates-v1`、`source`、`requested_symbol`、`source_symbol`、`response_identity=source_key`，以及 `capture_version`、`capture_sha256`、`body_sha256`、`request_sha256`、`response_headers_sha256`。固定 `qualification=retrospective_source_candidates`、`economic_semantics=unverified`、`coverage=unknown`、`historical_known_at=null`。legacy另保留原 `provenance`、`capture_mode`、`header_cardinality`、`transport_evidence` 与 `provenance_hash_verification=syntax_only`；现有包不能额外证明采集运输条件。

`source_row_count`、`empty_object_count`、`candidate_count`分别计源行、空对象、非空候选。`candidates`按原顺序保存 `ordinal`（从1起）、`source_date`、`locator`（`body:$.data.<源证券>.day[i][6]`）及 `nd/fh_sh/djr/cqr/FHcontent` 五原字符串。完整保留早于请求start的上下文；不设日期过滤，不trim空白、不转数值、不拆分、不合并、不按年度或日期去重。相同源行仍是两条观察，零现金、混合送转、双现金与 `cqr` 不同行日都保留；字符串只作数据，不执行或解释其内容。

## 失败处理

- 空 `{}` 只计空对象，不能推断没有公司行动。
- 缺槽、null、非dict、坏hash或错误源证券沿用现有校验拒绝，不放宽旧输入。
- 空day沿旧解码器拒绝，错误码 `empty_public_market_result`。
- 非空对象必须恰有上述五键且五值均为字符串，否则整份候选提取拒绝。`UnsupportedSourceActionShape`继承 `DecodeError`，错误码 `unsupported_tencent_action_shape`；`context`保留上列来源身份、hash、版本及首个错误的ordinal、source_date、locator，无部分候选结果。旧行情解码的接受范围不变。

## 验收与停止点

先固定异常输入合成测试，再实现纯函数。覆盖五原串、空白/长串/恶意文本、缺键/多键/非字符串、空对象/空day/缺槽/null、重复行/同年度多行/双现金/零现金送转/日期不符、legacy限制、来源/hash与640行边界。逐项原串和原定位为独立参考，不做数值收益测试。

先新测试，再旧相关回归，再完整适用测试。最后只读120个既有canonical包与原件，对照469个对象及343个目标对象，核原件、旧 `capture_rows`/解码/查询与JSON、Parquet导出不变；合成验收和真实兼容分别报告，真实文件留仓库外。不新增网络、依赖、API/UI、CLI采集或数据库写入；不认证经济收益、PIT、事件完整性或原价/复权语义。后续公告与原价核对须另行确定范围。
