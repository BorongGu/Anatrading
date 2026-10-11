"""Deterministic synthetic research benchmarks; never a market/alpha test.

Run: .venv/bin/python qualification/research_benchmark.py --sizes 5000 20000 --repeats 3
Writes JSON to stdout and progress to stderr. ASGI timings include source
verification, DB query, analysis and response serialization; no real socket,
network or browser is involved. Preparation and integrity checks are untimed.
"""
import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from anatrading.pair_research import pair_report
from anatrading.signal_research import signal_report
from anatrading.store import EvidenceStore
from anatrading.universe_research import universe_report
from anatrading.workbench import create_app


def source(size, side):
    records = []
    for i in range(size):
        day = date(1990, 1, 1) + timedelta(days=i)
        close = 10000 + i + round(120 * math.sin(i / (13 + side))) + (i * (3 + side)) % 37
        records.append(struct.pack('<IIIIIfII', int(day.strftime('%Y%m%d')),
                                   close, close + 20, close - 20, close, float(close * 100), 10000, 0))
    return b''.join(records)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def summary(durations):
    return dict(median_seconds=statistics.median(durations), runs_seconds=durations)


def timed_stage(function, repeats):
    durations = []
    for _ in range(repeats):
        start = time.perf_counter()
        function()
        durations.append(time.perf_counter() - start)
    return summary(durations)


def store_diagnostics(store, ids, evidence, cutoff, repeats):
    return dict(
        row_budget_count=timed_stage(lambda: [store.query_row_count(sid, cutoff=cutoff) for sid in ids], repeats),
        raw_verification_only=timed_stage(
            lambda: [store._verify_raw(item['raw_sha256'], item['raw_bytes']) for item in evidence], repeats))


def release_formula_inputs(queries, before):
    if digest(queries) != before:
        raise AssertionError('Pure research mutated exact source query inputs')


def timed(function, repeats):
    durations, serialization = [], []
    previous = None
    for _ in range(repeats):
        start = time.perf_counter()
        report = function()
        durations.append(time.perf_counter() - start)
        start = time.perf_counter()
        payload = encoded(report)
        serialization.append(time.perf_counter() - start)
        current = hashlib.sha256(payload).hexdigest()
        if previous is not None and current != previous:
            raise AssertionError('Repeated formula results changed')
        previous, payload_size = current, len(payload)
        # Do not retain an earlier report while timing the next construction.
        del report, payload
    return dict(**summary(durations), json_encode=summary(serialization),
                json_bytes=payload_size, json_sha256=previous, repeated_result_identical=True)


async def timed_request(client, path, params, repeats, expected):
    durations, previous = [], None
    for _ in range(repeats):
        start = time.perf_counter()
        reply = await client.get(path, params=params)
        durations.append(time.perf_counter() - start)
        if reply.status_code != 200:
            raise RuntimeError(f'research request failed: {reply.status_code} {reply.text}')
        current = hashlib.sha256(reply.content).hexdigest()
        if previous is not None and current != previous:
            raise AssertionError('Repeated ASGI responses changed')
        if digest(reply.json()['result']) != expected['json_sha256']:
            raise AssertionError('ASGI result differs from pure formula result')
        previous, response_size = current, len(reply.content)
        del reply
    return dict(**summary(durations), response_bytes=response_size,
                response_sha256=previous, formula_result_identical=True,
                repeated_response_identical=True)


def prepare(store, size, members):
    ids, evidence = [], []
    for side in range(members):
        raw = source(size, side)
        item = store.import_bytes(raw, 'tdx-public-day-v1',
                                  filename='SYNTHETIC-NOT-MARKET.day',
                                  interpretation=dict(instrument=f'{600001 + side:06d}', venue='SH', asset_type='stock'))
        if item['status'] != 'committed' or item['raw_sha256'] != hashlib.sha256(raw).hexdigest():
            raise AssertionError('Synthetic source import/hash failed')
        ids.append(item['snapshot_id'])
        evidence.append(dict(snapshot_id=item['snapshot_id'], raw_sha256=item['raw_sha256'],
                             raw_bytes=len(raw), raw_path=store._raw_path(item['raw_sha256'])))
    return ids, evidence


def timed_load(store, ids, cutoff, repeats, expected_rows):
    durations = []
    for index in range(repeats):
        start = time.perf_counter()
        queries = [store.query(sid, cutoff=cutoff) for sid in ids]
        durations.append(time.perf_counter() - start)
        if sum(len(q['rows']) for q in queries) != expected_rows:
            raise AssertionError('Unexpected source row count')
        if any(q['unlocated'] for q in queries):
            raise AssertionError('Synthetic source unexpectedly has unlocated rows')
        if index < repeats - 1:
            del queries
    return queries, summary(durations)


def check_integrity(queries, before, evidence):
    if digest(queries) != before:
        raise AssertionError('Research mutated exact source query inputs')
    for source_evidence in evidence:
        path = source_evidence.pop('raw_path')
        with path.open('rb') as stream:
            after = hashlib.file_digest(stream, 'sha256').hexdigest()
        if after != source_evidence['raw_sha256'] or path.stat().st_size != source_evidence['raw_bytes']:
            raise AssertionError('Research changed original source bytes')
    return dict(query_sha256_before=before, query_sha256_after=before,
                exact_query_inputs_unchanged=True, raw_objects_unchanged=True,
                synthetic_sources=evidence)


