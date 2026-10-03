const explanations: Record<string, string> = {
  connection_error: '连接中断，请确认本地服务仍在运行。',
  invalid_response: '服务返回格式无法识别。',
  invalid_query_response: '响应与当前选择或显示映射不一致，已清空结果。',
  invalid_ordinal_range: '源序号须为正整数，起点不大于终点，闭区间最多 20,000 条。',
  explicit_window_required: '该批次超过显示预算，请填写两端源序号（最多 20,000 条）。',
  invalid_label_cutoff: '截止标签格式无效，请使用源日期或完整分钟标签。',
  query_id_mismatch: '导出身份与当前查询不一致，请重新查询。',
  raw_object_corrupt: '原件哈希或长度不一致，结果已清空；请恢复正确原件再查询。',
  raw_object_missing: '原件缺失，结果已清空；请恢复正确原件再查询。',
  chart_render_failed: '图层无法绘制，当前结果已清空。可重新查询并核对原字段。',
  upload_too_large: '文件超过本地入口的 16 MiB 预算。',
  upload_in_progress: '已有文件正在接收或导入，请等待其账本终态。',
  upload_incomplete: '文件传输未完整结束，请核对尝试账本。',
  query_row_limit: '当前选择超过 20,000 条预算，请缩小源序号窗口。',
  service_busy: '本地请求队列已满，请稍后重试。',
  service_closing: '本地服务正在关闭，请等待退出后重新启动。',
  snapshot_not_found: '快照不存在，请刷新目录后重新选择。',
  invalid_snapshot_id: '快照身份无效，请刷新目录后重新选择。',
  mode_not_supported: '本切片仅支持历史回顾查询。',
  invalid_import_spec: '导入格式或声明不符合合同，请核对所选格式。',
  invalid_content_type: '上传内容类型无效，请通过原始文件入口导入。',
  invalid_request: '请求参数无效，请重新选择输入。',
  invalid_token: '本地会话已变化，请刷新页面后重试。',
  invalid_host: '访问地址不符合本地服务设置，请使用服务打印的 127.0.0.1 地址。',
  invalid_origin: '请求来源与本地服务地址不一致，请重新打开服务地址。',
  export_integrity_error: '服务端导出完整性校验失败，已阻止交付。',
  import_outcome_unavailable: '尚不能判明导入终态，请检查尝试账本。',
  storage_io_error: '本地文件读写失败，请检查数据目录后重试。',
  database_error: '数据库操作失败，请检查本地服务状态。',
  internal_error: '本地服务遇到内部错误，当前操作未获确认。',
  non_market_payload: '该内容未通过行情预检，已拒绝保存。',
  invalid_text_encoding: '文本编码不在已验范围内。',
  invalid_text_structure: '文本结构与所选格式不符。',
  invalid_text_row_width: '文本记录的字段数量不符。',
  invalid_day_length: '.day 字节长度与已验记录结构不符。',
  unsupported_known_minute_binary: '分钟二进制不在当前导入白名单内。',
  unsupported_bao_period: 'BaoStock 周期不在当前合同范围内。',
  invalid_bao_fields: 'BaoStock 字段与已验合同不符。',
  invalid_bao_records: 'BaoStock 正文记录结构不符。',
  invalid_bao_cells: 'BaoStock 单元格未满足字符串合同。',
  invalid_interpretation: '解释声明的键或值不符合合同。',
  invalid_export_response: '导出文件身份或内容哈希校验失败，已阻止下载。',
  unsupported_format: '请选择本次服务支持的文件格式。',
  file_required: '请先选择原始文件。',
};

export function safeCode(error: unknown): string {
  const code = error instanceof Error ? error.message : '';
  return /^[a-z][a-z0-9_]{0,79}$/.test(code) ? code : 'connection_error';
}
export function explain(error: unknown): string {
  const code = safeCode(error);
  return `${explanations[code] ?? '操作未完成，请根据安全代码核对输入或本地服务。'}（${code}）`;
}

export async function checkedFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const response = await fetch(url, { ...options, cache: 'no-store', credentials: 'same-origin' });
  if (!response.ok) {
    let code = 'invalid_response';
    try {
      const payload = await response.json();
      if (typeof payload.error === 'string' && /^[a-z][a-z0-9_]{0,79}$/.test(payload.error)) code = payload.error;
    } catch { /* Never echo a server body. */ }
    throw new Error(code);
  }
  return response;
}
export async function jsonRequest<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await checkedFetch(url, options);
  try { return await response.json() as T; } catch { throw new Error('invalid_response'); }
}

export async function verifiedExportBlob(response: Response, queryId: string): Promise<{ blob: Blob; digest: string }> {
  if (response.headers.get('X-Query-Id') !== queryId) throw new Error('invalid_export_response');
  const blob = await response.blob();
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()))].map(byte => byte.toString(16).padStart(2, '0')).join('');
  if (response.headers.get('X-Content-SHA256') !== digest) throw new Error('invalid_export_response');
  return { blob, digest };
}
