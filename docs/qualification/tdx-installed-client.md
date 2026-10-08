# 通达信已安装客户端：首次只读验收

2026-10-08。用户已安装客户端并报告登录行情主界面。此次只读核对实际文件、进程、监听端口和历史目录；没有运行安装器、加载 SDK、读取账户配置或请求行情／交易接口。

同日后续：用户已另装 64 位版到 `D:\tdx_64`，文件与本地监听检查通过，见文末补充。下文保留首次 32 位检查的原始结论。

**首次检查结论：`D:\txd` 的主程序为 32 位，该安装的 TQ 自动取数路径未就绪。** 不能据此断言所有 32 位版本都不支持 TQ；该版本的手动导出仍待操作验证。随后另装的 64 位版结果见文末。

## 本机证据

| 项目 | 2026-10-08 实查结果 |
|---|---|
| 安装目录／主程序 | `D:\txd\TdxW.exe`；该路径的进程正在运行 |
| PE 架构 | 签名 `0x00004550`，Machine `0x014C`，x86／32 位 |
| 主程序身份 | 15,267,760 字节；SHA-256 `6718ae8629b33875c37da4fc5095f0f9abb4e4f3eda7829d617f5dfaf5336a3b` |
| Windows 签名 | `Valid`；签名主体 Shenzhen Fortune Trend technology Co., Ltd |
| 商业版本号 | 未核定；文件资源仅报通用 `1, 0, 0, 1`，不据此填为 V7.73 |
| SDK | 安装树未找到 `tqcenter.py` 或 `TPythClient.dll`，`PYPlugins` 不存在 |
| 本地接口 | 全量 TCP Listen 查询成功，其中无 17709；未对该端口发请求 |
| 本地历史 | `vipdoc` 下存在市场／周期目录，递归含隐藏文件计数为 0；不据此断言其他缓存为空 |
| 登录状态 | 用户报告已登录；本轮未直接查看原生 GUI，进程存在不能独立证明账号权限 |

私有清单：`artifacts/qualification/tdx-current-client/20261008T0312457543105Z/census.json`，SHA-256 `73c029f66f34a478d33a40c462d0c4053cb11c202298735a3df7266229c78030`。清单不含账户配置或凭据，不提交 Git。

## 下一步安装路线及独立复核

