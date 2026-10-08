# 日线定时入口：本地代码资格

2026-10-08。依据[实现合同v0.2](../contracts/TDX_DAILY_SCHEDULE_IMPLEMENTATION.md)、[开工决定](../contracts/TDX_DAILY_SCHEDULE_IMPLEMENTATION_DECISION.md)、[029合同反方](../reviews/029-tdx-schedule-implementation-contract-review.md)与[030代码反方](../reviews/030-tdx-schedule-code-review.md)。本阶段新增有限计划到期入口，尚未注册或运行真实系统任务，未新增真实行情请求。

## 已实现与验收

- `acquire-tdx-due --plan <绝对路径>`：按固定SH日历自动选择到期日，无需每次输入日期；只执行一个槽或只恢复原运行。复用通达信日线采集和工作台HTTP唯一写者，未增加数据格式、数据库或服务。
- 同客户端锁贯穿保留、journal建立、采集与归槽；全局dispatch必需标记覆盖手工入口。单边写入、残缺状态、错误关联或未知后台任务停止新请求；同槽重复触发不重复POST。
- 原publication_unknown/committed只GET核账；恢复本次不消费新槽。保留完整7日分母、5交易槽、2休市记录及到期积压。
- 150秒业务预算与POST前民用时间/时区/回拨重核；原生HTTP连接后再次核门禁。窗口跨界或预算耗尽不能开始新POST。PT3M只是未注册XML中的系统终止上限，尚无真实强停资格。
- XML生成包含当前交互用户、LeastPrivilege、IgnoreNew、有限结束日、StartWhenAvailable、无失败重启。Hidden不证明控制台窗口已隐藏。

根方定时/预算59项通过。独立反方先复现“残缺终态收据允许手工入口”和“时区探测耗时跨到期边界仍发送”的两项P1，共3个负例；修订后独立负例与定时/预算共62项通过。通用journal验证提取复用，未放宽旧状态准入；追加SID完整检查、探测后重读UTC和连接后POST门禁。根方最终完整Python回归 **416项通过**，79.33秒，只有既有Starlette/httpx弃用提示。CLI新入口畸形计划实测exit2且不创建数据根。没有UI改动、前端构建或新HTTP性能结论。

这些测试用合成日线、临时控制目录及真实ASGI单写者；只授予故障边界资格，不授予来源兼容、连续日期实际更新或定时系统执行资格。

## 可审阅私有产物与真实状态

私有目录 `artifacts/qualification/tdx-schedule/20261008-u4`：

| 文件 | SHA-256／状态 |
|---|---|
| daily-plan.json | `da5d17ae5763850001ba0b9bc52ec72a3e275d0f41056bc906a0ccfd8753bbf8`；10月8—14日，固定古越龙山1d／本机工作台 |
| daily-task-unregistered.xml | `a49e7f080a12dfb4da40e41e3929a752e7a10c2bac1f1139f9524dbd804ca522`；仅生成，未安装 |
| source-blocker-read-only.json | 2026-10-08T09:08:06.403060Z只读观测；未调用acquire/due |

只读重新核现有全局current仍为分钟 `refresh_unknown`，run `20dc43a410af406aa6ba099ce2015f1c`，current SHA `5fa6af4427152614838483704e9562c4200cdbb08c32e21ad0c7f2d7de1fb343`。真实dispatch与marker均不存在；本阶段未启用调度或改动该收据。它仍阻止新采集；不能以时钟已晚于盘后时间推定客户端后台结束。

## 当前结论与后续

[单次日线自动获取](tdx-daily-acquisition.md)已通过真实客户端验收，无需用户下载或导出；本阶段定时入口代码与未注册XML通过本地检查。**持续无人值守更新尚未通过真实系统触发验收。** 工作台和客户端仍需运行；7日固定日历仅首次资格窗口，不能要求用户每周手工续期来充当长期自动化。

下一步先证明原客户端未知状态已结束，再审精确任务注册/注销与隐藏启动，验真实触发、重启去重和外层终止。随后落实长期日历维护/续期、工作台生命周期、积压恢复、全市场日线及自选分钟。分钟有效样本和同花顺自动接口仍未验，完整研究工具目标保持active。全部私有计划、用户SID、行情、令牌及原文保存于git忽略目录。
