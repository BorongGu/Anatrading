# 071 同层研究组件 key 修正

2026-10-14，编码前边界：070实际App合成验收发现重复key；只修正App六处组件角色命名空间，保留query_id原语义与所有请求代次、条件渲染和卸载行为。

首次日线加载SourceChart/SingleResearch同层共用query_id；详细指标日线GapAnalysis/PivotAnalysis/SourceActions及分钟GapAnalysis/PivotAnalysis/MinuteAggregation也同层重复。query_id是查询内容身份；相同查询重复执行保持相同ID。无需新增运行ID、随机值或更改后端哈希。

验收先保留旧版警告，实际React App/SourceChart组件仅图形API适配后，检查首次/重复加载、详细指标切换、源选择、研究重跑、卸载和迟到响应。零重复key警告、各面板单实例、来源/结果归属及既有重置语义不变；分钟同层也覆盖。独立复审后再发布。未观察到既有错行或旧结果污染，不据警告夸大用户影响。

## 本次本地验证

- 旧版实际React DOM：日线、分钟两个用例均因重复key断言失败，保留红例；静态六角色断言也先失败。
- 修正后全Node **955/955通过，0失败/跳过**；TypeScript与Vite构建通过。既有npm http-proxy与主包大于500 kB提示保留。
- 仓库内可复跑实际App DOM **2/2通过**，全console.error断言为空；实际SourceChart保留，其lightweight-charts图形API用测试适配器代替。日线/分钟首次加载、源选择、展开/收起详细指标、相同查询重载、日线重复研究、旧请求卸载后迟到成功均通过；完整合成DTO未改。
- 070既有实际研究/实际App受影响DOM **42/42通过，0失败/跳过**，本次App测试也保留实际SourceChart，仅替换图形API。分页与选择重置保持原语义。
- 查询fixture来自070未修改内核生成的21槽/1事件合成响应，query_id按现有canonical selection SHA256计算；其余来源元数据为合成测试壳。分钟用例只验证组件接线，不能当作真实分钟来源资格。图形API回调调用不等于浏览器鼠标命中。

复跑：在web目录执行 `node --test tests/*.test.mjs`、`npm run build`；DOM使用已安装jsdom，执行 `ANATRADING_JSDOM_PATH=/absolute/path/to/jsdom/lib/api.js node --test tests/component-query-keys-dom.mjs`。jsdom依赖仍为可选外部工具，未加依赖或把未安装算通过。

后端无改动，未跑完整Python；真实浏览器/canvas、实际键盘默认激活、Windows、真实来源、HTTP/Store与性能均未验。未取得新的预测或金融效果证据。本记录为实现者验证，独立审核与发布尚待完成。
