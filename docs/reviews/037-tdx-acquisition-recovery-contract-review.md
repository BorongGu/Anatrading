# 037：客户端未知恢复实现合同复审

2026-10-08。收到作者修订完成通知后，独立全文重读[恢复方案v0.2](../contracts/TDX_ACQUISITION_RECOVERY_PLAN.md)、[实现合同v0.1](../contracts/TDX_ACQUISITION_RECOVERY_IMPLEMENTATION.md)、[官方API研究016](../research/016-client-session-recovery.md)，并对照现有acquisition/schedule三入口、双写、journal验证和测试。本轮仅新增此评审；无产品、生产状态、进程、SDK或行情操作。另用本地Python做两个纯时间解析负例，未运行恢复实现或真实客户端资格。

实核文档SHA-256：

- PLAN：`0fc1f65b618d9018a72da172bce450cba3b10884edcf6f60b2eb2d849c28c47e`。
- IMPLEMENTATION：`b659a7ad5ba81fb622f70fb15bf355c041bf3fb158a47a3f61af8542de4b4c63`。

## 结论

**036三项P1在修订契约层关闭，未发现新增P0/P1；根方可据此决定限定开工。** 这只证明设计具备机械实现与故障测试判据，不证明恢复代码通过、原客户端终态、分钟数据可用或正式后台任务已经持续运行。先异常用例、后实现、独立代码反方及真实只读资格保持。

## R01：三入口及所有双写组合关闭

gate明确位于acquire新采集和due初始化control/持久时钟/reserve之前；调度active先走已有保护，无active才进入本恢复。恢复当次无论阻断、未完成或刚完成都返回，HTTP、Store、SDK、新run/槽和control写入为零。已有control与计划不符先拒绝且原bytes保持。

不可覆盖的checkpoint先封存两次原进程终态及新监听稳定证据，才写receipt/current。因此没有“journal已failed但第二监听核证未完成”的正常路径。O/O、N/O、反常O/N都严格绑定原bytes/机械new并只补旧run；两final为N/N即完成，不需要第三个done标记。

N/N下recover幂等返回；下一次acquire/due只核checkpoint、tag、关联与exact final bytes后允许正常流程，不要求已经封结的旧客户端证据再次可查询，也不形成永久提前返回。新run替换current后仅看新run目录，不扫描历史checkpoint；terminal tag缺checkpoint或损坏仍拒绝。落盘后预算/读回失败不会否定下次独立识别N/N；同次禁止继续采集。

故障模型现已准确限于原子replace断点：有合法current可定位后，receipt/必要checkpoint/已确认final缺失拒绝；current整份被外部删除、无dispatch/anchor时无法与初次运行区分，合同明确此能力边界，没有用历史扫描或新全局anchor扩大切片。

## R02：原生终态与100ns关闭

process_observation固定五键和三状态，先验PID为非bool正DWORD；成功句柄的creation与Wait0绑定，missing必须87外加独立Toolhelp完整枚举到18、计数1—16384且原PID缺席。snapshot/First/Next错误、空枚举、原PID仍在、超限或访问拒绝均停止。process与snapshot句柄每路径CloseHandle，Close失败也不落盘；不把Get-Process无输出或观察Python结束当TdxW终态。

checkpoint的prior观察复用这五键，missing严格保留计数/complete=true/error87；不同creation支持PID重用，相同creation只有ended通过。新监听须alive，native tick等其完整started；两次新监听pid/tick/path/指纹一致，且不同于原会话。SDK/EXE/AMD64/唯一监听核查保持，不额外探测任务RPC。

started先regex分离至多7位小数，仅整秒日期交datetime验证，UTC秒差通过整数days/seconds换算，再加7位tick；不使用float/total_seconds或先把7位交datetime。恢复60秒与既有due150秒取较早值，复用deadline、分块及每阶段remaining，无轮询重试、不强停客户端、不声称同步系统调用可硬取消。

**实现时的非阻断提醒**：合同已要求拒绝“无规范offset”和非法时间，不能仅依赖datetime.fromisoformat校验offset子字段。当前Python实测`+01:99`被归一为2:39、`+00:60`被归一为1:00；regex或明确数字边界须拒绝offset分钟≥60，并同样明确小时范围。这属于执行现有拒绝规则，须放入异常用例，不接受归一后的tick冒充原时间。

## R03：原件、路径和机械候选关闭

journal64KiB/checkpoint256KiB，strict UTF-8无BOM、递归重复键/非有限/非整数JSON数值拒绝，typed错误不通过float强转。原bytes canonical base64及SHA保存；old通过完整非终态与额外绝对路径/身份校验，new只能由old变更四个冻结字段，exact序列化bytes和SHA独立确认。终态通用validator的身份放宽不能授权此候选。

root/data_root_id/client/state目录哈希/run32hex/证据目录及每个读写replace目标重新绑定；首切片拒绝任何dispatch_id/plan_hash/slot_id字段与scheduled空identity。checkpoint顶层/观察/native字段键集和类型固定，不覆盖已有final，只有同run临时文件不授予资格。原请求/响应、source字段、coverage、单位与purpose在old原件及new机械对象中保留。

## 开工与验收界限

实施明确覆盖U1“identity任意变化即failed后同次采集”和U4“未关联unknown不核会话终态”的旧规则；旧测试应围绕新证据与同次零请求修订，不能通过保留手工旁路兼容旧绿色结果。scheduled active/reserved/linked/dispatch_unknown及publication/committed原核账行为保留，owner终态不授权关原槽。

根方决定后仅合同限定文件可开工。三个入口的全部断点、同会话活而监听转移、87不完整枚举、1tick精度、候选字段变化、路径与tag丢失、completed下次派发和历史文件不阻断都需实际测试；实现后的代码反方不能由此契约评审替代。

当前方案记录的原TdxW会话仍活，真实再次采集继续阻断；未取得官方同会话任务终结接口证据。不能用合成成功、自建进程终态、checkpoint存在或历史日线成功解除。后续真实原件、恢复、行情预算、生产任务及长期计划分别定范围审核；用户无需被反复要求手工下载来推进这些工程工作。
