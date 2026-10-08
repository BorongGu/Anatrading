# U4 调度设计定案

2026-10-08。根方采纳 [调度方案v0.2](TDX_DAILY_SCHEDULE_PLAN.md)，SHA `eb3d0d9c71e5372fb9450774b692237d6c466f628e6ca9dcc741918116ce0a0c`，及[027反方复审](../reviews/027-tdx-daily-schedule-plan-review.md)；两项方案P1关闭。方案通过后进入具体实现合同，当前仍不解冻产品代码或注册任务。

定案：单个Windows Task Scheduler触发有限CLI，复用运行中的工作台唯一写者；全客户端dispatch门禁覆盖普通手工/due/换计划，保留派发间隙未知；旧运行恢复只关联原运行/原槽，本次不消费新槽。7天仅首次资格观察，长期无手工续期和全市场/自选分钟目标保留，不能把有限首验当最终寿命。

实现合同须固定全部字段、日历日期名单/原文/hash/获取时刻、dispatch必需标记和每次原子替换顺序、关联预分配run_id及owner原生身份、只读恢复接口、总业务deadline、注册XML与注销的精确范围。先测崩溃派发间隙/单边写成/旧run误归新槽/clock回拨/期限和后台超时，再受控注册。不能在serve/import中隐式安装任务，不另开DB或启动第二工作台。

本轮U3留下[分钟未知运行](../qualification/tdx-minute-after-hours.md)，目前新采集已按现行全局门禁停止；后续调度不得绕过这一实际状态。完整工具的数据处理、研究与接口兼容目标仍active。
