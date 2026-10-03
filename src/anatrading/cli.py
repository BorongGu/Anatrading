"""Synchronous Windows entry point for the first evidence-workbench contract."""
import argparse
import json
from pathlib import Path
import signal
import sys

import duckdb

from .formats import FORMAT_IDS
from .models import DecodeError
from .numeric import NumericError
from .store import EvidenceStore, StoreError


def _parser():
    parser = argparse.ArgumentParser(description="Anatrading 本地源值证据工作台")
    parser.add_argument("--root", type=Path, default=Path("data/local"), help="私有数据目录（默认 data/local）")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("import", help="保存原件并建立不可变快照")
    ingest.add_argument("source", type=Path)
    ingest.add_argument("--format", choices=FORMAT_IDS, required=True)
    for name in ("instrument", "venue", "asset-type", "volume-unit", "amount-unit"):
        ingest.add_argument("--" + name, help="来源解释声明，保留为 assumed")
    commands.add_parser("snapshots", help="列出已提交快照")
    commands.add_parser("attempts", help="列出导入尝试及结果")
    for name, help_text in (("query", "输出精确源值与质量报告"), ("export", "导出相同查询范围")):
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
    if arguments.command == "restore":
        return EvidenceStore.restore(arguments.backup, arguments.destination)
    with EvidenceStore(arguments.root) as store:
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
        exporter = store.export_json if arguments.format == "json" else store.export_parquet
        return exporter(arguments.snapshot_id, arguments.output, **selection)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    arguments = _parser().parse_args(argv)
    try:
        result = _run(arguments)
    except (StoreError, DecodeError, NumericError) as error:
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
    return 130 if status in {"cancelled", "interrupted"} else 2 if status in {"error", "failed", "rejected"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
