"""Deterministic synthetic research benchmarks; never a market/alpha test.

Run: .venv/bin/python qualification/research_benchmark.py --sizes 5000 20000 --repeats 3
For a compact-read comparison add --baseline PATH/TO/FROZEN_BASELINE.json and
write stdout to a new file. The frozen baseline is read-only and hash-checked.
Writes JSON to stdout and progress to stderr. ASGI timings include source
verification, DB query, analysis and response serialization; no real socket,
network or browser is involved. Preparation and integrity checks are untimed.
"""
import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
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
from anatrading.research_api import _calculate
from anatrading.store import EvidenceStore, _json
from anatrading.universe_research import universe_report
from anatrading.workbench import create_app


def source(size, side, anomaly_dense=False):
    records = []
    for i in range(size):
        day = date(1990, 1, 1) + timedelta(days=i)
        close = 10000 + i + round(120 * math.sin(i / (13 + side))) + (i * (3 + side)) % 37
        raw_day, high = int(day.strftime('%Y%m%d')), close + 20
        if anomaly_dense:
            if i % 10 == 3:
                high = close - 1  # Invalid OHLC; preserve the entire source row.
            elif i % 10 == 4:
                raw_day = int((day - timedelta(days=1)).strftime('%Y%m%d'))
            elif i % 10 == 6:
                raw_day = 19901301  # Unreadable date retained as an unlocated row.
        records.append(struct.pack('<IIIIIfII', raw_day,
                                   close, high, close - 20, close, float(close * 100), 10000, 0))
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


async def timed_request(client, path, params, repeats, expected, expected_envelope=None):
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
        body = reply.json()
        if expected_envelope is not None and current != expected_envelope['response_sha256']:
            raise AssertionError('ASGI envelope/IDs differ from full-query reference')
        identity = {key: body[key] for key in ('analysis_id', 'method_id', 'inputs')}
        if digest(body['result']) != expected['json_sha256']:
            raise AssertionError('ASGI result differs from pure formula result')
        previous, response_size = current, len(reply.content)
        del reply, body
    return dict(**summary(durations), response_bytes=response_size,
                response_sha256=previous, formula_result_identical=True,
                repeated_response_identical=True, identity=identity,
                full_query_envelope_identical=expected_envelope is not None)


def prepare(store, size, members, anomaly_dense=False):
    ids, evidence = [], []
    for side in range(members):
        raw = source(size, side, anomaly_dense=anomaly_dense)
        item = store.import_bytes(raw, 'tdx-public-day-v1',
                                  filename='SYNTHETIC-NOT-MARKET.day',
                                  interpretation=dict(instrument=f'{600001 + side:06d}', venue='SH', asset_type='stock'))
        if item['status'] != 'committed' or item['raw_sha256'] != hashlib.sha256(raw).hexdigest():
            raise AssertionError('Synthetic source import/hash failed')
        ids.append(item['snapshot_id'])
        evidence.append(dict(snapshot_id=item['snapshot_id'], raw_sha256=item['raw_sha256'],
                             raw_bytes=len(raw), raw_path=store._raw_path(item['raw_sha256'])))
    return ids, evidence


def timed_load(store, ids, cutoff, repeats, expected_rows, method='query', allow_unlocated=False):
    durations = []
    for index in range(repeats):
        if method == '_research_query':
            counts = [store.query_row_count(sid, cutoff=cutoff) for sid in ids]
            if any(n > 20000 for n in counts) or sum(counts) > 200000:
                raise AssertionError('Private read called without budget admission')
        reader = getattr(store, method)
        start = time.perf_counter()
        queries = [reader(sid, cutoff=cutoff) for sid in ids]
        durations.append(time.perf_counter() - start)
        if sum(len(q['rows']) + len(q['unlocated']) for q in queries) != expected_rows:
            raise AssertionError('Unexpected source row count')
        if not allow_unlocated and any(q['unlocated'] for q in queries):
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



def compact_digest(value):
    # The Store's exact Decimal serializer is deliberate; never cast to float.
    return hashlib.sha256(_json(value).encode()).hexdigest()


def projection_reference(full):
    result = {key: full[key] for key in ('snapshot_id', 'batch_id', 'selection', 'query_id',
                                        'manifest', 'metadata', 'counts', 'batch_checks')}
    result['read_projection'] = 'daily_ohlc_input_v1'
    for scope in ('rows', 'unlocated'):
        result[scope] = []
        for row in full[scope]:
            item = {key: row[key] for key in ('ordinal', 'label', 'tokens', 'checks')}
            item['values'] = {key: None if row['values'][key] is None else Decimal(row['values'][key])
                              for key in ('open', 'high', 'low', 'close')}
            result[scope].append(item)
    return result


def projection_fingerprints(queries, from_full=False):
    return [compact_digest(projection_reference(q) if from_full else q) for q in queries]


