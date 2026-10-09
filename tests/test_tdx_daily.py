"""Native quantities are preserved; batch publication keeps per-source outcomes."""
import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from anatrading import tdx_daily, workbench
from anatrading.tdx_acquisition import AcquireError
from test_formats import day_record


def cache(root, symbol, raw=None):
    code, venue = symbol.split('.')
    path = root / 'vipdoc' / venue.lower() / 'lday' / f'{venue.lower()}{code}.day'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(day_record() if raw is None else raw)
    return path


def test_reads_three_venues_exactly_and_rejects_path_injection(tmp_path):
    for symbol in ('600059.SH', '000001.SZ', '920000.BJ'):
        path = cache(tmp_path, symbol)
        assert tdx_daily.read_daily_cache(tmp_path, symbol) == path.read_bytes()
    for symbol in ('../600059.SH', '600059.sh', '600059', '600059.US'):
        with pytest.raises(AcquireError, match='invalid_tdx_symbol'): tdx_daily.read_daily_cache(tmp_path, symbol)
    with pytest.raises(AcquireError, match='daily_cache_missing'): tdx_daily.read_daily_cache(tmp_path, '600000.SH')


def test_current_pool_validates_response_before_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(tdx_daily.acquisition, '_client_identity', lambda client: dict(pid=1))
    def request(port, method, path, body, headers, **kwargs):
        assert json.loads(body) == dict(id=1, method='get_stock_list', params=dict(market='5', list_type=0))
        return 200, json.dumps(dict(id=1, result=dict(ErrorId='0', Value=['600059.SH', '920000.BJ']))).encode()
    monkeypatch.setattr(tdx_daily.acquisition, '_http', request)
    symbols, capture = tdx_daily.current_symbols(tmp_path)
    assert symbols == ['600059.SH', '920000.BJ']
    assert json.loads(capture['response_utf8'])['result']['Value'] == symbols
    for values in (['600059.SH', '600059.SH'], ['private-account'], None):
        monkeypatch.setattr(tdx_daily.acquisition, '_http', lambda *a, **kw: (200, json.dumps(dict(id=1, result=dict(ErrorId='0', Value=values))).encode()))
        with pytest.raises(AcquireError, match='invalid_stock_list'): tdx_daily.current_symbols(tmp_path)


def test_batch_missing_is_recorded_and_identical_raw_is_published_unchanged(tmp_path, monkeypatch):
    cache(tmp_path / 'client', '600059.SH')
    monkeypatch.setattr(tdx_daily, 'current_symbols', lambda client: (['600059.SH', '000001.SZ'], dict(request_utf8='request', response_utf8='response')))
    monkeypatch.setattr(tdx_daily.acquisition, '_config', lambda root, port: dict(csrf_token='secret'))
    calls = []
    def publish(port, method, path, raw, headers, **kwargs):
        calls.append((path, raw))
        assert headers['X-Anatrading-Token'] == 'secret'
        return 200, json.dumps(dict(attempt=dict(status='committed', snapshot_id='a'*64, raw_sha256=hashlib.sha256(raw).hexdigest()))).encode()
    monkeypatch.setattr(tdx_daily.acquisition, '_http', publish)
    result = tdx_daily.import_current_caches(tmp_path / 'data', tmp_path / 'client')
    assert result['status'] == 'completed' and result['coverage'] == 'partial'
    assert (result['expected'], result['committed'], result['missing'], result['failed']) == (2, 1, 1, 0)
    assert calls[0][1] == day_record() and 'instrument=600059.SH' in calls[0][0]
    log = Path(result['evidence_directory']) / 'outcomes.jsonl'
    entries = [json.loads(line) for line in log.read_text().splitlines()]
    assert entries[1]['symbol'] == '000001.SZ' and entries[1]['status'] == 'missing'
    assert 'secret' not in ''.join(p.read_text() for p in log.parent.glob('*.json'))


