# 063 合成复现与执行历史

本目录只含原创合成脚本、人工数值和研究记录，无真实行情、上游代码快照或运行凭据。两个原协议逐字保留；独立审计协议公开副本删除了执行器私有路径并注明该编辑。

## 复现

从仓库根运行（仅Python标准库及Node内置BigInt，无依赖安装）：

```sh
python docs/research/artifacts/063-close-dispersion/experiment.py
python docs/research/artifacts/063-close-dispersion/source_experiment.py
node docs/research/artifacts/063-close-dispersion/audit.mjs
```

前两条分别覆写本目录`results.json`、`source-results.json`并输出同内容；第三条输出JSONL，可与`original-results.jsonl`和`reviewer-rerun.jsonl`比对。脚本是研究复现，非产品导入、资格或回归测试；浮点输出的误差界及失败数组在`results.json`中，执行退出0本身不能取代结果检查。

## 运行账本

- 主研究：先冻结`protocol.md`，原binary64实验运行1次；再冻结`addendum-protocol.md`，精确源补充运行1次。没有改原门槛或把转换失败归入原浮点参考通过。
- 独立审计：原JS基础/源碰撞执行1次，另行预先文字冻结的边界扩展执行1次；原运行使用JavaScript环境，输出后来转录到`original-results.jsonl`。保存的`audit.mjs`将两次代码合并，仅适配输出、重命名夹具变量及中性化注释；保存时间不证明原文件预冻结。
- 发布复现（2026-10-13，Python3.12.14、Node24.19.0）：上述三个脚本各运行1次；两个Python输出与原输出逐字节一致，合并JS输出与转录原结果逐字节一致，保存为`reviewer-rerun.jsonl`。共2次主浮点、2次主源补充；独立原2次加合并复现1次，不能相加为独立样本数。
- 原两份协议SHA256分别为`5dcdb7d5e2daa6ca9be449478672e96b0e8ce9c25c9f221fcbef4e5bb572f57c`、`227bb47858b3f1af47ac2dd97877a936a396ace22ab36baeffd38877c0bea534`。
- 发布前独立汇总原JSON发现初稿将朴素浮点失败窗误写为246，实际为205；已纠正文稿，原结果及门槛未改。
- 原边界审计冻结位数限为264；推导可收紧到262，未改历史脚本或验收结果。缺失位置测试只验索引，格点资格只验界限；Decimal解析、真实来源和产品集成均未跑。

本目录没有计时、RSS或市场样本，不能用于性能、经济效果或完整TradingView兼容宣传。