主方检查本机文件，独立 agent `tdx_install_check` 重新读取原厂页面。2026-10-08 的[个人版下载页](https://www.tdx.com.cn/products/singledown.html)仍列 V7.73；普通版条目没有标出 TQ，64 位金融终端明确支持免费用户登录和 TQ。量化模拟版也标示免费、注册用户支持 TQ。这些声明不证明全部历史、字段或所有方法免费。

原厂[安装说明](https://help.tdx.com.cn/quant/docs/markdown/mindoc-1cfsjkbf8f3is/mindoc-1d00kk3jsibbc.html)给出 `PYPlugins/user/tqcenter.py`，本地 [HTTP 说明](https://help.tdx.com.cn/quant/docs/markdown/mindoc-1hdhbmi50d038.html)要求运行支持 TQ 的客户端。独立复核接受“当前 TQ 未就绪”的结论及单独安装 64 位版的最小下一步，未把普通版缺少标示扩大为所有版本不支持。

此前保留的 `artifacts/client-installers/new_tdx64.exe` 本轮再次核验：189,032,880 字节，SHA-256 `183a0b129553b948f9f1c7febed85d4f5a26d60d19407cbe8a331f9e1a889a87`，Windows 签名仍为 `Valid`。其[官方来源](https://data.tdx.com.cn/level2/new_tdx64.exe)与最初下载链见[安装包记录](current-client-paths.md)；本轮未重新下载安装包或执行它。官网元数据仍列 2026-09-22／180.28 MB；没有重新取得当前远端 EXE 的哈希，不能据文件名和大小宣称远端字节永久相同。

建议用户另装到 `D:\tdx64` 并登录行情界面，保留现有目录。安装／协议／登录由用户操作：本会话原生应用 GUI 控制不可用。完成后先核位数、SDK 和接口监听，再按既有 C03 范围，以一个证券、少量已结束日期、未复权且关闭填充的只读请求，对账同版真实日线／分钟导出。权限、单位、精度、历史范围与自动更新资格仍须分别验证。

本次没有产品实现改动；不因客户端启动就宣布真实导出兼容或自动取数成功。

## 同日补充：64 位客户端与 TQ 监听

用户另装目录为 `D:\tdx_64`。实际 `TdxW.exe` 为 AMD64（Machine `0x8664`），17,557,936 字节，SHA-256 `4c822464613fabe4b4235edf171b031d8b209ef68bd7d06dea403e1cd54c1fad`，Windows 签名为 `Valid`。文件资源仍未给出可采信的商业版本号。

`PYPlugins/user/tqcenter.py` 为 165,889 字节，SHA-256 `241358919fd394751a46bb51d64374eb0216f7c22bfa47bc13c48418ba26b1b0`，与先前从官方安装包有限提取的文本逐字节身份相同。`127.0.0.1:17709` 已监听，归属当前安装目录的运行主程序。本轮没有导入 SDK 或调用其方法；监听通过不等于行情字段、账户权限或订单可用。

私有清单为 `artifacts/qualification/trade-access/20261008T0336416361169Z/tdx64-census.json`，SHA-256 `3f77ed26603dfe2d3898910042f0ba7df5abe0093638f02f3633cacd8411ed23`。清单生成时尚未发送行情／账户／下单／撤单请求；后续行情请求另记如下。原生 GUI helper 按规定恢复后仍报告缺少 native pipe，因此未直接观察外部委托配置，也没有变更交易设置。

用户补充券商为长城证券，新账户未开通自动化接口。程序化交易路线与尚缺证据见[接入研究](../research/010-programmatic-trading-access.md)和[候选方案](../contracts/PROGRAMMATIC_TRADING_ACCESS_PLAN.md)。行情只读资格与交易权限分别验收。

## 同日补充：真实 HTTP 请求返回空数据

在每次请求前核对 `127.0.0.1:17709` 的监听程序仍为 `D:\tdx_64\TdxW.exe`。仅向本机发送两次 `get_market_data` 请求，均为 `000001.SZ`、`1d`、截至 `20260930` 的三条记录、未复权、关闭填充；无重试、无重定向，每次限时 10 秒、响应上限 1 MiB。未请求账户、下单或撤单，未导入 SDK。

| UTC 时间 | 对照参数 | 真实结果 | 请求／响应 SHA-256 |
|---|---|---|---|
| 03:46:08 | `field_list=[Open,High,Low,Close,Vol,Amount]` | HTTP 200；外层和证券层 `ErrorId=0`；内层 `Value=[]` | `181ede4859f62b442b8484b94bdcdf1491da4028f689dd41aeb42545a3611520` / `fe2564392ccc7ea3a423d709731d2899a17322f23b36781879f583b68d2dac46` |
| 03:50:51 | 省略 `field_list`；增加响应关联 `id=2`，其余行情参数相同 | HTTP 200；外层和证券层 `ErrorId=0`；内层 `Value=[]` | `23a203f9bee83b8e5345c4f1fd33122b74244a9570b5e875505105c19bbf9260` / `b71fd34d2dfc61976e69849e4bdee075864096fe16e75367659862c929acbd53` |

两次均报 `KlineTotal[000001.SZ]=3`，但实际没有 OHLCV 或日期记录，不能将计数字段记作成功取得三条日线。省略字段筛选仍为空，`Vol` 拼写不足以单独解释当前失败；官方 HTTP 样例使用 `Volume`，后续仍须采用并验证官方字段。

私有证据保存在上述 `trade-access` 目录，第二次请求位于 `field-control/`。首次请求后 `vipdoc` 文件数仍为 0，但这不能排除其他缓存、登录权限或客户端行为。官方[安装说明](https://help.tdx.com.cn/quant/docs/markdown/mindoc-1cfsjkbf8f3is/mindoc-1d00kk3jsibbc.html)给出“系统→盘后数据下载”；先下载一只股票的日线，再重复相同查询并对账同版真实导出，才能检查历史缓存这一解释。

本次未调用 `refresh_kline`：实际安装 SDK 只接受股票列表和周期，没有日期或条数上限，内部等待上限为 600,000 ms，不能把刷新宣称为仅下载三条数据。现阶段通过的是本地 HTTP 可达性；数据完整性、单位、真实导出一致性和交易接入均未通过。
