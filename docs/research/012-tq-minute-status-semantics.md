# 012：分钟空返回与操作终态

2026-10-08。范围为采集接口诊断，沿用[008](008-acquisition-and-revisions.md)、[011](011-unattended-source-capture.md)的时点/源修订研究。没有新指标或预测研究。

## 当前证据

[U3实际观察](../qualification/tdx-minute-after-hours.md)在上海16:16仍只有HTTP成功文字、0条实际分钟和指定缓存不存在。日线已在同一安装真实取得缓存和快照，不能外推分钟路径。主站GUI此前拒绝与本轮API返回之间尚未建立因果。

本轮只读安装 SDK `D:\tdx_64\PYPlugins\user\tqcenter.py`，既有固定SHA `241358919fd394751a46bb51d64374eb0216f7c22bfa47bc13c48418ba26b1b0`。源码1136—1163把1m列为get_market_data合法周期；2712—2748把1m列为refresh_kline合法周期，向原生GetTdxDataStr提交type17/stock_list/period，设置600000ms调用等待。原生返回错误码时该Python函数会打印错误并return None；返回成功时return原字符串。没有执行该SDK或DLL，没有读账户配置。

这只证明该固定SDK的参数和错误表达，不能证明实际17709 HTTP桥的内部控制流。**推论：若某桥忽略Python None返回，可能把原生失败包装成HTTP成功；本轮未定位到实际HTTP桥源码，因此不能把它归为已证原因。** 本地名为tqserver.py的文件头指向TdxAiData云库，它没有所查refresh_kline文本，不能据文件名当作当前本机HTTP实现；未继续读取或启动其服务。

## 后续可区分案例

- 保留当前共享未知，先收客户端加载窗口／真实错误提示或原厂明确的任务完成语义；不能按成功Msg、run_id字符串0或时间经过清除。
- 针对经证据支持的参数转换/主站限制/桥接错误分别写独立有限案例。14位HTTP截止仍未验证，不混成“SDK也不接受14位”；SDK公共时间参数和原生参数是不同边界。
- 若考虑原生SDK路径，先审导入时副作用、DLL身份/签名、初始化/运行身份、仅行情方法及返回字节保存；不能因为已有HTTP调用获准就直接执行SDK。本轮无此执行放行。

当前明确阻断为没有实际分钟记录及对应缓存，操作终态仍缺证据；完整性、经济单位与预测效力尚待验收。已有日线源值处理和[调度设计](../contracts/TDX_DAILY_SCHEDULE_PLAN.md)可继续，正式分钟格式保持冻结。
