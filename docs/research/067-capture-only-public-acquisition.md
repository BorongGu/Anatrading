# 067：有界公开捕获与数据库隔离

2026-10-13。基线 `d142513382227380618e113c92b9b31166e0936a`。编码前设计经独立反方确认；本轮仅离线实现，不恢复真实请求资格。

## 问题、选择与数据要求

现行公开采集先构造 EvidenceStore，再读取计划。仅跳过最后导入仍可能初始化、迁移或恢复数据库。为保留原始运输证据且隔离数据库，选择既有 `acquire-public --capture-only`；默认路径保持导入。独立下载器会重复预算、来源限制、锁及恢复合同，因此不新增下载框架或依赖。

研究依据为既有[来源定义与限制](029-automated-ashare-data.md)、[有界运输诊断](055-bounded-transport-phase-diagnostics.md)和实际 `public_acquisition.py`／Store锁实现。没有新增价格、量额转换、公式、统计或金融假设；原单位未知保持未知。本轮没有新增真实源数据或一手来源口径验收。

## 编码前冻结决定

1. 默认生成原 plan-v1；capture-only 生成 `public-market-plan-v2`，顶层 `execution_mode=capture_only` 纳入完整计划哈希。journal、reservation及capture布局不变。resume不允许切换模式。
2. capture-only要求原 `root/public_acquisition/sources` 已存在，不创建权威父目录。目录存在不能证明历史完整，真实发送另需核验原来源限制与预算连续性。不得新根重置历史。
3. resume先只读校验完整计划以路由，再持原 `.operation.lock`，重读计划、检查根身份。直接复用Store的OS锁，描述符相对no-follow打开锁文件，检查普通文件、单链接及inode。恢复不完整标记拒绝。持锁前存在检查关闭目录，持锁后重新打开；发送前复核根、锁和来源目录身份。
4. 新模式禁止 EvidenceStore构造、DB连接、导入、receipt、revision及数据库摘要查询；全部历史attempt禁止committed、Store IDs、reused或revision，block也不得committed。
5. 共用运输、源URL、header约束、reservation、10次发送预算、时限、临时文件恢复、净化和捕获验证。合法非空状态为captured，合法空为empty_result。captured仅说明捕获的运输封套和源形状已验证，不授予数值、入库、覆盖或研究资格。
6. 发布后崩溃在原槽恢复，不重复发送。真正不完整的规范临时前缀保留且原预算不退还，可以下一槽重发；完整错hash/错绑定、非法前缀、多候选、legacy封套一律拒绝。
7. 全部captured/empty_result成功；至少一块完成而其它失败、取消或pending为partial，CLI exit2。无成果取消/interrupted保留130。完成捕获不等于待导入，resume_allowed仅按原可恢复失败及剩余预算。
8. 捕获落盘后取消保留证据，下一块停机。旧二进制不能安全恢复v2：其旧实现可能在拒绝计划前打开Store。必须配套更新CLI和acquisition，不承诺降级零DB。

## 先行异常与验收门槛

冻结矩阵覆盖：v1持久化逐字及完整摘要对照；零Store/DB spies；源限制跨run；发送前落盘和10次预算；五个崩溃边界；部分结果/取消；坏capture与净化；双向共享锁、symlink/hardlink/根和来源目录切换；v2模式篡改及resume参数拒绝；原运输与格式golden回归。

首轮新增测试在产品改动前出现15失败、3通过，证明新增入口／路由尚不存在；三个通用拒绝用例当时仅证实拒绝，没有把它们计作新功能已通过。最小实现后原受影响及新增108项通过。独审随后发现恶意journal.blocks非对象会绕过安全错误，已补四项负例并修正；补持锁后目录重开和发送前身份复核。最终证据见[067验收](../qualification/067-capture-only-public-acquisition.md)。

## 持续停止边界

当前实际网络仍NO-GO：旧来源限制与发送预留历史未恢复核验。全部验证使用合成临时根、假运输或本地故障进程；不访问旧数据库、旧行情原件、真实DNS/市场、登录、浏览器或公开服务。没有来源可用性、Windows原生、性能、PIT、完整覆盖或金融效果的新结论。058 STOP保持。
