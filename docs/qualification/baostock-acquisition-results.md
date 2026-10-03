# 自动取数接口：实际验证记录

日期：2026-10-04。依据 [有限请求协议](AUTOMATIC_ACQUISITION_PROTOCOL.md) 和 [源码前审/反方批准](baostock-pagination-plan.md)。当前仅有资格探测，不向产品数据库写入，不宣称生产采集、全市场覆盖或实时能力。

**最新结果：有界尾区修正后，P01真实取得两页共2,784条5m记录；P02在record结构预检处停止，P03未执行。** 下文保留原失败及诊断过程，固定范围成功不等于完整采集器验收。

## 1. 新增本地验证

独立传输、响应身份/分页、父进程及控制载荷测试合计 **139项通过、50个子用例通过，2.65秒**。命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest `
  qualification/test_acquisition_preflight.py qualification/test_acquisition_process.py `
  qualification/test_baostock_acquisition_probe.py qualification/test_baostock_transport.py `
  -q --junitxml=artifacts/qualification/baostock-acquisition-tests.xml
```

其中父进程测试先观察到4个红灯：worker正常退出但仍为running、缺状态文件或captured未完成收尾，未全部转为incomplete。修复后7个进程用例通过，超时后确认子进程退出，并停止后续案例。行情/控制载荷整合负例证明登录、登出及SDK输出的敏感标记不进入任何保存文件或输出。

本机SDK的两个风险也在不联网的真实`ResultData`对象上复现：满2,000行后把发送函数替换为None返回，`next=False`时`error_code`仍为0并保留旧2,000行；批量接口同样满2,000行时，实际构造出的请求正文变为`query_daily_history_k_AStock / anonymous / 2`，日期被替换。因此探测对历史逐页取证，批量只读首份data。

## 2. 首轮真实请求：停止于P01

实际运行一次默认P01→P02→P03流程，目录：

`artifacts/qualification/baostock-acquisition/20261003T183357030285Z/`

| 项目 | 实际观察 |
|---|---|
| P01参数 | sh.601577，2021-01-04—2021-03-31，5m，adjustflag=3，固定10字段 |
| 行情发送计数 / 保存页数 | 1 / 0 |
| 开始 / 查询终止UTC | 2026-10-03T18:33:57.491845+00:00 / 18:33:58.555282+00:00 |
| 最终状态 | `incomplete`；`error_code=invalid_frame`；`phase=finished`；进程`exited` |
| P02 / P03 | 未执行，没有对应目录 |
| 失败证据 | P01目录仅request.json、status.json，没有page载荷 |

源SDK版本0.9.4，Python3.14.0，匿名公共端点public-api.baostock.com:10030。流程跨过登录检查并发送第一条行情请求；没有保存认证/控制载荷。该结果证明本轮受限传输与实际回复未达成兼容，不能据此认定服务不可用、第二页失败或数据为空。

| 对象 | SHA-256 |
|---|---|
| 运行时探测脚本 | `711d8e88f7c46097f7b565d81578ff1b02d06c62a150420151a0924bdbd32ea0` |
| 运行时受限传输 | `5b8288aa256bf316abc1751083b98eac2d6dac38aceac4c176cd4f6b63cce922` |
| P01 status.json | `5a90f2831f8f9d033ec63929cc6bbf022d9f9228c4867157f1f85475fd319086` |

## 3. 调查结论与剩余不确定性

受限传输将压缩帧总长设为`21 + 声明压缩长度 + 13字节结束标记`；该精确关系尚未从真实线路证据验证。官方SDK等待尾标后只解压`[21:21+N]`，不检查该切片后至尾标间的内容。因此本地模拟帧通过仍不能证明实际帧尾兼容。

在纯内存构造“头+zlib正文+SOH+十进制CRC+尾标”时，当前受限函数拒绝、SDK切片可解压。它支持尾段候选机制，尚未证明真实P01含CRC。五份旧捕获已经被SDK解码，线路尾段未保留；重新压缩也不能还原服务器实际字节。

`invalid_frame`覆盖压缩帧超长、预期位置尾标错误、控制帧尾后有多余字节三个分支；原status没有响应类型/长度，因此原失败分支仍未知。没有通过扩大容差、删尾字符或忽略额外数据修补。

上述判断是D01前的证据边界；原失败目录保留。原P01跨页、P02空首屏和P03批量接口均继续未验收。

## 4. D01实测：长度假设不兼容

[D01协议](FRAME_DIAGNOSTIC_PROTOCOL.md)经另一agent复审、57项离线测试通过后，执行一次，目录为`artifacts/qualification/baostock-frame-diagnostic/20261003T190140638990Z/D01/`。本次未解压或保存行情正文，只有request、status和结构摘要。

| 字段 | 实际结果 |
|---|---|
| 类型／版本 | 96／00.9.10 |
| 声明压缩正文／累计接收 | 46,934／46,980字节 |
| 正文后至结束标记 | **12字节**；尾段形状`other` |
| 结束标记 | 找到，位于本次已读缓冲末端；不证明连接此后没有字节 |
| 原严格关系应用于D01缓冲 | `compressed_length_exceeded` |
| 预声明CRC候选 | `null`，形状不适用，未评估；不能写成不匹配 |
| 状态／行情请求／页数 | `diagnostic_incomplete`／1／0；worker已退出 |
| UTC起止 | 2026-10-03T19:01:40.639897+00:00—19:01:42.043178+00:00 |