async def benchmark(size, repeats, lookbacks):
    print(f'Benchmarking single/pair: {size} rows, windows {lookbacks}', file=sys.stderr, flush=True)
    with tempfile.TemporaryDirectory(prefix='anatrading-synthetic-benchmark-') as tmp:
        cutoff = (date(1990, 1, 1) + timedelta(days=size - 1)).isoformat()
        with EvidenceStore(tmp) as store:
            ids, evidence = prepare(store, size, 2)
            diagnostics = store_diagnostics(store, ids, evidence, cutoff, repeats)
            queries, loading = timed_load(store, ids, cutoff, repeats, size * 2)
        before = digest(queries)
        output = dict(rows_per_series=size, members=2, cutoff=cutoff,
                      store_load_two_series=loading, store_diagnostics=diagnostics, windows=[])
        for lookback in lookbacks:
            output['windows'].append(dict(
                lookback=lookback,
                single=timed(lambda: signal_report(queries[0], lookback=lookback), repeats),
                pair=timed(lambda: pair_report(*queries, lookback=lookback), repeats)))
        release_formula_inputs(queries, before)
        del queries
        gc.collect()  # The direct-call fixtures must not inflate ASGI live memory.
        app = create_app(tmp)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8765') as client:
                for row in output['windows']:
                    lookback = row['lookback']
                    row['asgi_single'] = await timed_request(client, '/api/research/single/' + ids[0],
                                                             dict(cutoff=cutoff, lookback=lookback), repeats, row['single'])
                    row['asgi_pair'] = await timed_request(client, '/api/research/pair',
                                                           dict(left=ids[0], right=ids[1], cutoff=cutoff, lookback=lookback),
                                                           repeats, row['pair'])
                    print(f'  W={lookback}: single ASGI {row["asgi_single"]["median_seconds"]:.3f}s; '
                          f'pair ASGI {row["asgi_pair"]["median_seconds"]:.3f}s', file=sys.stderr, flush=True)
        with EvidenceStore(tmp) as store:
            queries = [store.query(sid, cutoff=cutoff) for sid in ids]
        output['integrity'] = check_integrity(queries, before, evidence)
        return output


async def benchmark_universe(members, size, repeats):
    print(f'Benchmarking universe: {members} x {size} rows, W=252', file=sys.stderr, flush=True)
    with tempfile.TemporaryDirectory(prefix='anatrading-synthetic-universe-benchmark-') as tmp:
        cutoff = (date(1990, 1, 1) + timedelta(days=size - 1)).isoformat()
        with EvidenceStore(tmp) as store:
            ids, evidence = prepare(store, size, members)
            diagnostics = store_diagnostics(store, ids, evidence, cutoff, repeats)
            queries, loading = timed_load(store, ids, cutoff, repeats, size * members)
        before = digest(queries)
        output = dict(members=members, rows_per_series=size, total_source_rows=size * members,
                      lookback=252, cutoff=cutoff, store_load=loading, store_diagnostics=diagnostics,
                      universe=timed(lambda: universe_report(queries, cutoff, lookback=252), repeats))
        release_formula_inputs(queries, before)
        del queries
        gc.collect()
        print(f'  Load {loading["median_seconds"]:.3f}s; formula {output["universe"]["median_seconds"]:.3f}s',
              file=sys.stderr, flush=True)
        app = create_app(tmp)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8765') as client:
                output['asgi_universe'] = await timed_request(client, '/api/research/universe',
                                                             dict(snapshot_ids=','.join(ids), cutoff=cutoff, lookback=252),
                                                             repeats, output['universe'])
        with EvidenceStore(tmp) as store:
            queries = [store.query(sid, cutoff=cutoff) for sid in ids]
        output['integrity'] = check_integrity(queries, before, evidence)
        print(f'  Universe ASGI {output["asgi_universe"]["median_seconds"]:.3f}s', file=sys.stderr, flush=True)
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[5000, 20000])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--lookbacks', type=int, nargs='+', default=[20, 252])
    parser.add_argument('--skip-universe', action='store_true', help='For a quick single/pair harness smoke test only')
    args = parser.parse_args()
    if any(not 25 <= n <= 20000 for n in args.sizes) or not 1 <= args.repeats <= 10:
        parser.error('sizes must be 25..20000; repeats 1..10')
    if any(not 5 <= n <= 252 for n in args.lookbacks):
        parser.error('lookbacks must be 5..252')
    tracked_sources = [ROOT / 'qualification/research_benchmark.py', *sorted((ROOT / 'src/anatrading').glob('*.py'))]
    hashes_before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked_sources}
    output = dict(kind='synthetic_performance_only', started_at=datetime.now(timezone.utc).isoformat(),
                  python=platform.python_version(), platform=platform.platform(), processor=platform.machine(),
                  logical_cpus=os.cpu_count(), affinity_cpus=len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
                  versions={name: importlib.metadata.version(name) for name in ('duckdb', 'pyarrow', 'fastapi', 'starlette', 'httpx')},
                  base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  repeats=args.repeats, warmup='first run included; individual timings retained; prepared DB and OS caches may be warm',
                  memory_scope='Direct-call input fixtures are checked, released and garbage-collected before ASGI; final integrity reload is untimed',
                  timing_scope=dict(formula='formula only; JSON encoding reported separately',
                                    store_load='raw verification plus complete cutoff-prefix query; excludes import and budget count',
                                    asgi='budget count, raw verification, query, formula and JSON response; excludes socket/network/browser'),
                  results=[asyncio.run(benchmark(n, args.repeats, args.lookbacks)) for n in args.sizes],
                  universe_results=[] if args.skip_universe else [asyncio.run(benchmark_universe(m, n, args.repeats))
                                                                  for m, n in ((10, 20000), (50, 4000))])
    hashes_after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked_sources}
    output.update(finished_at=datetime.now(timezone.utc).isoformat(), source_sha256=hashes_after,
                  benchmarked_code_unchanged=hashes_before == hashes_after)
    if hashes_before != hashes_after:
        raise RuntimeError('Benchmarked code changed during run; rerun against final files')
    print(json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == '__main__':
    main()
