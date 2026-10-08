# U5 私有 helper 与登记实现反方

2026-10-08；依据[运行合同 v0.2](../contracts/TDX_TASK_RUNTIME_QUALIFICATION.md)。私有目录 `artifacts/qualification/tdx-task-runtime/20261008-u5`。初审 helper SHA `131fcbb8ac717c0ae03729cb8a0801ad3faa7a160556a3c14ff340310ab41935`；修订后独立核得 helper SHA `878b7bf64ac834cdba6261431a0f8989f79870c1299d296554bbbb68663a81e4`、manifest SHA `e39d926005e3f67748cb34827e6f56aa226891b955d25c81480ab220457daa86`。当前没有登记或正常 pythonw 运行。

## 初审结论

登记暂冻结。helper 真实 PID/GetProcessTimes FILETIME/GetModuleFileNameW/SID/GetConsoleWindow 路径独立于 venv 启动器，且与 manifest 运行时 exe/hash/SID 比较；network/acquisition/Store 调用均设封闭计数，blocked 行情 unknown 用真实 journal 副本。以下目录缺口必须关闭，并完整审查登记控制器后才能解冻。

1. **P1：私有 state 的 lexical containment 不能证明写入目录。** 当前 `state.is_relative_to(BASE)` 允许固定名字的 junction/symlink 指向生产 state；`due` 随后可以写真实 dispatch。应解析并验证 state 与 BASE 的实际路径，拒绝重解析点/目录别名，逐项绑定 manifest 所有私有输入/输出；source root/client 路径只读。
2. **P2：reserve-hang 必须验证空 state。** 固定私有目录名不足以保证无旧 current/marker/dispatch。启动前应拒绝不干净 state，不把旧 reserved 当成本次持久派发。

helper 复审：解析后 state 等于 manifest 原路径、实际包含 BASE、不得等生产 state/root；blocked 目录严格只有 current，hang 严格为空。上述 P1/P2 已关闭，实际别名路径拒绝由离线注入测试覆盖。

controller 初审仍有缺口：候选 XML 已在 Register 前核动作，但未严格限制为单一 TimeTrigger/Principal/Exec，额外触发器或 ComHandler 会被忽略；update 只排除 Running，尚未排除 Queued 或核 blocked 实际 PID 终态；poll 未核 started nonce/运行时身份；cleanup StopProcess 后缺实际 PID 终态再核。须修订并核动态 XML 后才能登记。

controller 最终复审 SHA `48940dce341e176cbdda62fdc62d6cca347ffc4d729421109b6870dc4b6b8701`：上述缺口均闭合。XML Namespace 精确计数 Principal/Exec/TimeTrigger，并在登记前校验；运行时统一核 nonce/stage/exe/hash/SID/console，只认可明确 NoProcessFound 为消失；update 限 Ready/Disabled 且旧实际 PID 消失；定向 Stop 后 WaitForExit 与 missing 再核。create/update 前 phase seal 核 manifest/controller/XML SHA；登记后异常对自己 nonce/Action/SID 对象禁用注销。实际 COM 行为仍待运行。

blocked XML 独立 SHA `2931a1e21c29a35aaa739032378829d4429f181e54a6a850d019e69d069c4302` 与 seal 相同，单一未来 TimeTrigger，17:27:18—17:30:18 +08:00；09:26:21 UTC 阅读时距离开始 57 秒。Principal/Action/Context 与 manifest 绑定，IgnoreNew、StartWhenAvailable、Hidden、AllowHardTerminate 均 true；AllowStartOnDemand false、PT3M，无重启/重复触发。

**登记解冻：允许根方首次 create-only 登记 blocked 阶段。** 登记时仍须余量≥15秒；若越界，只重新生成 Start/End/XML seal 并复核同一身份及上述边界。未允许手动启动、第二阶段提前更新或生产任务。阶段二仍须第一阶段终态通过及根方核新的动态 XML/PT10S seal。

