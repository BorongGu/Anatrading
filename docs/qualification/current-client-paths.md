# G1 · 当前客户端下载与导出路径

访问日期：2026-10-04。一次有限调查，仅通达信 Windows 客户端与同花顺普通 PC 版；不扩展产品清单。读取原厂网页、帮助正文及 HTTP HEAD 后，按新增授权唯一一次下载正常 64 位安装包并核验哈希/签名。**未执行安装包、未安装/启动客户端、登录、注册、接受协议或请求客户端行情。**

**结论：通达信当前官方 V7.73 64 位金融终端明确支持免费用户登录和 TQ；免费量化模拟版明确允许注册用户使用 TQ。已有可验证的零付费客户端路线，但游客能否调用、免费账号具体数据范围和真实导出一致性仍需客户端实测。同花顺已找到一级导出说明，当前普通版的日/分钟文件结构尚未验证。**

本文补充 [002](../research/002-data-access.md) 与 [006](../research/006-domestic-capabilities.md) 的资料状态；不将下载页能力说明提升为 T01/T02 通过。

## 1. 通达信当前版本与免费边界

官方来源链为 [下载中心](https://www.tdx.com.cn/soft.html) → 其嵌入的 [个人版下载页](https://www.tdx.com.cn/products/singledown.html) → `data.tdx.com.cn` 的下载链接。当前下载页比软件更新文章索引更新；不能以索引中的 V7.71 判定当前最新版。

| Windows 产品 | 当前官方标示 | TQ / 登录边界 | 本轮决策 |
|---|---|---|---|
| 金融终端 V7.73，64 位 | 支持免费与收费用户；官网推荐的 64 位版本 | 明确列出支持 TQ；收费账号的交易功能另列，不能将交易权限要求套给全部行情读取 | 优先验证候选；免费用户登录、游客免登录、各类数据额度仍分别验证 |
| 金融终端 V7.73，普通版 | 同样支持免费与收费用户 | 下载页没有给这一项标出 TQ；未证明其支持 TQ，也未证明它完全不支持 | 可作本地导出候选；不先选它验证 TQ |
| 金融终端（量化模拟）V7.73，64 位 | 免费，无券商交易组件 | 明确要求注册用户使用 TQ；不等于匿名即可调用 | 无需券商账户的候选；注册及协议需由用户完成，本轮不操作 |
| 专业研究版 V7.73，64 位 | 仅收费用户登录 | 支持 TQ | 排除出本轮零付费验证路线 |

以上表格是同一官方下载页的当前声明。原厂 [TdxQuant 简介](https://help.tdx.com.cn/quant/) 另说明：本地 `tqcenter` 模式须预先启动支持 TQ 的客户端；支持 64 位 Python 3.7—3.14 等版本，建议 3.13。因此现有 Python 3.14 在其声明范围内，实际动态库兼容性仍未测试。

[官方安装说明](https://help.tdx.com.cn/quant/docs/markdown/mindoc-1cfsjkbf8f3is/mindoc-1d00kk3jsibbc.html) 指向正式版和量化模拟版，并说明客户端目录下 `PYPlugins/user/tqcenter.py` 为支撑文件。无需客户端的 `TdxAiData` 后台模式需要付费订阅，不能替代上述免费客户端路线。原厂没有在这些页面给出“全部数据、全部历史、所有函数永久免费”的承诺。

## 2. 安装包地址、大小与签名状态

先对下列三个官方链接发出 HEAD，均返回 200、无跳转；随后仅下载第一项正常 64 位包。另两项未下载。表中字节数取 HEAD `Content-Length`；官网显示大小和更新时间来自 [singledown.data.js](https://www.tdx.com.cn/products/singledown.data.js)。官网的 MB 标签接近二进制 MiB，验收以字节数记录。

| 候选 / 官方链接 | HEAD 字节数 | 官网显示大小 / 更新时间（时区未标） | HEAD Last-Modified（UTC） |
|---|---:|---|---|
| [金融终端 64 位](https://data.tdx.com.cn/level2/new_tdx64.exe) | 189,032,880 | 180.28 MB / 2026-09-22 18:00:56 | 2026-09-22 10:26:05 |
| [量化模拟版](https://data.tdx.com.cn/mock/new_tdx_mock.exe) | 169,425,328 | 161.58 MB / 2026-09-16 12:39:17 | 2026-09-16 05:27:24 |
| [金融终端普通版](https://data.tdx.com.cn/level2/new_tdx.exe) | 154,724,784 | 147.56 MB / 2026-09-22 17:55:31 | 2026-09-22 10:23:57 |

`Last-Modified`、ETag、官网标示版本、文件内 ProductVersion 与数字签名是不同证据。上述地址使用可变文件名，之后下载前须重新核对，不能把本表当永久文件身份。

### 正常 64 位安装包的实际核验

北京时间 2026-10-04 00:51:06—00:51:25，使用已核对的官方 URL 下载一次，HTTP 200，0 次跳转；下载传输耗时 17.66 秒。设置 15 秒连接、240 秒总时限和 0 重试。执行 session `28010` 已正常结束，退出码 0；没有因等待再次启动下载。

| 实际文件证据 | 结果 |
|---|---|
| 私有路径 | `artifacts/client-installers/new_tdx64.exe`，Git 忽略规则已验证 |
| 大小 | 189,032,880 字节，与本轮 HEAD 一致 |
| SHA-256 | `183A0B129553B948F9F1C7FEBED85D4F5A26D60D19407CBE8A331F9E1A889A87` |
| Windows Authenticode 状态 | `Valid`，状态消息为已验证签名 |
| 签名主体 | `Shenzhen Fortune Trend technology Co., Ltd`；证书组织同名，地区 Shenzhen / Guangdong Province / CN |
| 签名证书指纹 | `D05994A6CB7A51F5EADB48783F5610822DF98294` |
| 颁发者 / 有效期 | DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1；2024-05-13 至 2027-05-13（UTC） |
| 时间戳证书 | DigiCert SHA256 RSA4096 Timestamp Responder 2026 1；指纹 `51D9ABDA034973D84F4266ACA48248E6B369C439` |
| 外层安装器资源 | ProductName 为 `TdxIntall 应用程序`；ProductVersion/FileVersion 均为 `1, 0, 0, 1`，CompanyName 为空 |

本机已有 `C:\Program Files\7-Zip\7z.exe`（22.01），只运行 `l -slt` 列清单，退出码 0；识别到外层 PE（32 位安装器），仅列出四个区段和证书共五项，未展开安装负载，未取得可直接列举的 TQ/SDK/许可文件。没有提取或执行内容，也没有安装解包工具。外层安装器属性不能确定内部终端/SDK 的位数与版本；当前 V7.73 64 位身份来自官方入口，内含程序版本仍待后续只读检查或实际安装阶段核对。

下载页的金山/360 认证字样未用作签名证据。本轮签名结果来自实际文件及本机 Windows 信任验证；所读页面仍未提供可对照的原厂 SHA-256 清单。实际哈希用于锁定本次文件，不能冒充原厂发布的哈希。签名和原厂来源已提供文件身份依据，不证明业务功能或数据权限合格。

私有证据还包括同目录的 `new_tdx64.headers.txt`、`new_tdx64.transfer.json`、`new_tdx64.verification.json` 与 `new_tdx64.listing-verification.json`。可用以下等价只读命令复核，不运行 EXE：

```powershell
$clientInstaller = 'C:\Users\顾卜荣\Anatrading\artifacts\client-installers\new_tdx64.exe'
Get-Item -LiteralPath $clientInstaller | Select-Object Length
Get-FileHash -LiteralPath $clientInstaller -Algorithm SHA256
$clientSignature = Get-AuthenticodeSignature -LiteralPath $clientInstaller
$clientSignature | Select-Object Status, StatusMessage, SignerCertificate, TimeStamperCertificate
(Get-Item -LiteralPath $clientInstaller).VersionInfo |
    Select-Object CompanyName, ProductName, ProductVersion, FileVersion
```

`Get-AuthenticodeSignature` 是 [Microsoft 提供的文件签名读取命令](https://learn.microsoft.com/nb-no/powershell/module/microsoft.powershell.security/get-authenticodesignature?view=powershell-7.5)。此记录为本机本次 Windows 验证结果，未单独审计证书链/吊销缓存；后续文件或环境变化应重新验证。不能把文件 `CompanyName` 当签名证明。

## 3. 通达信本地导出与自动取数能确认到哪一步

- [官方功能演示](https://help.tdx.com.cn/function.html) 说明可将屏幕数据导出为格式化文本或图形。[金融终端在线说明书](https://www.tdx.com.cn/products/helpfile/tdxw/) 的入口标记发布于 2026-09-21；本轮读取了其 [目录/搜索索引](https://www.tdx.com.cn/products/helpfile/tdxw/left.html) 中“数据导出”和“盘后数据下载”的文字。
- “数据导出”文字列出文本、Excel、图形及高级导出，支持选择屏幕/报表内容；“盘后数据下载”文字说明日线与沪深分钟数据按日期范围补充。它们证明官方提供此功能说明，不证明免费账号的所有字段/历史范围均可导出。
- 该说明书的目录与搜索索引存在章节编号/路径差异，本轮尝试对应独立章节页返回 404。因此只引用已经读取的索引正文，不将未打开的单页或其截图列作证据。实际菜单和高级导出是否包含所需完整 OHLCV 仍待同版本操作。
- [官方本地 HTTP 契约](https://help.tdx.com.cn/quant/docs/markdown/mindoc-1hdhbmi50d038.html) 提供 `127.0.0.1:17709` 的调用路径；本轮未启动客户端或访问该端口。`refresh_kline` 的盘中历史限制、量额单位冲突、默认填充与复权窗口问题继续执行 002 的验收，不能由下载页消除。

无需付费账号已经完成：读取官方文档、核实下载地址/大小、下载正常 64 位包及核验哈希/签名。验证 TQ 运行、免费账号数据范围、菜单导出和连续更新，需要实际客户端及其允许的登录状态；**免费用户不自动等于免注册游客**。

## 4. 同花顺普通 PC 版的一级导出入口

[官方下载页](https://download.10jqka.com.cn/index/list?id=1) 于本轮直读显示：普通免费版 **V9.60.71，2026-09-22**；AI 版另列，不混用版本。搜索摘要仍可显示 V9.60.61，以本轮直读为准。当前“说明书下载”入口指向 `help.10jqka.com.cn`，该站跳转到 [牛叉帮助](https://help.10jqka.com.cn/ncbz/index/)。

| 导出路线 | 已读取的一级说明 | 可确认 / 尚不能确认 |
|---|---|---|
| 工具菜单 → 数据下载及管理 → 数据的导入、导出 | [官方帮助正文](https://help.10jqka.com.cn/ncbz/index/content/title/instruction/guid/528657795/nodeid/808_list/)：本地已有数据可导出到目录并在另一台客户端导入；同页提供分钟 K 线数据下载分类 | 确认本地迁移导出路径；文件格式、压缩/专有结构、是否为逐行 OHLCV 文本、当前免费历史范围未知，不能预设为 CSV |
| 表格窗口右键 → 数据导出 | [原厂表格右键帮助](https://www.10jqka.com.cn/ad_mar/man/f2-2.htm)：可选 Excel、文本或剪贴板 | 确认可导出表格；报价截面不等于按日期排列的历史 K 线。需要实测日/分钟历史表格是否能进入此出口 |
| 下载历史后迁移 | [原厂数据维护 FAQ](https://www.10jqka.com.cn/ad_mar/man/f6-6.htm)：讨论日线/1m/5m、本地中间交换格式及导入 | 资料属于旧帮助；不采用其中历史起点、时间和容量描述作为 2026 服务保证 |

当前下载页链接到的帮助系统本身仍含早期 Windows 和 2012 安装包例子，没有标明其全部内容适用 V9.60.71。旧说明可提供实测入口，无法代替当前版本真实导出。未使用 iFinD、智能交易或社区文章来证明普通免费版能力；本轮未核实普通版通用外部 API。

## 5. 下一次有限客户端验收

文件核验 C01 已取得本轮证据，其余为待执行步骤。当前没有请求用户操作或安装/启动软件。

| 步骤 / 关联验收 | 可由只读检查完成 | 需要的实际操作与停止边界 |
|---|---|---|
| C01 文件来源 | 正常 64 位包的官方入口链、HEAD、实际哈希与签名已核验；内部 SDK 清单未读到 | 后续安装/启动需单独安排；不运行交易组件或示例策略。未下载其他候选包 |
| C02 免费登录与 TQ / T01 | 记录产品/位数、TQ 文件存在性、版本和权限类别 | 安装和登录需要后续执行；模拟版注册与协议由用户完成。页面出现收费或权限要求即记录，不能切换付费后台规避 |
| C03 一只股票、少量已结束日期 / T01/T06/T07 | 审核未复权、关闭填充、有限窗口的只读请求 | TQ 仅调用已列白名单行情方法；和同版真实导出逐字段核对。不得运行包含下单/模拟交易的官方示例 |
| C04 普通同花顺真实导出 / T02 | 检查文件扩展名、编码、列、单位、时区、日期维度和哈希 | 用户当前普通版分别提供实际日线、分钟出口。若仅得到截面表或专有迁移包，则该分支继续未验收，不制造示例充当真实导出 |
| C05 历史与当日资格 / T03/T04 | 检查已得样本及来源契约 | 盘后历史与盘中最新闭合分钟分别验证；首次到达、修订和持续更新不能靠静态导出证明 |

**本轮完成状态：官方候选/版本/下载大小/导出文档已核查；正常 64 位包已下载、哈希已固定且签名有效。客户端权限、内部 SDK/许可细项、真实行情导出及自动取数仍未验收。** 调查到此收束，不下载更多包；业务原型与已批准架构未修改。
