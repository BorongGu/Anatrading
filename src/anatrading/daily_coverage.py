"""Inspect explicitly selected native collection runs and their stored source dates."""
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import struct

from .tdx_acquisition import AcquireError, _inside


def _run(root, run_id):
    if not isinstance(run_id, str) or not re.fullmatch('[0-9a-f]{32}', run_id):
        raise AcquireError('invalid_daily_cache_runs')
    directory = _inside(Path(root)/'acquisition'/'daily-cache'/run_id, Path(root))
    try:
        progress = json.loads((directory/'progress.json').read_text(encoding='utf-8'))
        if (not isinstance(progress, dict) or not isinstance(progress.get('status'), str)
                or type(progress.get('processed')) is not int or progress['processed'] < 0
                or not isinstance(progress.get('pool_sha256'), str)
                or not re.fullmatch('[0-9a-f]{64}', progress['pool_sha256'])):
            raise ValueError()
        return directory, progress
    except (OSError, ValueError):
        raise AcquireError('invalid_daily_cache_runs') from None


def collection_runs(root):
    root = Path(root).resolve()
    directory = root/'acquisition'/'daily-cache'
    if not directory.exists():
        return []
    result = []
    for entry in sorted(directory.iterdir()):
        if not re.fullmatch('[0-9a-f]{32}', entry.name):
            continue
        _, progress = _run(root, entry.name)
        result.append(dict(run_id=entry.name, status=progress['status'],
                           processed=progress['processed'], pool_sha256=progress['pool_sha256']))
    return result


def _dates(raw):
    values = []
    for (value,) in struct.iter_unpack('<I28x', raw):
        try:
            values.append(date(value//10000, value//100 % 100, value % 100).isoformat())
        except ValueError:
            values.append(None)
    known = [value for value in values if value is not None]
    return dict(first_record_date=values[0], last_record_date=values[-1],
                earliest_source_date=min(known, default=None), latest_source_date=max(known, default=None),
                invalid_date_rows=len(values)-len(known), duplicate_date_rows=len(known)-len(set(known)),
                descending_steps=sum(a > b for a, b in zip(values, values[1:]) if a is not None and b is not None))


def coverage_report(root, snapshots, run_ids):
    root = Path(root).resolve()
    if not run_ids or len(run_ids) != len(set(run_ids)) or len(run_ids) > 100:
        raise AcquireError('invalid_daily_cache_runs')
    pool, pool_sha, outcomes = None, None, {}
    for run_id in run_ids:
        directory, progress = _run(root, run_id)
        try:
            if progress['status'] not in {'completed', 'failed', 'interrupted'}:
                raise ValueError()
            capture = json.loads((directory/'catalog.json').read_text(encoding='utf-8'))['response_utf8']
            sha = hashlib.sha256(capture.encode('utf-8')).hexdigest()
            response = json.loads(capture)
            symbols = response['result']['Value']
            start = progress.get('skipped_prefix', 0)
            entries = [json.loads(line) for line in (directory/'outcomes.jsonl').read_text(encoding='utf-8').splitlines()]
            if (response.get('id') != 1 or response['result'].get('ErrorId') != '0'
                    or not isinstance(symbols, list) or not symbols or len(symbols) != len(set(symbols))
                    or any(not isinstance(s, str) or not re.fullmatch(r'[0-9]{6}\.(SH|SZ|BJ)', s) for s in symbols)
                    or sha != progress['pool_sha256'] or (pool_sha is not None and sha != pool_sha)
                    or type(start) is not int or not 0 <= start <= len(symbols)
                    or len(entries) != progress['processed']
                    or [item['symbol'] for item in entries] != symbols[start:start+len(entries)]):
                raise ValueError()
            for item in entries:
                if item['symbol'] in outcomes or item['status'] not in {'committed', 'missing', 'failed', 'rejected', 'publication_unknown'}:
                    raise ValueError()
                outcomes[item['symbol']] = item
            pool, pool_sha = symbols, sha
        except (OSError, ValueError, KeyError, TypeError):
            raise AcquireError('invalid_daily_cache_runs') from None
    catalog = {snapshot['snapshot_id']: snapshot for snapshot in snapshots}
    counts = dict(pool=len(pool), processed=len(outcomes), committed=0, missing=0, failed=0,
                  unprocessed=len(pool)-len(outcomes), source_rows=0)
    rows, latest = [], Counter()
    for symbol in pool:
        item = outcomes.get(symbol, dict(status='unprocessed'))
        row = dict(symbol=symbol, status=item['status'], snapshot_id=None, raw_sha256=None,
                   source_rows=0, latest_source_date=None, earliest_source_date=None,
                   first_record_date=None, last_record_date=None,
                   invalid_date_rows=0, duplicate_date_rows=0, descending_steps=0)
        if item['status'] == 'committed':
            try:
                snapshot, sha = catalog[item['snapshot_id']], item['raw_sha256']
                if not re.fullmatch('[0-9a-f]{64}', sha):
                    raise ValueError()
                raw = _inside(Path(root)/'raw'/sha[:2]/sha, Path(root)).read_bytes()
                if (not raw or len(raw) % 32 or hashlib.sha256(raw).hexdigest() != sha
                        or len(raw)//32 != snapshot['row_count']
                        or snapshot['metadata']['period'] != '1d'
                        or snapshot['manifest']['contract']['format_id'] != 'tdx-public-day-v1'
                        or snapshot['manifest']['raw_sha256'] != sha
                        or snapshot['manifest']['interpretation'].get('instrument') != symbol
                        or snapshot['manifest']['interpretation'].get('venue') != symbol[-2:]):
                    raise ValueError()
            except (OSError, KeyError, ValueError, TypeError):
                raise AcquireError('daily_cache_evidence_mismatch') from None
            row.update(snapshot_id=item['snapshot_id'], raw_sha256=sha, source_rows=len(raw)//32, **_dates(raw))
            counts['committed'] += 1
            counts['source_rows'] += row['source_rows']
            latest[row['latest_source_date'] or 'unreadable'] += 1
        elif item['status'] != 'unprocessed':
            counts['missing' if item['status'] == 'missing' else 'failed'] += 1
        rows.append(row)
    return dict(method_id='native-daily-cache-coverage-v1', run_ids=sorted(run_ids), pool_sha256=pool_sha,
                scope='current_source_market_5_not_historical_universe', counts=counts,
                latest_source_date_counts=dict(sorted(latest.items())), rows=rows)
