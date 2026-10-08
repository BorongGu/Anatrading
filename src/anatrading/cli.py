"""Synchronous Windows entry point for the first evidence-workbench contract."""
import argparse
import json
from pathlib import Path
import signal
import sys

import duckdb

from .formats import FORMAT_IDS
from .candle_geometry import geometry_report
from .models import DecodeError
from .numeric import NumericError
from .store import EvidenceStore, StoreError


def _port(value):
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("端口须介于1与65535之间")
    return number


def _parser():
    parser = argparse.ArgumentParser(description="Anatrading 本地源值证据工作台")
    parser.add_argument("--root", type=Path, default=Path("data/local"), help="私有数据目录（默认 data/local）")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="启动本机图形工作台")
    serve.add_argument("--port", type=_port, default=8765, help="仅监听127.0.0.1（默认8765）")
    stop = commands.add_parser("stop-workbench", help="请求指定本机工作台正常关闭，等待在途工作完成")
    stop.add_argument("--port", type=_port, default=8765)
    acquire = commands.add_parser("acquire-tdx", help="自动获取已验客户端日线并发布到运行中的工作台")
    acquire.add_argument("--client-directory", type=Path, required=True)
    acquire.add_argument("--symbol", choices=["600059.SH", "000001.SZ"], required=True)
    acquire.add_argument("--target-date", required=True, help="需要实际观察的源日期 YYYY-MM-DD")
    acquire.add_argument("--port", type=_port, default=8765)
    due = commands.add_parser("acquire-tdx-due", help="执行有限日线计划的到期槽或只读恢复")
    due.add_argument("--plan", type=Path, required=True, help="已核验的私有计划绝对路径")
    recovery = commands.add_parser("recover-tdx", help="核证原客户端会话终态并只封结旧刷新，不下载")
    recovery.add_argument("--client-directory", type=Path, required=True)
    minutes = commands.add_parser("read-tdx-minutes", help="读取通达信分钟数据并直接入库，无需手动导出")
    minutes.add_argument("--client-directory", type=Path, default=Path(r"D:\tdx_64"))
    minutes.add_argument("--symbol", required=True, help="证券代码，例如600059.SH")
    minutes.add_argument("--count", type=int, default=720)
    minutes.add_argument("--end-time", default="", help="历史截止YYYYMMDDHHMMSS，留空取最新")
    ingest = commands.add_parser("import", help="保存原件并建立不可变快照")
    ingest.add_argument("source", type=Path)
    ingest.add_argument("--format", choices=FORMAT_IDS, required=True)
    for name in ("instrument", "venue", "asset-type", "volume-unit", "amount-unit"):
        ingest.add_argument("--" + name, help="来源解释声明，保留为 assumed")
    commands.add_parser("snapshots", help="列出已提交快照")
    commands.add_parser("attempts", help="列出导入尝试及结果")
    for name, help_text in (("query", "输出精确源值与质量报告"), ("export", "导出相同查询范围"),
                            ("candle-geometry", "输出单根源K线的精确几何与有理比例")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("snapshot_id")
        command.add_argument("--cutoff", help="含边界的源标签上限：日线 YYYY-MM-DD，分钟 YYYY-MM-DDTHH:MM")
        command.add_argument("--ordinal-start", type=int)
        command.add_argument("--ordinal-end", type=int)
        command.add_argument("--mode", default="retrospective", choices=["retrospective"])
        if name == "export":
            command.add_argument("--format", choices=["json", "parquet"], default="json")
            command.add_argument("--output", type=Path)
    backup = commands.add_parser("backup", help="持锁关闭数据库并校验离线副本")
    backup.add_argument("destination", type=Path)
    restore = commands.add_parser("restore", help="从完整备份恢复到新的空目录")
    restore.add_argument("backup", type=Path)
    restore.add_argument("destination", type=Path)
    return parser


def _run(arguments):
    if arguments.command == "recover-tdx":
        from .tdx_recovery import recover

        return recover(arguments.client_directory)
    if arguments.command == "acquire-tdx-due":
        from .tdx_schedule import due

        return due(arguments.plan)
    if arguments.command == "acquire-tdx":
        from .tdx_acquisition import acquire

        result = acquire(arguments.root, arguments.client_directory, arguments.symbol,
                         arguments.target_date, port=arguments.port)
        return {key: result[key] for key in ("status", "error_code", "evidence_directory", "capture_state",
                "target_observed", "coverage", "units", "raw_sha256", "snapshot_id", "attempt_id",
                "reconciled", "reused", "run_id", "recovery_version", "source_status", "client_task_cancelled") if key in result}
    if arguments.command == "serve":
        from .workbench_lifecycle import serve

        return serve(arguments.root, port=arguments.port)
    if arguments.command == "stop-workbench":
        from .workbench_lifecycle import stop

        return stop(arguments.root, port=arguments.port)
    if arguments.command == "restore":
        return EvidenceStore.restore(arguments.backup, arguments.destination)
    with EvidenceStore(arguments.root) as store:
        if arguments.command == "read-tdx-minutes":
            from .tdx_market import read_minutes

            raw = read_minutes(arguments.client_directory, arguments.symbol,
                               count=arguments.count, end_time=arguments.end_time)
            return store.import_bytes(raw, "tdx-http-market-v1", filename=f"{arguments.symbol}.http.json",
                                      interpretation={"instrument": arguments.symbol, "venue": arguments.symbol[-2:],
                                                      "asset_type": "stock"})
        if arguments.command == "import":
            requested = False

            def request_cancel(signum, frame):
                nonlocal requested
                if not requested:
                    print("已请求取消；提交临界段会完成后返回最终状态。", file=sys.stderr)
                requested = True

            previous = signal.signal(signal.SIGINT, request_cancel)
            try:
                interpretation = {name: getattr(arguments, name) for name in
                                  ("instrument", "venue", "asset_type", "volume_unit", "amount_unit")
                                  if getattr(arguments, name) is not None}
                return store.import_file(arguments.source, arguments.format, interpretation=interpretation,
                                         cancelled=lambda: requested)
            finally:
                signal.signal(signal.SIGINT, previous)
        if arguments.command == "snapshots":
            return store.list_snapshots()
        if arguments.command == "attempts":
            return store.attempts()
        if arguments.command == "backup":
            return store.backup(arguments.destination)
        selection = {name: getattr(arguments, name) for name in ("cutoff", "ordinal_start", "ordinal_end", "mode")}
        if arguments.command == "query":
            return store.query(arguments.snapshot_id, **selection)
        if arguments.command == "candle-geometry":
            query = store.query(arguments.snapshot_id, **selection)
            return dict(query=query, geometry=geometry_report(query))
        exporter = store.export_json if arguments.format == "json" else store.export_parquet
        return exporter(arguments.snapshot_id, arguments.output, **selection)


def main(argv=None):
    from .tdx_acquisition import AcquireError

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    arguments = _parser().parse_args(argv)
    try:
        result = _run(arguments)
    except (StoreError, DecodeError, NumericError, AcquireError) as error:
        result = {"status": "error", "error_code": error.code}
    except OSError:
        result = {"status": "error", "error_code": "storage_io_error"}
    except duckdb.Error:
        result = {"status": "error", "error_code": "database_error"}
    except KeyboardInterrupt:
        # No cancelled outcome is asserted without the import's durable attempt.
        result = {"status": "interrupted", "error_code": "process_interrupted"}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    status = result.get("status") if isinstance(result, dict) else None
    return 130 if status in {"cancelled", "interrupted"} else 2 if status in {
        "error", "failed", "rejected", "not_covered", "refresh_unknown", "publication_unknown", "dispatch_unknown",
        "shutdown_unknown"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
