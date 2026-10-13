# 065 单日期精确收盘离散：限定验收

2026-10-13；基线 main `a79a8768fd56c8174d7ae678e3f9ec001c51a72b`。新增按需HTTP与独立日线面板，复用064来源和精确算术，无新模型/依赖/采集/公开部署。代码发布另以实际提交/PR为准。

## 用户入口与限制

在“个股研究”读取日线数据版本，点击“打开离散窗口”。日期为空取最近可读来源日期组，包括坏OHLC、重复及原token恢复的失格日期；输入日期只精确匹配，没有相邻日期替换。计算当前及此前19来源日期组，首19不足、完整窗任一成员失格及缺目标日期都有明确原因。图形源序号不裁剪研究前缀，原趋势模型失败不阻断这个面板。

均值、总体方差与原收盘文本精确保留；σ及均值±2σ展示经两端舍入一致性证明的显示值，歧义保留“显示舍入未定”和精确端点。负下界有效，显示0.0000不等于数学零。数值界不代表概率区间，无买卖、95%覆盖、预测或交易收益主张。

整个成功响应含身份、资格与成员，最多65,536 UTF-8字节；超限整份拒绝，不截短资格。前后端都执行字节限，最多20成员；服务端每次仍核验完整来源前缀，最大20,000行含无定位行。日期/截止参数在Store访问前严格校验；未知/重复参数拒绝。默认latest与明确同日的选择身份不同；完整前缀query_id保留，不能把图形裁剪query_id冒充来源证明。

## 编码前设计与回归

[冻结设计](../research/065-selected-close-dispersion.md)经独立反方GO后，先新增纯核/字节边界测试，首次12失败（入口尚不存在），随后实现。客户端先加DTO/流读取测试，首次模块缺失失败，随后实现。共享行投影的旧报告对编码前四份完整合成golden逐字段一致；独立测试另保留17例旧报告golden，不累计为市场样本。

仓库新增23个后端测试覆盖逐日期旧行全等、全报告函数禁止调用、每选窗最多一次exact_window、空/缺日期零次、全部成员/失格原因、最新坏/重复/恢复日期、未来NULL-label披露、当前隔离资格改变、64KiB精确边界和Unicode、临时合成Store/ASGI身份/原件篡改/空查询核验/预检拒绝。

最终允许产品Python集合3693通过、0失败、49跳过、2 deselected、1既有Starlette/httpx弃用警告，149.67秒。49为缺私有样本及Windows原生，不能计实源通过；两项test_http_slow_chunks_do_not_reset_absolute_deadline需真实localhost socket，沿用排除，未重试。全程仅仓库合成夹具和专用临时Store；无真实行情、旧Store或捕获读取。

最终前端Node936通过、0失败/跳过；含新增26项DTO/字节流测试。持久化实际ReactDOM+jsdom22通过（新增19、既有3）；涵盖按需读取、A/B乱序、关闭/取消/卸载晚到、错误后恢复、输入日期切换、同ID来源/截止/源序号/模式/期间/当前资格/声明变化、普通显示名称不重置。构建与类型检查通过；现有主bundle>500kB提示保留，无新增依赖。jsdom为既有外部测试环境，无真实浏览器/网络服务测试。

初稿TypeScript构建因控制流未识别箭头never及未知字段索引失败，改用显式never函数/局部字段收窄后重跑。独立DOM初验发现同ID隔离/known_negative_sample/manifest资格3例旧结果残留；补入实际资格上下文后复验，旧失败日志保留。自有日期DOM夹具曾把2026数据日期误写2025，修正夹具后通过，不改产品日期语义。独审另加source_rejected与computed/全局计数矛盾拒绝用例，最终全部前端回归在同一产品字节上执行。

## 资源观测：原失败与新口径分列

纯来源字典矩阵使用冻结256MiB地址空间/20秒CPU/30秒墙钟/64KiB正文预算，分别独立进程：0、19、20、20,000近上限正价、20,000全零失格、20,000交错失格、20,000重复/无定位。报告耗时约0.00023–0.335秒，整个进程峰值RSS29,072–58,384KiB；响应1,747–5,744字节，exact_window调用0或1。重复/无定位脚本首次在构造夹具时i+1越界，未执行产品工作负载；修正夹具索引后按原预算完成，错误保留。这些进程没有导入API/Store，不能冒充完整应用资源通过。

