# 030：U4 日线调度代码反方

2026-10-08。独立阅读新 `tdx_schedule.py`、acquisition与CLI改动及 `test_tdx_schedule.py`、`test_tdx_schedule_budget.py`。以私有临时fixture独立执行三项负例，脚本 `artifacts/qualification/tdx-schedule/reviewer_negative.py` SHA-256 `67052685671ffc61730be7ed12d1e37c6219816fb9b3b8a6140c7f7434b837f4`；只修改本评审与私有脚本，没有产品代码、真实行情、SDK、用户全局状态或任务注册操作。

## 首审结论

**两项P1已有临时fixture复现，修复后需要复审；尚不批准注册或真实调度。** 初次负例运行3项全部失败，含两项同一控制字段缺陷和一项民用时间边界缺陷。测试中的HTTP均由synthetic fixture和真实ASGI工作台替代，不连接用户客户端；不能把测试结果当真实行情资格。

### P1-1：终态槽的残缺journal未阻断所有入口

`tdx_schedule._read_control()` 对终态slot.result只核绑定、status及committed的三个hash/id形状。删除已保存result的 `identity`，仍通过控制验证，普通 `acquire()` 随后允许新采集；删除 `workbench_session_id` 亦然。合同要求终态result是有效终态journal且字段不全fail closed，现有判断弱于这一要求。committed会话字段缺失还会在关联原run恢复时导致 `_recover_locked()` 的字典索引错误。

最小修订：提取现有通用journal验证体供路径读取与内存result共用，保持原journal准入规则；scheduled committed结果额外要求恢复所需workbench_session_id为64位hex。控制读取不发网络，不借补字段、清除dispatch或换root规避损坏。负例在普通入口和due均应零POST拒绝。

### P1-2：主机时区探测耗时后仍使用旧UTC授权POST

`_observe()` 先读取UTC，随后执行最多8秒的主机时区探测，最终仍返回先前UTC。独立负例让原槽在end_at前1秒进入POST守卫，再让host探测推进UTC至end_at后；实际fixture记录一个refresh POST。单调剩余预算正常，无法替代民用期限重核。原生HTTP连接也可能在守卫后耗时，连接后直接request还有同类窗口。

最小修订：主机时区探测后再次读取UTC、核合法性/回拨并持久前值；原生transport完成connect后、真正request前再次执行guard和剩余预算检查。注入transport的 `_request()` 前守卫继续保留，用于功能测试。应增加host探测跨期限与native connect跨期限/预算的负例，保持刷新/发布未知证据，不把未发POST写成成功。

## 其余读到的边界

- 公共手工入口的dispatch读取先于旧current恢复与新建请求；同客户端锁覆盖reserve、internal collection和归槽，公开CLI无dispatch身份参数。marker单边写成及active保留阻断换root/日期/计划，符合合同方向。
- 关联恢复要求current与receipt相同对象及完整绑定；旧手工publication_unknown只恢复原run、本次不占新槽；reserved无journal与preparing空identity保持阻断，未放宽通用journal。
- 关闭槽是单dispatch原子替换；原journal已终态但归槽未落盘时走原run只读核账，不调用能发refresh的普通acquire。请求只有既有唯一工作台写者，无备用库或后台服务。
- deadline ContextVar包住本次due并finally恢复，阶段transport与身份探测取剩余上限；XML仅生成，有结束边界、IgnoreNew、无失败重启，未注册。Hidden不证明控制台窗口隐藏，文档已明确。

首次负例之外，本反方尚未独立运行完整回归；完整回归和本两项关闭证据需在复审记录。当前minute_source_observation未知应原样保留；本评审不授予清除状态、真实POST、注册或终止用户进程的许可。

## 修订代码复审

实际重读修订差异，并独立运行私有三项negative及产品调度／预算测试，**62项全部通过**（含59项产品调度和预算检查）。两项P1关闭，无剩余代码阻断；可进入本合同范围的本地代码验收与XML生成，真实注册／行情资格保持冻结。

本次实读版本SHA-256：

- `tdx_schedule.py`：`2a060c8849cdbc409dc4777f385cfacd856d69061ae02031ee668553f8941b61`。
- `tdx_acquisition.py`：`f2e0a9d52254cd121422eb410effd72af6371d0b5cf7cda524269828a2217af4`。
- `cli.py`：`baca59a6e3dabc59c16f605e09e19da66b86a7b321ddf62ac132dd8992dbece0`。
- `test_tdx_schedule.py`：`4e0a92d931139c17fc6cf8726ddbd2773d564fb4493fa227afefb512ed932c81`。
- `test_tdx_schedule_budget.py`：`f7289b2a547806ffb9b136f982c6af8fef682d300eaac9c0925c8400a8c6bdbc`。

P1-1通过原通用验证体提取 `_validate_journal()` 并在terminal slot加载时复用关闭；committed额外验证64hex workbench_session_id。原journal准入没有放宽。恢复会话读取用get，缺失不会抛KeyError或误记committed。两项独立残缺字段negative均已从失败转为零POST拒绝。

P1-2通过host探测后重读UTC及回拨检查关闭；native `_http()` 完成connect后、request前再次执行POST guard并重核该请求剩余预算。独立host延迟跨end_at负例现为零POST，native连接后的guard中止测试验证request未调用。ContextVar和连接资源finally恢复保持。

本反方只独立执行上述62项，没有重跑整个仓库；根方完整回归结果需单列，不能把这里的局部检查包装为全系统验收。系统任务未启用、连续真实自动覆盖未通过，分钟真实未知未解除。