def check_projection(queries, expected_hashes, expected_ids):
    if projection_fingerprints(queries) != expected_hashes:
        raise AssertionError('Private projection differs from independent full-query reference')
    if [q['query_id'] for q in queries] != expected_ids:
        raise AssertionError('Private projection changed source query IDs')
    for query in queries:
        for row in query['rows'] + query['unlocated']:
            if any(value is not None and type(value) is not Decimal for value in row['values'].values()):
                raise AssertionError('Private OHLC must remain Decimal, never float or text')


def reference_envelope(kind, queries, cutoff, lookback):
    params = dict(cutoff=cutoff, lookback=lookback)
    selected = queries
    if kind == 'single':
        params.update(horizon=5, test_start=None)
        selected = queries[:1]
    elif kind == 'universe':
        selected = sorted(queries, key=lambda q: q['snapshot_id'])
    report = _calculate(kind, selected, params, ValueError)
    return dict(response_sha256=digest(report), response_bytes=len(encoded(report)),
                identity={key: report[key] for key in ('analysis_id', 'method_id', 'inputs')})


def formula_matrix(queries, cutoff, lookbacks, repeats, universe_only=False, include_universe=False):
    result = []
    for lookback in lookbacks:
        row = dict(lookback=lookback)
        if not universe_only:
            row['single'] = timed(lambda: signal_report(queries[0], lookback=lookback), repeats)
            row['pair'] = timed(lambda: pair_report(*queries[:2], lookback=lookback), repeats)
        if universe_only or include_universe:
            row['universe'] = timed(lambda: universe_report(queries, cutoff, lookback=lookback), repeats)
        result.append(row)
    return result