def test_publication_uncertainty_stops_without_retry_or_false_commit(tmp_path, monkeypatch):
    cache(tmp_path / 'client', '600059.SH')
    monkeypatch.setattr(tdx_daily, 'current_symbols', lambda client: (['600059.SH'], dict(request_utf8='request', response_utf8='response')))
    monkeypatch.setattr(tdx_daily.acquisition, '_config', lambda root, port: dict(csrf_token='secret'))
    calls = []
    def publish(*args, **kwargs):
        calls.append(1)
        raise AcquireError('http_result_unknown')
    monkeypatch.setattr(tdx_daily.acquisition, '_http', publish)
    result = tdx_daily.import_current_caches(tmp_path / 'data', tmp_path / 'client')
    assert result['status'] == 'failed' and result['committed'] == 0 and calls == [1]
    entries = (Path(result['evidence_directory']) / 'outcomes.jsonl').read_text()
    assert 'http_result_unknown' in entries


def test_progress_reader_collision_retries_only_replacement(tmp_path, monkeypatch):
    cache(tmp_path / 'client', '600059.SH')
    monkeypatch.setattr(tdx_daily, 'current_symbols', lambda client: (['600059.SH'], dict(request_utf8='request', response_utf8='response')))
    monkeypatch.setattr(tdx_daily.acquisition, '_config', lambda root, port: dict(csrf_token='secret'))
    publications = []
    def publish(port, method, path, raw, headers, **kwargs):
        publications.append(1)
        return 200, json.dumps(dict(attempt=dict(status='committed', snapshot_id='a'*64, raw_sha256=hashlib.sha256(raw).hexdigest()))).encode()
    monkeypatch.setattr(tdx_daily.acquisition, '_http', publish)
    original = Path.replace
    collisions = []
    def replace(path, target):
        if json.loads(path.read_text())['processed'] == 1 and not collisions:
            collisions.append(1)
            error = PermissionError('reader without delete sharing')
            error.winerror = 5
            raise error
        return original(path, target)
    monkeypatch.setattr(Path, 'replace', replace)
    result = tdx_daily.import_current_caches(tmp_path / 'data', tmp_path / 'client')
    assert result['status'] == 'completed' and result['processed'] == 1 and publications == [1]
    assert json.loads((Path(result['evidence_directory']) / 'progress.json').read_text()) == result


def test_other_progress_io_failure_seals_failed_after_committed_outcome(tmp_path, monkeypatch):
    cache(tmp_path / 'client', '600059.SH')
    monkeypatch.setattr(tdx_daily, 'current_symbols', lambda client: (['600059.SH'], dict(request_utf8='request', response_utf8='response')))
    monkeypatch.setattr(tdx_daily.acquisition, '_config', lambda root, port: dict(csrf_token='secret'))
    publications = []
    def publish(port, method, path, raw, headers, **kwargs):
        publications.append(1)
        return 200, json.dumps(dict(attempt=dict(status='committed', snapshot_id='a'*64, raw_sha256=hashlib.sha256(raw).hexdigest()))).encode()
    monkeypatch.setattr(tdx_daily.acquisition, '_http', publish)
    original = Path.replace
    def replace(path, target):
        report = json.loads(path.read_text())
        if report['processed'] == 1 and report['status'] == 'running':
            raise OSError('unrelated persistent I/O failure')
        return original(path, target)
    monkeypatch.setattr(Path, 'replace', replace)
    with pytest.raises(OSError):
        tdx_daily.import_current_caches(tmp_path / 'data', tmp_path / 'client')
    folder = next((tmp_path / 'data/acquisition/daily-cache').iterdir())
    report = json.loads((folder / 'progress.json').read_text())
    assert report['status'] == 'failed' and report['committed'] == 1 and publications == [1]
    assert len((folder / 'outcomes.jsonl').read_text().splitlines()) == 1