独立测试者原完整API依赖链两次单次运行均在256MiB RLIMIT_AS下导入libarrow失败，工作负载未开始。原地址空间FAIL永久保留，不提高该预算重试，也不以纯核通过替代。

独立反方及主方随后明确另立物理成本观测：全进程峰值RSS含API/native导入基线≤256MiB，CPU20秒、墙钟30秒、输出64KiB，虚拟空间分记；不限定为增量内存，不声称256MiB AS可运行。实际API适配器配合纯合成Store stub的观测与真实Store IO/完整ASGI性能资格分开。两项单次观测通过新物理RSS口径（仅两项，不冒充全矩阵）：

- 20,000近最大/相邻格点有效价格：适配器0.359655秒，子进程墙钟0.717698秒/CPU0.734533秒，进程峰值RSS158,916KiB；响应5,516字节、20成员，exact_window一次，完整报告零次。
- 20,000全零OHLC失格价格：适配器0.200398秒，墙钟0.478808秒/CPU0.494251秒，峰值RSS160,380KiB；响应5,926字节、20成员/20失格成员，exact_window零次，完整报告零次。

导入后虚拟空间377,572/377,556KiB，记录的虚拟峰值434,256/434,260KiB，明确超过原256MiB地址空间门槛。5ms RSS watchdog观察峰值159,092/160,492KiB；它是尽力观察/终止机制，不是OS硬RSS隔离。数据含原生依赖导入和构造夹具成本，不减去基线。这只能证明本机两类单请求合成内存适配器的有限成本；并发、吞吐、真实Store IO、完整ASGI资源和浏览器响应性能未验。

## 独立最终复核与固定代码

独立反方最终代码GO；独立验收在同一前后hash上68项Python与40项Node全部通过，后者为20项实际ReactDOM交互及20项DTO/流检查。它们与产品套件有重叠，不相加为独立样本。另有只读临时合成EvidenceStore+真实路由功能验收：裁剪图形与完整前缀身份、缺失/篡改原件含空查询、恢复后全部合成文件hash不变；不视为资源或真实数据资格。真实SingleResearch错误不会阻断独立面板，Profiler确认新上下文的首次commit即隐藏旧结果。

独立验收和最终产品全套使用以下字节：
- `src/anatrading/close_dispersion.py`：`a1575edc8808af9b82b588c8849bf9d57a3ab62cb30cf29bc0bb1d21febb0fb7`
- `src/anatrading/research_api.py`：`5383d41711ee7e4399fe43dca3ed21409abb37c4364e8f50d05e688976ce4e89`
- `web/src/selected-dispersion.ts`：`c38c827de1ac6f88337868ec65d1341fbb607c7d2e8961526ffcd5426a3fd5aa`
- `web/src/SelectedCloseDispersion.tsx`：`0f40e0429c9679d542bf95420f1ef142beaefbd04c45a462b7814de809d1877a`

## 仍未完成与复现

真实来源兼容、真实浏览器/截图、Windows原生、PIT、复权/公司行动、完整日历、收盘闭合、稳定延迟、人效与金融效果仍未验；058等既有科学STOP保持。取消只废弃UI结果，不能承诺已排入owner的只读工作终止。任何未来扩展不能据当前小切片自动取得资格。

```sh
.venv/bin/python -m pytest tests/test_selected_close_dispersion.py tests/test_selected_close_dispersion_api.py tests/test_close_dispersion.py -q
env -u DRAWDOWN_FIXTURE_EXPORT .venv/bin/python -m pytest tests -q -ra -k 'not test_http_slow_chunks_do_not_reset_absolute_deadline' --basetemp=<本次独立临时目录>
(cd web && node --test tests/*.test.mjs && npm run build)
# ANATRADING_JSDOM_PATH指向已安装jsdom/lib/api.js，不安装产品依赖：
(cd web && node --test tests/pair-history-dom.mjs tests/selected-dispersion-dom.mjs)
```

此处跳过实源只反映本次私有夹具缺失；复现者若持有文件仍需单独确认其读取权限，不自动授权任何历史数据。
