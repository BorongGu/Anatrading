# 通达信公式桥的数值与时间范围验证

2026-10-09。数据层反方检查完成；以下仅为当前安装、当前样本的数值映射证据。

## 一手定义与实际阅读

- [HTTP调用](https://help.tdx.com.cn/quant/docs/markdown/mindoc-1hdhbmi50d038.html)、[批量公式](https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h4ad5lisvdfg.html)、[公式信息](https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1hce356csmgmo.html)：读取请求及参数说明。批量计算无需设置共享公式上下文；数值输出最多8位小数。
- [函数表](https://help.tdx.com.cn/gspt/docs/markdown/redword/functionlist.html)：VOL为手，AMOUNT/AMO为元，A股历史均价示例为AMO/(VOL*100)。这些定义适用于公式函数；尚未取得当前内置公式输出VOLUME、AMOW的原始公式代码。
- [get_market_data](https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10g60jt68sc.html)说明数量为最小单位、金额万元；[旧示例](https://help.tdx.com.cn/quant/docs/markdown/gzh0122inweixinwenz/gzh20260122wzlz.html)注释却写数量手。语义冲突仍需与当前安装绑定的证据解决。
- [Python struct](https://docs.python.org/3/library/struct.html)格式字符说明：f使用IEEE754 binary32，I使用标准4字节无符号整数。独立检查器用Fraction做24位有效数的近邻半偶舍入，将binary32舍入和桥端8位文本舍入分别处理。

本轮为源数值资格验证，未新增交易指标，也未据软件数值一致性推论策略价值。公司行动与事件研究的论文边界沿用020，不用于解释单位。

## 真实验证结果

固定安装EXE SHA256 `4c822464613fabe4b4235edf171b031d8b209ef68bd7d06dea403e1cd54c1fad`，SDK SHA256 `241358919fd394751a46bb51d64374eb0216f7c22bfa47bc13c48418ba26b1b0`。直接HTTP调用，不初始化SDK，不改共享公式数据，不调用委托。

内置VOL与AMO的公式信息返回isSys=1，输出分别有VOLUME、AMOW。三市场600059.SH、000001.SZ、920000.BJ的18条日线数量、9条日线金额，以及600059的720条分钟向量，符合候选模型：

- 数量：`f32(f32(native_uint)/100)`，再输出8位小数；原整数仍保留。
- 金额：`f32(native_binary32/10000)`，再输出8位小数。
- 本批数值符合正数8位half-up文本舍入；不能从字符串倒称取得原始float bits，也不能外推全部版本的舍入规则。

区分样本排除了“先精确除100、只舍入一次”的另一候选模型：

| 证券与源日期 | 原整数Q | f32(Q/100) | 实际VOLUME，与f32(f32(Q)/100)相同 |
|---|---:|---:|---:|
| 600059.SH，2026-09-15 | 45419678 | 454196.78125 | 454196.8125 |
| 600059.SH，2026-09-11 | 32939495 | 329394.9375 | 329394.96875 |
| 000001.SZ，2026-09-29 | 69097909 | 690979.0625 | 690979.125 |

这些观察支持当前样本的数值模型，不能证明内部实现唯一。单位资格与VWAP资格仍未授予。日线原整数比公式逆乘保留更多源信息，不能用公式值覆盖原字段。

## 时间范围与自动读取

公式请求仅2026-09-28 09:31，count=0、return_count=0、return_date=true，实际仍返回当天240条；Date只有YYYYMMDD，没有分钟时钟。720条对照仅按相同日期向量和源顺序配对，时钟对应是假设。不得把此接口用于分钟截止回放或声称具备逐分钟身份。

15:28本地分钟读取请求600059.SH、240条、截止2026-10-09 15:00，成功保存，但实际源标签仅2026-09-30 09:31～15:00。已提交不等于请求日期覆盖，更不证明完成下载或闭合。

界面应同时展示返回记录的实际范围和请求截止日期。日期缺失需明确提示，保留旧数据供复查；不填补、不悄悄换源。无显式截止日期时只能报告实际范围，不能根据“取最新”称数据已更新至当前交易日。

原始请求、响应、哈希与Fraction独立检查结果保存在D盘私有资格产物中；个人行情原件不提交公开仓库。下一步单位晋级需要与当前内置公式绑定的定义/原始导出；量额同一成交集合的证据另行验证。