async def benchmark_compact(size, members, repeats, lookbacks, baseline_case=None,
                            universe_only=False, anomaly_dense=False):
    label = f'{members} x {size}, W={lookbacks}' + (' anomaly-dense' if anomaly_dense else '')
    print('Benchmarking compact/full equivalence: ' + label, file=sys.stderr, flush=True)
    with tempfile.TemporaryDirectory(prefix='anatrading-synthetic-compact-') as tmp:
        cutoff = (date(1990, 1, 1) + timedelta(days=size - 1)).isoformat()
        with EvidenceStore(tmp) as store:
            ids, evidence = prepare(store, size, members, anomaly_dense=anomaly_dense)
            diagnostics = store_diagnostics(store, ids, evidence, cutoff, repeats)
            queries, full_loading = timed_load(store, ids, cutoff, repeats, size * members,
                                               allow_unlocated=anomaly_dense)
        full_before = digest(queries)
        query_ids = [q['query_id'] for q in queries]
        projected_hashes = projection_fingerprints(queries, from_full=True)
        counts = [q['counts'] for q in queries]
        full_windows = formula_matrix(queries, cutoff, lookbacks, repeats, universe_only, anomaly_dense)
        references = []
        for row in full_windows:
            references.append({kind: reference_envelope(kind, queries, cutoff, row['lookback'])
                               for kind in ('single', 'pair', 'universe') if kind in row})
        release_formula_inputs(queries, full_before)
        del queries
        gc.collect()
        with EvidenceStore(tmp) as store:
            queries, compact_loading = timed_load(store, ids, cutoff, repeats, size * members,
                                                  method='_research_query', allow_unlocated=anomaly_dense)
        check_projection(queries, projected_hashes, query_ids)
        compact_before = compact_digest(queries)
        windows = formula_matrix(queries, cutoff, lookbacks, repeats, universe_only, anomaly_dense)
        for compact_row, full_row in zip(windows, full_windows):
            for kind in ('single', 'pair', 'universe'):
                if kind in compact_row and compact_row[kind]['json_sha256'] != full_row[kind]['json_sha256']:
                    raise AssertionError('Compact-input formula changed numeric or report results')
        compact_after = compact_digest(queries)
        if compact_before != compact_after:
            raise AssertionError('Formula mutated compact exact inputs')
        del queries
        gc.collect()
        print(f'  Full read {full_loading["median_seconds"]:.3f}s; compact {compact_loading["median_seconds"]:.3f}s',
              file=sys.stderr, flush=True)
        app = create_app(tmp)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8765') as client:
                for row, golden in zip(windows, references):
                    lookback = row['lookback']
                    routes = dict(single=('/api/research/single/' + ids[0], dict(cutoff=cutoff, lookback=lookback)),
                                  pair=('/api/research/pair', dict(left=ids[0], right=ids[1], cutoff=cutoff, lookback=lookback)),
                                  universe=('/api/research/universe', dict(snapshot_ids=','.join(ids), cutoff=cutoff, lookback=lookback)))
                    for kind in golden:
                        path, params = routes[kind]
                        row['asgi_' + kind] = await timed_request(client, path, params, repeats, row[kind], golden[kind])
                        print(f'  {kind} W{lookback} ASGI {row["asgi_" + kind]["median_seconds"]:.3f}s', file=sys.stderr, flush=True)
        with EvidenceStore(tmp) as store:
            queries = [store.query(sid, cutoff=cutoff) for sid in ids]
        integrity = check_integrity(queries, full_before, evidence)
        output = dict(rows_per_series=size, members=members, total_source_rows=size * members,
                      cutoff=cutoff, lookbacks=lookbacks, anomaly_dense=anomaly_dense,
                      source_counts=counts, store_diagnostics=diagnostics,
                      store_load_full=full_loading, store_load_compact=compact_loading,
                      full_input_windows=full_windows, windows=windows,
                      full_query_response_references=references, integrity=integrity,
                      projection_equivalence=dict(independent_projection_sha256=projected_hashes,
                                                  exact_projection_equal=True, full_and_compact_query_ids=query_ids,
                                                  compact_input_sha256_before=compact_before,
                                                  compact_input_sha256_after=compact_after,
                                                  source_values_type='Decimal', full_query_fingerprint_retained=True))
        if baseline_case is not None:
            if full_before != baseline_case['integrity']['query_sha256_before']:
                raise AssertionError('Public full query differs from frozen baseline')
            old_windows = baseline_case.get('windows') or [dict(lookback=252, universe=baseline_case['universe'],
                                                                 asgi_universe=baseline_case['asgi_universe'])]
            old_by_window = {row['lookback']: row for row in old_windows}
            for row in windows:
                old = old_by_window[row['lookback']]
                for kind in ('single', 'pair', 'universe'):
                    if kind not in row:
                        continue
                    if row[kind]['json_sha256'] != old[kind]['json_sha256']:
                        raise AssertionError('Formula differs from frozen baseline')
                    actual, expected = row['asgi_' + kind], old['asgi_' + kind]
                    if actual['response_sha256'] != expected['response_sha256'] or actual['response_bytes'] != expected['response_bytes']:
                        raise AssertionError('Public response bytes or IDs changed from frozen baseline')
            output['baseline_equivalence'] = dict(full_query_identical=True, numerical_reports_identical=True,
                                                  response_bytes_identical=True,
                                                  query_and_analysis_ids_identical_by_complete_response_hash=True)
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[5000, 20000])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--lookbacks', type=int, nargs='+', default=[20, 252])
    parser.add_argument('--skip-universe', action='store_true', help='For a quick single/pair harness smoke test only')
    parser.add_argument('--baseline', type=Path, help='Frozen original JSON; enables full/compact read comparison without modifying it')
    parser.add_argument('--skip-anomaly', action='store_true', help='Smoke only: omit the additional anomaly-dense case')
    args = parser.parse_args()
    baseline_bytes = args.baseline.read_bytes() if args.baseline else None
    baseline = json.loads(baseline_bytes) if baseline_bytes is not None else None
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
                  results=[], universe_results=[])
    if baseline is None:
        output['results'] = [asyncio.run(benchmark(n, args.repeats, args.lookbacks)) for n in args.sizes]
        output['universe_results'] = [] if args.skip_universe else [asyncio.run(benchmark_universe(m, n, args.repeats))
                                                                  for m, n in ((10, 20000), (50, 4000))]
    else:
        output['read_comparison'] = 'unchanged_public_full_query_vs_internal_daily_ohlc_projection'
        output['timing_scope'].update(
            store_load_full='unchanged public full query; includes raw verification and exact totals',
            store_load_compact='private OHLC/Decimal projection; includes raw verification; budget admission timed separately',
            formula_comparison='both full and compact input formulas measured independently; result hashes must match')
        output['baseline'] = dict(path=str(args.baseline), sha256=hashlib.sha256(baseline_bytes).hexdigest())
        for n in args.sizes:
            old = next((r for r in baseline['results'] if r['rows_per_series'] == n), None)
            output['results'].append(asyncio.run(benchmark_compact(n, 2, args.repeats, args.lookbacks, old)))
        if not args.skip_universe:
            for m, n in ((10, 20000), (50, 4000)):
                old = next(r for r in baseline['universe_results'] if r['members'] == m and r['rows_per_series'] == n)
                output['universe_results'].append(asyncio.run(benchmark_compact(n, m, args.repeats, [252], old, universe_only=True)))
        output['anomaly_results'] = [] if args.skip_anomaly else [asyncio.run(benchmark_compact(5000, 2, args.repeats, [252], anomaly_dense=True))]
        if args.baseline.read_bytes() != baseline_bytes:
            raise AssertionError('Frozen baseline file changed during measurement')
        output['baseline']['unchanged'] = True
    hashes_after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked_sources}
    output.update(finished_at=datetime.now(timezone.utc).isoformat(), source_sha256=hashes_after,
                  benchmarked_code_unchanged=hashes_before == hashes_after)
    if hashes_before != hashes_after:
        raise RuntimeError('Benchmarked code changed during run; rerun against final files')
    print(json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == '__main__':
    main()