def test_explicit_start_at_keeps_original_pool_capture_and_labels_subset(tmp_path, monkeypatch):
    cache(tmp_path / 'client', '000001.SZ')
    capture = dict(request_utf8='request', response_utf8='original full source response')
    monkeypatch.setattr(tdx_daily, 'current_symbols', lambda client: (['600059.SH', '000001.SZ'], capture))
    monkeypatch.setattr(tdx_daily.acquisition, '_config', lambda root, port: dict(csrf_token='secret'))
    def publish(port, method, path, raw, headers, **kwargs):
        assert 'instrument=000001.SZ' in path
        return 200, json.dumps(dict(attempt=dict(status='committed', snapshot_id='a'*64, raw_sha256=hashlib.sha256(raw).hexdigest()))).encode()
    monkeypatch.setattr(tdx_daily.acquisition, '_http', publish)
    result = tdx_daily.import_current_caches(tmp_path / 'data', tmp_path / 'client', start_at='000001.SZ')
    assert (result['pool_size'], result['skipped_prefix'], result['expected'], result['processed']) == (2, 1, 1, 1)
    assert result['coverage'] == 'selected_current_list_cache_files'
    assert json.loads((Path(result['evidence_directory']) / 'catalog.json').read_text()) == capture
    with pytest.raises(AcquireError, match='invalid_tdx_symbol'):
        tdx_daily.import_current_caches(tmp_path / 'data', tmp_path / 'client', start_at='600000.SH')


def test_page_cache_read_preserves_original_uint32_and_reuses_snapshot(tmp_path, monkeypatch):
    import struct
    raw = struct.pack('<IIIIIfII', 20260928, 1173, 1210, 1120, 1173, 1000.0, 122897667, 0)
    monkeypatch.setattr(workbench, 'read_daily_cache', lambda client, symbol: raw, raising=False)
    async def scenario():
        app = workbench.create_app(tmp_path / 'store')
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8765') as client:
                config = (await client.get('/api/config')).json()
                headers = {'Origin':'http://127.0.0.1:8765','X-Anatrading-Token':config['csrf_token']}
                route = '/api/read-tdx-daily-cache?symbol=600059.SH'
                first = (await client.post(route, headers=headers)).json()['attempt']
                assert first['status'] == 'committed'
                second = (await client.post(route, headers=headers)).json()['attempt']
                assert first['snapshot_id'] == second['snapshot_id']
                q = (await client.get('/api/query/'+first['snapshot_id'])).json()['query']
                assert q['metadata']['period'] == '1d'
                assert q['rows'][0]['values']['volume'] == '122897667'
                assert q['rows'][0]['volume_shares'] is None
                assert q['metadata']['interpretation']['instrument'] == '600059.SH'
                for parameters in ('?symbol=600059.SH&count=1','?symbol=600059.SH&symbol=000001.SZ'):
                    assert (await client.post('/api/read-tdx-daily-cache'+parameters,headers=headers)).status_code == 400
                assert (await client.post(route,headers=headers,content=b'unexpected')).status_code == 400
                assert (await client.post(route,headers={**headers,'X-Anatrading-Token':'wrong'})).status_code == 403
    asyncio.run(scenario())


def test_real_three_venue_native_fields_and_original_integers(tmp_path):
    from fractions import Fraction
    import struct
    from anatrading.store import EvidenceStore
    folder = Path(__file__).resolve().parents[1] / 'artifacts/qualification/daily-native'
    if not (folder/'manifest.json').exists(): pytest.skip('Private native samples unavailable')
    manifest = json.loads((folder/'manifest.json').read_text())
    assert set(manifest) == {'600059.SH','000001.SZ','920000.BJ'}
    with EvidenceStore(tmp_path/'store') as store:
        for symbol, expected in manifest.items():
            data = (folder/(symbol+'.day')).read_bytes()
            assert hashlib.sha256(data).hexdigest() == expected['sha256']
            source = list(struct.iter_unpack('<IIIIIfII',data))
            sid = store.import_bytes(data,'tdx-public-day-v1',interpretation=dict(instrument=symbol,venue=symbol[-2:]))['snapshot_id']
            q = store.query(sid)
            assert len(q['rows']) == len(source) == expected['records']
            assert not q['unlocated']
            for row, original in zip(q['rows'],source):
                assert row['label'].replace('-','') == str(original[0])
                for index, field in enumerate(('open','high','low','close'),1):
                    assert Fraction(row['values'][field]) == Fraction(original[index],100)
                assert Fraction(row['values']['amount']) == Fraction.from_float(original[5])
                assert int(row['values']['volume']) == original[6]
                assert row['volume_shares'] is None and row['amount_cny'] is None
