# 严格局部高低点与来源窗口确认

2026-10-09。研究与数据算法反方闭环，无未关闭阻断。目标是逐柱复盘可定位来源中的局部结构，并把极值中心与后续窗口齐备标签分开。形态数量减少不证明无信息噪声已经消除。

## 实际阅读

- 主 agent 读取 [TradingView Williams Fractal](https://www.tradingview.com/support/solutions/43000591663-williams-fractal-indicator/) 主体全文、[MetaTrader5 Fractals](https://www.metatrader5.com/en/terminal/help/indicators/bw_indicators/fractals) 定义正文：通常以中心和左右各两柱描述，具有确认延迟。文中的交易解释不作为本项目预测证据。
- 主 agent 与研究 agent 读取 [AmiBroker PEAK](https://www.amibroker.com/guide/afl/peak.html)、[Using Zig-Zag in trading systems](https://www.amibroker.com/kb/2014/03/06/using-zig-zag-in-trading-systems/) 全部主体：这些ZigZag派生功能可以使用未来信息，最后一段稳定所需延迟取决于价格反转。本功能固定来源柱窗口，不采用它们的路径语义。
- 研究 agent 读取 [通达信函数表](https://help.tdx.com.cn/gspt/docs/markdown/redword/functionlist.html) ZIG/ZIGA、PEAK/PEAKBARS、TROUGH/TROUGHBARS 条目，均标未来函数。读取 [TradingView ZigZag](https://www.tradingview.com/support/solutions/43000591664-zigzag-indicator/) 计算、构造、投影、限制；其左右相等价规则有区别，末点可替换。该文档不能替代ta.pivothigh源码资格。另完整读取 [Pivot Extension](https://www.tradingview.com/support/solutions/43000599888-pivot-extension-strategy/) 的右侧确认延迟说明。
- 主 agent 完整读取 [Stock Indicators Fractal](https://python.stockindicators.dev/indicators/Fractal/) 主体；研究 agent 完整读取固定提交 [Fractal.Series.cs](https://github.com/facioquo/stock-indicators-dotnet/blob/fab911375ea700661c1eed584c7f1e1c605a3268/src/Indicators/e-j/Fractal/Fractal.Series.cs)。中心高遇邻柱>=即取消、中心低遇<=即取消，两种判定独立；库保存中心日期，末S根无法判定。本项目独立记录窗口确认标签，不依赖该库。库span下限2，本项目radius1作为明确的三柱局部数学定义，并不声称完全复制库接口。MetaQuotes源码未取得，未声称验证其ties实现。
- 主 agent 完整读取 Adam Grimes [Elementary Market Structure](https://www.adamhgrimes.com/market-structure/)，研究 agent 完整读取 [AlgoSwings相关文章](https://www.adamhgrimes.com/current-bull-market-overextended-historical-perspective/)。作者强调局部点常见、识别依赖后柱；后续连接、ATR过滤和高阶点另有定义，本轮不混入。
- Lo/Mamaysky/Wang，[NBER7613](https://www.nber.org/papers/w7613.pdf)：研究 agent 本轮重读PDF14–19（印刷12–17）；主 agent 通过已验SHA的本地原PDF抽取文本重读PDF15–17及结论26–27。原方法对收盘路径做核回归并延后识别与收益观察；也明确直接raw局部极值可能过多。不能据该论文认证本功能raw H/L、radius2或A股净收益。
- Pagan/Sossounov，[2003，DOI10.1002/jae.664](https://onlinelibrary.wiley.com/doi/full/10.1002/jae.664)：研究 agent 取得正文，读§2、§4、§5随机游走/GARCH部分与Table IV、附录A/B。左右八个月初始极值再作交替和周期裁剪属于事后月度定年；带漂移随机游走也能产生相似周期特征，局部结构不能直接等同可预测信号。
- 研究 agent 读取 [TradingView repainting](https://www.tradingview.com/pine-script-docs/concepts/repainting/) 实时值、向过去绘图、历史修订章节。固定本地快照的窗口结果不重写，不代表实时OHLC已闭合或数据历史可得。

## 冻结算法与反方修正

1. radius=N，默认2，快捷2/5/10，整数范围1–20；左右同N。按可定位源标签排序并分组，窗口2N+1组。日/分钟标签间隔不保证相邻交易日或一分钟。
2. 完整且无异常窗口中，中心H严格高于其余H判high，中心L严格低于其余L判low。若存在更高/低值先判not_high/not_low；仅并列窗口最大/小时判tied_not_strict。所有ties不选，同中心两个极值可以并存，不作交替或柱内先后假设。
3. 缺左窗标history_insufficient，缺右窗标pending_right_window，不缩窗；重复标签和坏OHLC保留组与原序号，窗口不给判定，不跳过重拼。无法定位记录单列，并限定来源窗口完整覆盖未知。
4. anchor为中心标签/源序号；confirmation为右侧第N组唯一有效源柱标签/源序号。只证明冻结快照中右窗齐备（right_source_window_present）；闭合及真实当时可知性未知。延迟单位是N个可定位来源标签，不写N个交易日/分钟。
5. selected决定中心行；同快照上下文补足左史。asof取所选最大标签与cutoff较早者，更晚的上下文不能被借入；所选ordinal_end之外的更晚标签不能参与确认。右窗可以含不在所选ordinal集合中的上下文行，记录其身份。
6. 事件身份绑定method、snapshot、radius、中心源序号与kind。固定原件与参数时，已完成窗口结果不受更远未来影响；pending可随窗口推进转为可判断。新原件/修订另有snapshot和事件身份，不冒作旧事件不变。
7. 图标画到确认源柱，列表同时给中心、价格、确认与固定窗口成员；不回画中心制造当时已知的视觉印象。两种事件同柱并列，图标位置不代表成交价或先后。显示受浮点/源柱可绘制性限制的记录仍保留表格精确值。

复用既有OHLC边界验证、精确Decimal字符串和来源账本，不平滑、不替换原价格。价格尺度与复权可比性是假设；日历、覆盖、闭合、known_at、柱内路径未知。未来结构/策略评价从确认后的明确起点开始，并需补齐成本、公司行动、样本选择与样本外证据。

## 验收

手算单/双极值、并列最大/最小与普通非极值区别；坏值/重复组不跳过；左右不齐；缩窗前史；cutoff/ordinal_end不借未来；逐前缀确认事件一致；参数与快照身份；低精度全局context不改判定。三市场.day以UInt32独立窗口比较，真实分钟token以Fraction独立比较。图标映射必须到confirmation序号，遗漏/不可绘制确认柱不挪用其他坐标；旧query/参数响应不能显示。技术验收与预测价值分别记录。

已执行：141项相关后端回归、50项前端用例与TS/Vite构建通过。真实HTTP验证600059.SH的7069根日线、000001.SZ的8465根、920000.BJ的1254根及600059.SH的720根分钟，radius2/5/10全部判定、事件价格和确认位置与独立原件逐项一致。默认2的高/低点数分别899/882、1055/1022、163/157、46/41；这些计数只属于各冻结原件。9/9的9.68高点在9/10截止时仍未确认，在9/11右窗齐备后出现。缩窗上下文与原查询保持一致。12份实际HTTP报告通过前端校验，全部标记映射到确认源序号，真实组件静态输出保留中心/确认标签及精确价格；服务JS字节与构建一致。私有证明位于D盘artifacts/qualification/unit-reconciliation/source-pivots-workbench-check.json与source-pivots-frontend-check.json，未提交行情。静态输出和坐标检查不替代GUI点击、图标视觉布局或下载交互验收，预测价值未验证。
