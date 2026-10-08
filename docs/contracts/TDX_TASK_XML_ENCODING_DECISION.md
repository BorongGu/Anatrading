# 任务XML编码窄修决定

2026-10-08。U5实际本地Task Scheduler COM登记发现(1,40)“无法切换编码”。传入的是Python/PowerShell Unicode文本→COM BSTR，已有 `task_xml()`却给Unicode序列化文本声明UTF-8。私有相同动作XML去掉声明后确实登记成功；注册后的Windows XML文本声明UTF-16。早先仅ElementTree结构检查没有覆盖本机COM登记边界。

根方采纳独立U5反方在032后续消息中的窄修批准：仅 `task_xml()` 返回Unicode文本时去掉编码声明，保留全部字段、时间、动作和权限；现有XML测试增加无声明及中文路径完整断言。先做红测再修单行。U5产品冻结对此具体修复解冻，原helper/source manifest保持历史哈希，不重封已完成任务的输入，不增加注册或行情权限。

随后以实际Windows NewTask.XmlText只解析原产品模板与修订模板，记录旧声明失败/新文本成功，不创建生产任务。定时入口相关回归与独立窄修复审通过后结束本资格切片。真实生产CLI动作、行情更新和PT3M终止资格仍待验证。
