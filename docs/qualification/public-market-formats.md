# 腾讯日线／新浪分钟捕获格式：阶段验收

日期：2026-10-11。范围：已批准的[自动取数计划](../plans/2026-10-11-automatic-market-data.md)中格式／解码部分。本文保留早期格式阶段记录，并在末节补记最终集成状态。[独立实现审查](../reviews/2026-10-11-automatic-market-data-review.md)及全仓回归已通过；40份旧真实捕获离线Store验收通过，新CLI真实运输首发失败，详见[采集验收](public-acquisition.md)。

## 实现范围

- `public_market.py`：固定来源请求、规范封套／哈希、严格JSON及编码、市场记录预检、行形状／日期／条数检查、静态合同身份。没有网络、时钟、环境或文件读取。
- `formats.py`：新增两个格式和明确的未规范数量路径；旧四格式的默认解析、合同及全局版本不变。
- 腾讯完整保留早于request.start的上下文、原顺序及重复标签检查；晚于end拒绝。新浪请求声明与缺失响应身份分开。两个格式均不授予永久身份、源时区、known_at、标准单位或完整覆盖资格。
- 源量字符串逐字保存并作Decimal校验，source_volume、volume_shares、amount_cny均为NULL；合法小数不产生integer_fraction。有效OHLC仍可供既有价格研究，数量入口返回missing_quantity。
- 运输、预算、检查点、CLI和多块组合不由本阶段实现或验收；目标视图不改变Store完整上下文或query_id。

## 早期格式阶段实际通过（2026-10-11，最终状态见末节）

先创建合成异常测试，初次执行因新模块尚不存在而失败；实现后迭代并在最终格式代码上执行：

`python -m pytest tests/test_public_market_formats.py tests/test_public_market_adversarial.py tests/test_formats.py tests/test_tdx_http_format.py tests/test_store.py tests/test_store_failures.py tests/test_research_api.py tests/test_volume_api.py tests/test_daily_volume_api.py -q --disable-warnings --maxfail=1`

结果：459 passed，11 skipped，11.28秒。跳过项为既有私有样本门槛，未计为通过。另通过本次修改的py_compile及git diff --check。

覆盖：
- 366/367天、跨年／闰年、640/1970条边界、合法更早上下文、未来于请求end、逆序／重复、空结果、错误调整分支。
- 重算hash后仍恶意的URL／参数、错误callback、嵌套重复键、脚本前后缀漂移、NaN／Unicode异常、字节／深度限制、Content-Type／Encoding及关键头歧义。
- 量额及价格精确值、合法小数源量、非法／负／缺失源量、标准数量NULL、JSON／Parquet、幂等快照、仅qt变化的新版本、旧快照不变。
- 纯解码不读取当前日期，新浪源身份不由请求反填；正则成立的指数／ETF代码也只保留assumed声明。
- 既有HTTP查询、价格研究、数量研究入口读取新格式；这属于ASGI测试，未代替浏览器验收。
- 独立审查者编写的对抗测试，以及从修改前HEAD `321fb32`取得的旧四格式黄金摘要。

独立实现检查发现过一个阻断：固定新浪包装中的控制对象数组可在后续拒绝前进入raw。修正后，预检要求新浪记录具有恰好七个行情键、腾讯记录具有11槽形状；控制对象在持久化之前拒绝。已识别行情的字段类型／数值／日期错误仍可按既有拒绝账本保留原件。该反例在上述最终测试中通过。独立审查者随后重跑122个格式对抗用例全部通过，并确认旧四格式9种合成场景的完整Decoded黄金摘要一致；格式层当前无遗留阻断。这不包含尚未完成的采集／运输部分。

## 尚未取得的资格

- 格式阶段没有发行情请求。后续新产品真实CLI已尝试一次腾讯日线，网络失败且没有HTTP响应／捕获／数据版本；新浪未发，不能标整条链路通过。
- DNS／慢滴硬截止、运输环境、TLS、完整HTTP头检查、取消回收及崩溃恢复的本地故障注入已由[采集验收](public-acquisition.md)单列通过，真实来源网络成功仍未取得；不能由格式测试替代。
- 早先独立批量下载的原件只能复用实际保存的请求、响应头和字节；不得补造缺失头、采集验证或运输保证。该批次不自动构成新产品运输验收。
- Windows原生、浏览器、强断电、跨OS共享盘、最终性能和完整市场覆盖均未跑／未验证。没有量能／VWAP、预测收益或历史当时已可得的资格。
- 整体实现已于04:43 UTC通过[最终独立复核](../reviews/2026-10-11-automatic-market-data-review.md#9-最终独立实现决定与冻结清单)；通过范围与真实网络限制分别保留。


## Legacy与科创板最小兼容补充

经作者／独立审查者明确协议及父任务授权，新增显式离线legacy版本及腾讯attribute四键二进制字符串白名单。规则见计划第10节及029第7节。正常严格v1的完整Decoded黄金摘要保持一致；legacy具有独立合同／raw身份，metadata显示未记录HTTP头数量、未建立运输证据及原manifest／脚本哈希。该版本不能替代网络采集捕获。

合成异常用例先于实现创建。加入`tests/test_public_market_legacy.py`后，重跑上节全部测试并纳入该文件，结果为502 passed、11 skipped，13.05秒。包含legacy模式／provenance／selected-header正反例、同证据幂等／不同manifest身份、严格v1不变和STAR附属字段仅留原件。py_compile和修改文件的diff检查通过。

本轮直接读取并复算了029所列688599实体和十份attribute索引的哈希，仅用于核验附属结构；真实价格没有写入测试。40份legacy封套生成及逐字核验、实际仓库外Store首次导入、重复复用和关闭重开后核对均已通过，最终计数如下。全部格式代码在该审计及最终集成测试期间冻结；此处仍不授予新产品真实网络链路资格。

## 最终集成与真实离线结果（2026-10-11 04:45 UTC后补记）

- 冻结全仓：**1,937通过、0失败、49跳过、1项既有FastAPI/Starlette/httpx弃用警告，68.86秒**。49项跳过保持未完成；源码前后哈希、命令和日志见[采集验收](public-acquisition.md)。
- 独立复核：全部public测试**455通过、0失败、0跳过**，其中独立对抗**173通过**；I1–I5实现阻断已关闭。该子集不与全仓计数相加；早期459/502项为不同选择范围的历史记录。
- 真实旧捕获：40份首次导入全部committed；40次重复导入全部reused，raw/batch/snapshot/query身份保持不变；关闭重开后40个快照逐token核对通过。完整保存**38,900源行**，其中日线19,200、分钟19,700；目标视图**34,205行**，差额4,695为较早日线上下文，没有删源行。分钟仅为近期窗口。
- 真实数据均使用独立legacy捕获版本，保留头数量未记录、运输证据未建立的限制。原数量字符串逐字保留，source_volume、volume_shares、amount_cny非NULL计数均为0；未认证单位、复权、闭合、历史可得性或完整市场覆盖。该轮离线导入0网络请求，原件、库、明细和派生行情留仓库外。
- 新CLI真实验收：腾讯日线首发返回`failed_transient/transport_network_error`；HTTP响应、捕获和数据版本均为0，持久发送计数为1；立即停止，新浪未发、未重试。错误净化后无法确定DNS、路由或来源侧原因，没有限流证据。旧脚本成功不证明新隔离运输通过。
- Windows新采集要求的目录句柄/no-follow/fsync能力不足时在联网前拒绝；尚无原生Windows采集通过结论。浏览器、强断电、网络盘、长期来源可用性、预测和交易增量仍未验证。仓库没有配置GitHub CI，此处均为本地验证结果。