登记兼容性修订：根方报告第一调用在未来15秒门禁拒绝、第二调用 COM Create2 报 `(1,40) 无法切换编码`，均无 live 启动证据。当前模板用 `encoding="unicode", xml_declaration=True` 生成 Python str 同时宣称 UTF8；[微软 RegisterTask](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/nf-taskschd-itaskfolder-registertask)定义 xmlText 为 BSTR，[Python ElementTree](https://docs.python.org/3.14/library/xml.etree.elementtree.html)区分 Unicode string 与编码 bytes。报错支持声明/COM字符串冲突的推论，原因仍以去声明后的真实登记结果为最小验证。

允许私有 XML 仅去编码声明并更新未来时间/seal，再精确确认同名任务不存在后 Create2；不重跑已启动阶段，不手动 Start。产品最小修复另需根方决策记录、私有去声明登记成功证据，再将 `task_xml` 单行改为 `xml_declaration=False`，现有 XML 测试断言无声明且中文路径完整。其他 Trigger/Settings 不在此修订范围；修订产品 SHA 必须重新封 manifest/phase seal。

去声明后根方报告 COM 登记返回对象，随后服务回读触发 `task_identity_changed` 并自动禁用/注销；只读 cleanup 日志 nonce 匹配且 removed=true，没有 live 启动证据。允许保持全部身份门禁，新增服务实际 XML 证据后诊断重试，仍须精确缺席与未来余量。首次日志修订 controller SHA `9f84c5e1f63ef4a8530b2cbf21ff04fd582081362644954dda6c77c1424cb4c5` 把 WriteAllText 放在 try 外，产生日志 IO 失败绕过清理的 P1；必须移入登记后 try 首行，才可重封并 Create2。不得因归一化猜测而直接删除身份校验。

实际注册 XML SHA `5ff9761f09cbf839b6058b99047ed883b758e5597042651173ccfba0c2999c72` 显示服务省略默认 RunLevel/AllowHardTerminate/Settings.Enabled/TimeTrigger.Enabled。独立只读 `Schedule.Service.NewTask(0).XmlText` 加载该 XML 得到 HardTerminate=true、AllowDemandStart=false、Settings.Enabled=true、RunLevel=0、Trigger.Enabled=true，trigger/action 各1，归一化 XmlText 补出默认节点。与[微软 schema](https://learn.microsoft.com/en-us/windows/desktop/taskschd/task-scheduler-schema)的默认值一致；没有登记。

解析层最终 controller SHA `d2648814c9e1be0c08905cccd0dadf33efd019e755caa96ba42b687726b5469a` 只用上述原生解析替换 XML 输入，原单 surface/Action/Context/SID/Settings/Boundary 门禁均保留。私有 `test_controller_defaults.ps1` 以 AST 仅提取 Assert 函数、NewTask(0) 解析 fakeTask：实际 XML 正例通过；HardTerminate=false、HighestAvailable、Settings.Enabled=false 三项分别被原门禁拒绝。脚本不调用 RegisterTask 或真实 task 操作；首次脚本缺 probeBase 的测试环境错误已修正，最终 exit0。

解析层修订闭合；允许根方更新未来≥15秒 XML/seal、再证实同名任务缺席后 Create2。任务归一化以原生有效值校验，不授予任何运行成功结论；仍禁止 manual Start 或放宽明确错误设置。

阶段一结果复核：helper started UTC09:37:58.566894、finished09:37:59.104652；nonce/实际 pythonw SHA/FILETIME/SID/console0 均绑定，CLI exit2、refresh_unknown/client_task_unresolved，七项调用计数全0，完整分母7 civil/5 trading/2 closed。独立 COM 当前 State3/LastTaskResult2、实际 Xml 与 registered-blocked.xml 全字符串相同；实际 PID38760 明确 NoProcessFound。独立当前生产 current/receipt SHA 均 `5fa6af4427152614838483704e9562c4200cdbb08c32e21ad0c7f2d7de1fb343`，marker/dispatch 均缺席，matches source_before/after。授予真实 TimeTrigger 启动、无控制台身份和 unknown 阻断资格，未授予行情成功。

阶段二动态 XML 独立 SHA `20446484bae109872915c12d33d5e705eed19fef89d9259091989ce6fe1c3ba9` 与 seal 相同；manifest/controller 不变，单 TimeTrigger 17:39:41—17:42:41 +08，PT10S，动作仅换 reserve-hang。09:38:58 UTC 复核时有43秒余量。允许 Update4；调用前仍须≥15秒，越界仅时间/XML seal 刷新，同一 nonce/身份门禁保留，不手动启动。

helper 不执行 SDK/DLL行情接口；ctypes 仅用于所列系统身份 API。socket audit hook 属于补充防线，不能单独证明原生网络隔离。实际任务停止后的目录、PID、FILETIME、原 current/receipt SHA 保留仍待运行证据。

## 已执行离线校验

新增私有 `test_helper_rejection.py`。18 项通过：15 项仅调用 `load_manifest`，`run/native_identity` 强拒绝 stub；另 3 项在 source_proof/_load_plan/native_identity 全 mock 后注入 dirty blocked/hang、resolved escape，证明在 CLI 前拒绝。未执行正常 helper/action，未访问生产 state 或行情。

该测试集合证明 manifest 异常、目录解析逃逸和空 state 校验；没有创建真实 junction，没有证明 Task Scheduler create/update/cleanup 或实际进程终止。登记控制器最终源码和动态 XML 复核仍待完成。
