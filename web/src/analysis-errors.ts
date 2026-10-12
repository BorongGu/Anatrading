import { explain, safeCode } from './api.ts';

type AnalysisContext = 'current_version' | 'paired_daily_background' | 'minute_selection_and_daily';

const rowLimitGuidance: Record<AnalysisContext, string> = {
  current_version: '此分析需要显示窗口外的上下文；服务按当前完整数据版本总条数执行 20,000 条上限。缩小显示源序号窗口或提前截止均不能降低完整版本总条数，请改选不超过上限的较小来源数据版本。',
  paired_daily_background: '日线背景需要用于对照的日线数据版本上下文；服务按该完整日线版本总条数执行 20,000 条上限。缩小分钟显示窗口、背景历史窗口或提前分钟锚点均不能降低完整日线版本总条数，请改选不超过上限的较小日线数据版本。',
  minute_selection_and_daily: '此对账的分钟选择与用于对照的完整日线数据版本各有 20,000 条上限。若分钟选择超限，请缩小源序号窗口并重新查询；若完整日线版本总条数超限，缩小分钟窗口无效，请改选不超过上限的较小日线数据版本。',
};

export function explainAnalysisError(error: unknown, context: AnalysisContext): string {
  return safeCode(error) === 'query_row_limit'
    ? `${rowLimitGuidance[context]}（query_row_limit）`
    : explain(error);
}
