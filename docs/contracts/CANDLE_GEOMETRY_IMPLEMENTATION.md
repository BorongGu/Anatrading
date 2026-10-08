# 单根源K线结构实现合同 v0.2

2026-10-08。依据[015研究](../research/015-candle-geometry.md)及[014量能门槛](../research/014-relative-volume-and-baselines.md)。待独立反方、修订与根方决定后才编码。成功标准：现有快照的每条记录可查精确实体/影线/收盘位置，并按同Q导出，可用原OHLC独立复算；未来数据不影响旧行，不改变原件或源资格。

## 范围与职责

新增纯后端 `candle_geometry.py`，复用numeric.decimal_value/exact_sum/decimal_text、Store.query及现有HTTP唯一owner。只使用同根OHLC，不使用量额、前收盘、公司行动或后续记录；现有来源assumed/unknown、retrospective与不闭合限定全部继承。无形态命名、长短阈值、主动方向、资金流、预测评分或交易建议。跨日相对量、分钟同槽、多根形态、样本外实验继续原门槛，本功能不解除它们。

解冻候选：新后端/测试，cli.py、workbench.py必要接口，web的types/model/RecordDetails/SourceChart/App/styles和对应现有验证脚本。不改存储Schema、原始query身份、源值/导出、格式白名单、数据生命周期；不加依赖、缓存、数据库或服务。

## 数学与异常

输入只来自已限界Q的序列化源记录，价格接受现有有限DECIMAL(38,18)精确字符串／Decimal／整数；bool/float/非有限值拒绝，保持数值边界。按顺序判断：缺OHLC→missing_ohlc；数值无法接受→invalid_price；负价→negative_price；L≤O,C≤H不成立→invalid_ohlc。任一失败该根not_evaluated、全部派生值null，原行保留。零价符合现有非负价格规则，不能解释为缺失或无成交。量额条件检查失败不阻止独立合法OHLC计算。

合法行：range=H−L，body=|C−O|，upper_shadow=H−max(O,C)，lower_shadow=min(O,C)−L；direction依C/O为up/down/equal。必须精确成立range=body+upper+lower。用既有exact_sum局部128位且Inexact/Rounded陷阱做差，负号用Decimal.copy_negate，绝对值用copy_abs；现有输入最多20位整数+18位尺度，价差/三段加法远低128位，不依赖调用者全局context。禁止float中转、H/L互换、负段裁剪。

range>0：body/upper/lower各除range；close_location=(C−L)/range。权威值为约分有理数，numerator/denominator均整数串，0规范0/1，分母>0，四比例均[0,1]，前三比例精确和1。Fraction由有界Decimal直接构造。range=0合法推出四价相等：长度均0，direction equal，全部比例null，ratio_reason=zero_range；不返回0.5/NaN。

每个比例另含percent_display，固定两位百分数，仅显示；用整数divmod对n×10000/d作half_even舍入，不依赖Decimal context。如1/3→33.33，2/3→66.67；独立验证正半偶/奇舍入。显示百分数之和可能99.99/100.01，不修正分数或百分数来凑整。

## 结果与接口

`geometry_row(row)`每项固定字段ordinal/status/reason/direction/range/body/upper_shadow/lower_shadow/ratios/ratio_reason；ratios固定body/upper_shadow/lower_shadow/close_location，各为null或{numerator,denominator,percent_display}。status为computed/not_evaluated；computed reason=null；not_evaluated direction与长度全部null、ratios全null、ratio_reason=null。

`geometry_report(query)`固定method_id=source-candle-geometry-v1、query_id、geometry_id、qualification=source_observation_description、source_qualification=原manifest资格、assumption=same_price_scale_within_row、display_policy={percent_places:2,rounding:half_even}、rows/unlocated两组结果。每组与源Q同序且同ordinal，全量保留；geometry_id=现有_identity({query_id,method_id})。Q含快照/原件/解释/版本/截止/范围，报告不重建永久证券身份。显示分辨率不足的正常源值仍能精确计算；无法定位行可算几何但不能转为某个时点指标。