现在足以确定一个兼容缺陷：真实D01回复不满足“21字节头+声明压缩正文+13字节尾标”的等式，存在12字节附加尾段。原失败仍缺少相应线路记录，不能把D01分支补写成原P01已观察事实。尾段内容、校验含义及完整行情仍未知。

| D01证据 | SHA-256 |
|---|---|
| frame-summary.json | `dc0a44caf94b6d67f9e28afb34a49973370c7a9994961daa6f2342601bf18802` |
| status.json | `275e82eb13f0e2dad4968d53753461e7dde71b8ff8939ee9652e88b9b06d365b` |
| 诊断代码／测试 | `0ebeafb3306a0ed14db14c9c99ed4991419172ace9b222cfbb6c6e013ec4efa4`／`afd622f940f399f83c73ba417615e76835836e266450207c2f7ef67af257ce48` |

后续选择见[有界尾区兼容补充协议](BOUNDED_TRAILER_AMENDMENT.md)。本报告未授予CRC、网络完整性、来源完整覆盖或产品自动采集资格。

## 5. 有界尾区修正与新一轮实测

按补充协议只对96／99帧分离声明正文与含标记最多64字节的尾区。反方进一步复现首`recv(8192)`会在识别头前先吞入1,013字节尾区；随后修为未完整时最多补齐21字节头，再应用N+64边界。合包大尾与20种分片头负例确认超限时只读取64字节尾区，余量留在socket。控制回复语义、有限解压、字段／身份预检及失败停止规则保留。

独立最终复核49项transport测试及108子用例通过；主方运行全部`qualification`为**218项及112子用例通过，2.93秒**（这组包含早前资格工具，不是产品测试计数）。报告`artifacts/qualification/bounded-trailer-tests.xml`，SHA `ce1013542f5494c61d8850372a89df960f11dcef16ca1e9b14fd96f116a3cbe1`。

最终复审允许另建目录执行唯一一次原顺序，实际目录：`artifacts/qualification/baostock-acquisition/20261003T192327955539Z/`。

| 案例 | 实际发送／已保存页 | 结果及边界 |
|---|---|---|
| P01 | 2／2，2000＋784行 | `captured`、`protocol_end_observed`；2,784行，coverage仍`unverified`。完整响应与SDK单元格相同，SDK顶层adjustflag两页仍为空，原字段／行内为3 |
| P02 | 1／0 | `incomplete`、`invalid_record_body`。无page文件；类型、字段、方法及请求身份门已通过，record JSON解析或容器形状不满足要求。当前安全码未细分，不能断定实际为null、空串或其他结构 |
| P03 | 0／0 | P02失败即停止，未创建P03目录，未执行批量日线请求 |

P01起止UTC：2026-10-03T19:23:28.424507+00:00—19:23:30.015786+00:00；P02：19:23:30.562873+00:00—19:23:31.537992+00:00。两进程均`phase=finished/process_state=exited`；没有自动重试、改参数或写产品数据库。

| 实测对象 | SHA-256 |
|---|---|
| probe | `8e6b27d7479fa17fda648fa39f062f2752eac3e03b9c1bef592337f85a30b4a1` |
| 有界transport | `e33b94216a03d84403ed18327af77b11c60497b97f968d436a680fe1ea1ec3da` |
| P01 page1／page2 | `80e891da9d4398c7bcc7464c4079624364841e850af713be48257b58b21c6a72`／`dc5e64e4192241fe57917910e3b5e4727ea95cd7f3e9ec878eafc2de6b079660` |
| P01 status | `b4b99b75441789a2ec6667590537ee27683bce90db22f2e7c6594d3c683df025` |
| P02 status | `fb9386faa3853607f18b2bc9c1e1a05574066d7592bfeab3f35000c7a524f484` |

两页固定历史样本的[独立审计](baostock-multipage-audit.md)核对13段信封、页号／身份、27,840个字符串单元格及跨页边界；2,784条无重复键或逆序。2021-02-26的48条×10字段与前次固定捕获的480个原字符串完全相同。实际58个日期各48条仅是本次观察，不替代交易日历或分钟阶段分母，coverage仍未验。

## 6. P02的源码事实与下一项证据

`microstructure_papers`仅核读固定SDK和已存官方说明。`history.py:106–109`把整个响应None／空白视为接收失败；`:129`把正文第6段交给`ResultData.setData`。`resultset.py:154–160`在该段`strip()==''`时直接设`data=[]`，非空才解析JSON并取`record`。因此SDK存在“空白数据段”路径；本次探测只接受`{"record":[]}`形式，没有覆盖这个路径。

P02失败正文未保存，安全码同时涵盖JSON失败、顶层结构及record类型错误，尚不能把实际失败归因为空白段。SDK没有把`record=null`正常化为列表的证据，也没有可据以放宽任意坏record的依据。已读官方历史K线、每日更新、首页和0.9.4变更说明未给出空record线路结构。

最小下一步是先评审有限P02诊断：只在固定类型／成功码／匿名方法／字段／请求身份全部通过后，记录该数据段字节数、是否纯空白、JSON是否可解析、顶层类型、record存在性和类型／列表长度等结构元数据，不存字段值或不合格正文，最多一个固定请求。此处只记录建议，没有执行新请求或批准后续兼容修正。P03批量、持续更新和客户端实际导出对账继续未完成。
