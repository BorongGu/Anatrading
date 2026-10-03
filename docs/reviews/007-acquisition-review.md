# 007 · 自动取数资格探测复审

日期：2026-10-04。本记录仅覆盖独立资格工具，未批准产品采集器。正文协议保留其审查时字节及SHA；协议首页的待审标签是历史状态，以本记录和对应源码前审的决定为准。

## 初轮协议与实现

`validation_papers`针对[初轮协议](../qualification/AUTOMATIC_ACQUISITION_PROTOCOL.md)提出三个阻断项，主方修订后独立接受，具体反驳、处置及源码依据见[分页前审](../qualification/baostock-pagination-plan.md)。批准稿SHA：`b63a57eb21a3a5ee57c8e7506363cee0b34e60989593f2bac3e1cd454ea87963`。

独立传输、分页及父进程实现完成139项测试和50个子用例。原真实P01失败即停，未执行后续P02/P03。该失败与后续诊断均记录于[实际验证报告](../qualification/baostock-acquisition-results.md)，没有把离线通过写成真实兼容。

## D01实质复核

主方依据原失败提出单帧结构观察；`data_access_research`实现独立诊断，`validation_papers`复核并独立运行57项测试，另以114,688字节不透明合成体核查流式计数／CRC、8192最大recv请求及单次发送。观测仅留12个允许元数据键，无正文累积、无解压、无page文件。

反方要求区分“原失败已发生的分支”和“将原规则应用于本次D01缓冲”；尾形状或数值范围不合适时CRC结果必须为null。主方接受，落入协议与实现。

最终批准唯一D01，协议SHA `dcffeb5b5a18a3dc7aa50989550187074e98ec92848e33d5392c2cadf14bf14e`，代码SHA `0ebeafb3306a0ed14db14c9c99ed4991419172ace9b222cfbb6c6e013ec4efa4`，测试SHA `afd622f940f399f83c73ba417615e76835836e266450207c2f7ef67af257ce48`。主方随后执行一次；最终`diagnostic_incomplete/pages=0/requests=1`，worker退出。原传输和产品内核在本次观测时未改。

## 有界尾区补充协议

D01观察到12字节额外尾区，候选CRC为null。主方提出[补充协议](../qualification/BOUNDED_TRAILER_AMENDMENT.md)，选择按官方SDK切出声明正文、将尾区限制为包含标记最多64字节；不再追加请求猜测校验算法。

`validation_papers`核读具体文档及D01原件后接受，批准稿SHA `a9092de5cca0613dfa77822ad8157526496440b17b78da051d08cd44c1867fa3`。必须证明0／12／51字节前缀边界、52字节拒绝、正文伪尾标、声明短长、尾标拆包、已经接收的尾随字节拒绝、不透明尾区及控制载荷隔离，原wire／decoded／deadline／分页／父进程测试继续通过。

**当前决定：只批准传输最小修正及离线测试。** 新实现仍须独立复审，之后才可另建目录执行一次原P01→P02→P03有界轮次。现阶段没有CRC资格、全市场覆盖或生产更新成功结论。图形工作台另按独立合同审查。
