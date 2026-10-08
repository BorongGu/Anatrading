# 恢复原生资格 R1 动作合同

2026-10-08。仅准备，独立反方批准后由根方执行一次。产品实现、真实 unknown 阻断、真实恢复成功分别验收；本动作不授予行情刷新或修改生产 journal 的资格。

私有目录 `artifacts/qualification/tdx-recovery/20261008-r1` 被 Git 忽略。`native_qualification.py` 新增动作逻辑不超过150行；`audit_import.py` 为薄入口，`guarded_stage.py` 原样复用已存 G1 资源观察器。执行命令：`.venv\Scripts\python.exe -X utf8 artifacts/qualification/tdx-recovery/20261008-r1/guarded_stage.py audit-native`。不直接运行主脚本；批准前不启动任何脚本或子进程。

1. 用 `CREATE_NO_WINDOW` 启动本解释器 `-I -S -u -c`，只打印 ready、等待 stdin 一字节。Popen 后立即留 child_pid，ready 读取前以原生 GetProcessTimes 留 child_started_tick；直接对其 Popen 句柄核创建 tick，再验证模块返回 alive。stdin 正常结束、exit0 后保留 Popen 句柄，验证同 PID/tick 为 ended。finally 以 ExitStack 依次尝试 stdin.close、wait(timeout10)、stdout.close、Popen handle.Close；单项异常仍执行其余清理，并判本次资格失败。失败不得据观察超时重启，先按留存 PID/tick 核现有实例；不 Terminate、不 kill、不操作通达信。
2. 对固定 DWORD `0xFFFFFFFF` 做一次原生查询，必须返回 missing、OpenProcess error87、完整1—16384项 Toolhelp 至18；其它结果失败，不循环寻找 PID。该证明限此次枚举时点。
3. 只读绑定客户端 `D:\tdx_64`、规范 LOCALAPPDATA/client-hash state、规范仓库 `data/local/acquisition/20dc43a410af406aa6ba099ce2015f1c`。current/receipt 必须同为冻结 SHA `5fa6af4427152614838483704e9562c4200cdbb08c32e21ad0c7f2d7de1fb343`、旧 unknown run、PID25140、started精确 tick `134359031897815869`。marker/control 和 checkpoint 当前应缺席；已有 `.operation.lock` 必须规范、非空。状态改变、路径不匹配、文件超限、旧实例非同 tick alive，立即失败且不调用 recover。
4. 调用 public recover 的真实 blocked 分支前，封锁并计数 acquisition HTTP/request、socket、HTTPConnection、SDK import、EvidenceStore 构造、身份获取、collect、publication recover、状态 save/write、recovery publish/write、schedule active recover/save_control 及原生文件修改入口。额外拦截 Path.open/builtins.open，写权限仅允许私有资格目录与已有规范非空 operation.lock 的 `a+b`；lock stream 的 write 额外拒绝，确保无法新建或扩展锁文件。recover 对已有 state 的 mkdir 被只读 no-op 替代，其它 mkdir 拒绝。常规锁可取得并释放。封锁触发抛安全异常并计数，不能把异常当成功。
5. recover 必须返回 refresh_unknown/client_task_unresolved，所有封锁计数为0；current、receipt、marker、control、lock、checkpoint、三个可能临时文件的存在/哈希，以及 state/run 目录项，执行前后完全相同。输出仅安全状态、PID/tick、哈希、计数，禁止原件/账户/令牌。封锁结束后只写私有 result JSON。

资源观察器独立记录本执行 PID、原生 creation FILETIME、实际 exe 和100ms内存样本，WorkingSet/PrivateUsage及系统累计峰值均≤2GiB、elapsed<120s。观察非硬隔离；超界 os._exit 的管道关闭让自建 child 读到 EOF 正常退出，不声称强制取消内核调用。只读 API 与正常句柄清理不额外等待客户端。自建 child 的等价 tick/ended 和固定 absent PID，仅证明原生封装；当前 TdxW 同实例 alive 只证明真实阻断安全，持续自动更新、真实已结束后的恢复和新行情仍待后续资格。
