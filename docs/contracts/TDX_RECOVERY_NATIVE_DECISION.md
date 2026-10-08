# R1原生资格执行决定

2026-10-08。根方接受[039准入反方](../reviews/039-tdx-recovery-native-qualification-review.md)及[R1动作合同](TDX_RECOVERY_NATIVE_QUALIFICATION.md)，合同SHA `67eeb14d3ae668cd1595422e567ac4f81da30445310c38be87d1d18f5d5845b1`；私有helper SHA `9a212b63c77eafb32844ff66d6bf818b6489d5a0321849317f4e1f9368e444ed`，guard SHA `5350dc54c1cd097676324897870f49e2dde6790be1dca55f86281adf058e04ad`。NQ-01清理P1通过ExitStack修复，独立fake五分支通过。

仅允许根方一次guarded `audit-native`：自建hidden Python正常stdin结束、原生身份/终态及缺失枚举；原生产会话必须同实例alive后才允许封锁所有写/HTTP/SDK/Store的blocked recover。已有锁只读等价取放，任何状态变化或禁止入口调用使资格失败。全部产物仅私有ignored目录，不启动工作台、不强停通达信、不清原unknown、不追加行情。

本次动作不是生产恢复成功证明；结束后核实际child/资格进程终态、全禁止计数、原件及控制字节/目录不变和资源日志，交039结果复审。同步原生调用无硬取消资格，整体工具目标active。
