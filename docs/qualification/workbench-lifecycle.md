# 工作台正常关闭与后台启动接缝

2026-10-08。依据[实现合同](../contracts/WORKBENCH_LIFECYCLE_IMPLEMENTATION.md)、[开工决定](../contracts/WORKBENCH_LIFECYCLE_DECISION.md)、[040合同反方](../reviews/040-workbench-lifecycle-contract-review.md)。本轮仅本地测试与代码；没有启动真实工作台/pythonw、注册或操作任务、加载交易SDK、请求行情或改生产采集状态。

## 本轮行为

- CLI serve 使用固定单worker、asyncio/h11、lifespan=on、use_colors=False、graceful=None 的 owned Server。正常返回还须核生命周期完成事件、失败标志及 force_exit；启动失败和关闭失败均 typed 非零退出。
- 认证空 POST /api/shutdown 停止新 Store 工作，响应 finally 在正常发送、发送异常或取消时同步请求一次 Server 退出。缺 callback/错误鉴权/query/body不关闭；重复合格请求幂等。已提交操作仍由原单线程FIFO/shield完成，随后关闭 Store。
- CLI `--root <指定根> stop-workbench --port <指定端口>` 先核根与当前 token，再发一次空停止请求。总预算10秒、单请求5秒，恢复继承 deadline/guard；门禁过期零POST且 typed 拒绝。未知回执 exit2，不重试、不杀进程、不抢锁。202只代表停止意图。
- 纯 task_xml 生成未注册的固定用户登录模板，两个 PT0S、IgnoreNew、LeastPrivilege、无重试、无强停；拒绝不合法路径、控制/非法XML字符、端口及SID，不创建系统任务。

## 先失败后修订

私有 `artifacts/workbench-lifecycle/initial-red.txt`：18例，10个缺 on_shutdown 的TypeError、8个缺新模块的fixture错误；没有skip/collection错误掩盖。

私有 `phase-xml-red.txt`：6个具体失败；发送前期限过期本应零POST预算拒绝却被报回执未知，DEL/C1路径漏控制拒绝，U+FFFE/FFFF会生成无法解析的XML。窄修后门禁异常分类和字符拒绝均通过。DEL/C1本身并非XML语法错误，不与FFFE/FFFF混称。

测试作者最终 focused：148 passed，2.86秒（关闭路由28、stop/serve/XML120）。包括真实临时Store写入/账本/FIFO/同线程关闭及重开、实际Config在None标准流下的默认失败与显式False构造成功；Server运行使用fake，不是实际后台服务。

根方完整Python回归：**828 passed，1 warning，127.02秒，exit0**，私有 `full-python.txt`。唯一告警为已有Starlette TestClient弃用提示；没有修改UI，因此未重复前端测试。[041独立实现反方](../reviews/041-workbench-lifecycle-implementation-review.md)独立执行过中间stop119例、最终新增尾换行token组9例及既有owner边界；这些不同执行集合不相加作新增总数。

四份G0文件哈希保持冻结值；真实 `after.day` 本轮回归后仍SHA `f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30`。生产current经只读核仍run `20dc43a410af406aa6ba099ce2015f1c`、status refresh_unknown、SHA `5fa6af4427152614838483704e9562c4200cdbb08c32e21ad0c7f2d7de1fb343`。未清未知状态或增加下载。

## 仍未取得的资格

None标准流只有纯配置测试，实际pythonw默认stdio、worker身份/console、系统触发、正常进程终态、真实数据根锁重开及原件/query/JSON/Parquet稳定须另封真实资格后执行。TimeTrigger与自然登录、持久登记、长期持续运行分别验收。未注册XML不能证明无人值守已启用。

卡住的未完成请求体仍可能无限延迟 graceful=None 退出；本轮只证明body完成后尚未submit的上传被503拒绝，已accepted操作不被HTTP取消。接收阶段停止与慢连接治理保留完整系统必需后续。

生产通达信原PID25140的100ns创建时刻134359031897815869经本轮只读原生观察仍alive；原minute refresh_unknown保持。此生命周期切片不解除行情门禁，分钟有效样本、持续日线任务、全市场/自选覆盖、长期日历和完整分析目标均未闭合。
