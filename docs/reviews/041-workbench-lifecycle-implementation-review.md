# 041 · 工作台生命周期实现反方

2026-10-08，独立反方 `/root/candle_contract_rebuttal`。承接[040合同审查](040-workbench-lifecycle-contract-review.md)、[实现合同](../contracts/WORKBENCH_LIFECYCLE_IMPLEMENTATION.md)及[根方决定](../contracts/WORKBENCH_LIFECYCLE_DECISION.md)。只读审查workbench路由、workbench_lifecycle、cli、_config与新测试，新增本记录；没有修改产品/测试、启动真实服务/pythonw/Task、调用SDK/行情或改生产journal。仅调用纯task_xml进行输入边界复现，未注册XML或操作其字符串内的路径。

## 实现问题与修订区

| ID | 级别 | 实际复现/风险 | 闭环状态 |
|---|---|---|---|
| LI-01 | P1 | task_xml只拒ord<32/UTF8失败；U+FFFE/U+FFFF可UTF8编码，实际成功返回字符串，但ET.fromstring产生ParseError，交付非法XML。DEL/C1会返回合法XML，违反合同拒控制规则；不把后者说成XML格式非法。 | 已闭合。执行方先行5负例red；共享窄正则拒C0/DEL/C1与FFFE/FFFF，路径UTF8/规范化校验保留。反方独立读修订并运行最终stop文件119例全通过，含这5例。无需文件存在/COM/真实Task资格。 |
| LI-02 | P2 | stop外层prePOST remaining通过、内_request remaining到期（尚未调用_http）时，原代码把acquisition_deadline归shutdown_unknown。零POST却报回执未知属于合同阶段分类偏差，安全保守且无重试/成功误报。 | 已闭合。执行方精确时钟负例先red；stop仅重抛该发送前acquisition_deadline，其它POST后异常仍unknown。当前_post_guard=None且_http不产生此错误码，故不会将已发请求误归零POST。反方独立119例包含内_request过期、仅GET发生的断言。 |

最终限定结论：两项修订已独立复核，最终源码与合同局部实现一致，未发现未闭合P0/P1；148 focused与828完整Python回归通过，可接受本切片代码。不据本地green授予真实生命周期或后台资格。

## 当前已核路径

- 新路由沿用LocalBoundary精确Host/Origin/单token及重复header拒绝，参数空集合、实际空body与断连拒绝；缺callback503不改owner门禁。构造阶段拒非callable、async函数和async __call__，production callback限同步owned Server setter。
- 私有JSONResponse在send-start/body的try/finally中同步调用同app once闭包，标called后调用。正常发送后、发送异常/CancelledError均有退出意图，无BackgroundTask/threadpool/call_soon；重复响应共享一次标志。ACK/rootID/Response在owner.accepting=False前同步构造，无await，避免构造失败引入半关闭。
- Owner FIFO/shield/单线程生命周期没有重写。新测试实际使用临时真实Store、accepted慢import及queued query/HTTP waiter取消/close次序，after-body submit503且attempt为空；这些属于无监听端口的合成ASGI测试，不能代替真实Server连接drain或PID/锁终态。
- serve显式Config/Server、lifespan on/use_colorsFalse/独立默认logging副本/无限graceful；固定源码flags/event严格True/False核完才stopped，异常/未started/关闭标志失败均typed。KeyboardInterrupt保持CLI interrupted；不据202或日志缺席断言正常终态。
- stop先于CLI EvidenceStore路径，规范root/port、config根身份/43位ASCII令牌，10秒总量与继承deadline取早、请求≤5秒；_post_guard清空及finally恢复，不将关闭POST导入采集guard。仅一次GET/POST、202严格ack、明确403/503 typed拒绝、其它回执unknown，无重试或换token重投。_config兼容budget默认15，原采集调用不变。
- task_xml只是未注册文本：root/pythonw/cwd/SID/port和Windows list2cmdline参数、ElementTree escaping、同SID Logon/Principal、IgnoreNew、两层PT0S、无restart/强终止/电池idle网络停止。LI-01已闭合；正常XML仅经ElementTree解析/节点断言，未作Windows COM/schema/Task登记或执行资格。

未完成receive可无限延迟graceful=None的可用性缺口仍按040明确保留。body在停止后完成/断连才503，不授主动终止卡住连接或无条件限时退出；实际pythonw/系统Task/登录/持续更新与分钟数据仍另验。

## 最终执行与代码锚点

反方实际执行：修订后route/stop/既有boundaries三个文件113 passed / 4.07s；新增serve/stdio/XML专门用例落盘后，仅补跑stop文件119 passed / 1.10s。两次结果有重叠，113含既有boundaries，不能累加或称全为新增。所有请求为临时root、直接ASGI或HTTP stub，未启动真实监听。

119例的新增覆盖独立读过：fake Server的严格bool失败/字段缺失/event未完成或不可读、SystemExit0/3与初始化/启动后异常、KeyboardInterrupt保留；真实uvicorn.Config在stdout/stderr=None时先复现默认formatter失败，再用独立logging副本和use_colors=False成功。Server仍为fake，此测试不证明pythonw启动或进程终态。纯XML正常测试拒Popen/_http调用，核escaped参数、Logon节点顺序/同SID、两层PT0S与全部固定开关；不等于Windows任务schema验收。

执行方最终两个新测试文件148 passed / 2.86s（route28、stop/serve/XML120），反方已读本地focused-green.txt与phase-xml-red.txt：后者明确6 failed / 8 deselected / 0.70s，包含LI-02及LI-01五例。最终增加令牌尾换行拒绝边界后，反方仅补跑bad_config_token参数组9 passed / 111 deselected / 0.63s，未重跑全文件。新版全148与反方119/113均不可累加。

当前只读源码SHA256（四产品与route测试核保持不变，stop测试以最终148版封定）：

| 文件 | SHA256 |
|---|---|
| src/anatrading/workbench.py | 5726664038246cfb80a23d7183fd5cf97aec21425c0adbc857d06b7758ee1157 |
| src/anatrading/workbench_lifecycle.py | afccd1261b3256e78174b9a9dcc004899e267dc6248385c7a9e2119b3b3b84e1 |
| src/anatrading/cli.py | 3626f42835c8918fd58a8b4616cf7636a2c905b5bff402ac03ed5a25e59c33db |
| src/anatrading/tdx_acquisition.py | 4c7b6c07b866733575aa31c0823a4c49e58624284724e600c12e5e0537cca6b5 |
| tests/test_workbench_lifecycle.py | 3e1bad391444d1a44c46e1d62ca34e5b4e06305877f7486befa20b72792dc98c |
| tests/test_workbench_stop.py | 858a9cdedd7f1b5feaa841b9e36dd9dadfb44ad0649a9ad964a3c96c47152cdb |

根方完整Python回归终态exit0：828 passed / 127.02s，1项既有StarletteDeprecationWarning；反方只读核full-python.txt末尾及六文件哈希仍与表一致，未重复完整运行。未改UI，当前切片未跑frontend；旧浏览器资格不会因此升级。

不授真实后台、注册Task、实际正常关闭/释放锁、持续无人值守更新或分钟恢复资格；下一步须独立封定启动与关闭资格合同。完整系统的receive停止治理仍未完成。