前端新增直接的共享envelope validator，不加schema框架：Q/G均为64小写hex，G.query_id严格等Q.query_id，method/qualification/assumption/display_policy及source_qualification与原Q逐项匹配；报告/entry/ratio键集固定无多余字段。定位与unlocated两scope长度分别相等、同序同ordinal；所有源/派生ordinal均正安全整数，全两scope唯一，unlocated.label必须null，定位label非空字符串。Q的selection与当前draft、snapshot及rows/unlocated counts匹配，六源值须字符串或null。

not_evaluated限定reason为上述四种，全部direction/长度/ratio/ratio_reason为空；computed reason为空、direction固定三值、四长度为canonical非负十进制串（整数最多20位、小数最多18位，无多余前导/末尾零）；range=0须四长度0/equal/四ratio=null/zero_range；非零range四ratio必须对象且ratio_reason=null。n/d为canonical非负/正整数字符串、最多38位，0分子只允许0/1；percent_display为不带%的0.00—100.00固定两位字符串。前端不重算价差、GCD、比例或百分数，约分与数值恒等式由后端测试/独立实测证明。精确字段原串保留，不把显示字符串转回真值。

CLI增加 `candle-geometry <snapshot_id>`，接受现有cutoff/ordinal/mode，输出{query,geometry}。HTTP原`/api/query`增geometry，不改query/display/navigation。新固定POST `/api/geometry-export/{snapshot_id}`参数仅原selection+query_id+geometry_id，body必须空；沿用Host/Origin/token和owner。后端重读原件并以有界Q重算，任一ID不符409；返回完整{query,geometry}精确JSON、X-Query-Id/X-Geometry-Id/X-Content-SHA256，不另存导出文件。原JSON/Parquet源值导出保持原payload。无SQL/路径/任意方法入口。

## 工作台

后端为唯一真值；前端只校验/展示，不计算价差、比例或近似百分比。按Q/method/geometry身份、数组长度/ordinal、字段类型与状态校验响应；错映射/缺字段/版本不符清空当前结果，不能留下成功图。固定记录详情显示源价差、实体与上下影线、近似占比和收盘位置；可展开权威分数。标“单根源结构，未检验预测效力”，保留UnitEvidence，不称振幅百分比或对昨收涨跌。

compact十字线不加长几何表，点击后在固定详情读当前Q对应结构；unlocated在其记录详情展示源结构但保留无法定位限定。新增“导出K线结构JSON”，复用原请求代次/迟到拒绝、空响应校验与Blob SHA验证，额外核GeometryId header；改变Q或任何核验失败同时清掉旧结构，导出禁用。没有从图形坐标反算原值、跨日解释或API缺结果时浏览器补算。

结构导出不能只信headers：对已SHA校验Blob解析正文{query,geometry}，键集固定，复用上述共享validator核两scope与当前draft/预期Q；再核正文Q/G恰等导出开始时已确认Q/G和headers。无需display/navigation即可验此envelope。任一失败不触发下载，按当前generation清空；通过后下载原Blob字节，禁止重序列化成另一个文件。原JSON/Parquet导出流程不增加这些派生要求。

## 验收与停止

先写异常、手算、上下文与前缀用例，再实现；包括1/3、2/3、零实体/零range、H/L错、价格缺失/负价/float/nonfinite/精度边界、真实零、局部量额失败独立性、共同正缩放/平移、1e−18高位价差、BigInt字符串、2位half_even两侧、追加未来行与源版本隔离。HTTP验证同Q/导出/双scope/篡改ID/原件失效/20k预算/旧API不变；前端既有竞态与strict response脚本更新，构建通过。

真实验收在现有古越龙山7068条快照，不新增行情请求或清除分钟unknown。私有独立程序从原.day四个UInt32直接以整数价差/有理比复算全分母，逐根对API/CLI全部字段、定位、恒等式和近似舍入；两次读取及不同Q前缀一致，原件/旧源导出字节不变。真实服务保持单owner，测试结束正常关闭。不把合成输入或同一实现自对照当真实独立核算。

界面需实际浏览器可交互核查正常结构、零range/invalid与精度受限行、切换截止/快照/失败清除、导出身份。若当前浏览器能力不可用，明确该门槛未验，API/构建不能代替。源单位、PIT、收益有效性、完整G2/G3及竞品超越继续未完成；通过本切片的有限验收即停止扩写，保留完整目标。
