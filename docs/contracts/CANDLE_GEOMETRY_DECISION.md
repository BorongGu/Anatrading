# 单根K线结构开工决定

2026-10-08。根方核读[015研究](../research/015-candle-geometry.md)、[014相对量门槛](../research/014-relative-volume-and-baselines.md)，采纳[合同v0.2](CANDLE_GEOMETRY_IMPLEMENTATION.md)，SHA `87b1b3dd0570119afa0e49aa29c54857a072ce7eaf62ddbac59912dafe090658`，及[034最终反方](../reviews/034-candle-geometry-contract-review.md)。两项P1在合同层关闭。

只解冻新candle_geometry.py、workbench.py/cli.py必要接口、web的types/model/RecordDetails/SourceChart/App/styles及**api.ts必要导出校验薄层**、对应测试/已有前端测试脚本和资格文档。api.ts可以新增调用共享envelope validator的派生Blob核验helper；保留原verifiedExportBlob/源JSON-Parquet语义。先异常用例再实现，源真值仅由后端计算。

不改Schema/格式/标准单位/数据写者、不取新行情、不清原分钟未知；股份事件与可比性不足的跨日量能继续门控。实现后独立代码/真实全分母与浏览器验收分别记录，未验不计通过，完整目标active。
