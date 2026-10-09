"""Exact condition evaluation, target anchors and native-window equivalence."""
from copy import deepcopy
import struct

import pytest

from anatrading import daily_screen
from anatrading.daily_volume import daily_volume_report
from anatrading.path_efficiency import efficiency_report
from anatrading.price_channel import channel_report
from anatrading.tdx_acquisition import AcquireError
from test_daily_coverage import POOL, committed, run
from test_formats import day_record


def raw_record(day, close, volume=100, *, opening=None, amount=1000):
    return struct.pack('<IIIIIfII', 20260900+day, close if opening is None else opening,
                       close+1, max(0, close-1), close, amount, volume, 0)


PARAMS = dict(source_date='2026-09-03', channel_lookback=2, volume_lookback=2, efficiency_lookback=2)


def evaluate(raw, **rules):
    return daily_screen.screen_values(raw, 'a'*64, **PARAMS, **rules)


def test_exact_thresholds_ignore_rounded_display():
    raw = raw_record(1, 100, 100000)+raw_record(2, 600, 100000)+raw_record(3, 500, 199996)
    result = evaluate(raw, minimum_volume='2', minimum_efficiency='0.6667')
    assert result['volume']['ratio']['display'] == '2.0000'
    assert result['efficiency']['efficiency']['display'] == '0.6667'
    assert result['eligible'] and not result['matched']
    assert result['conditions'] == {'minimum_volume': False, 'minimum_efficiency': False}
    assert evaluate(raw, minimum_volume='1.99996', minimum_efficiency='0.6666')['matched']


def test_hand_channel_and_direction_are_independent_of_unsigned_efficiency():
    raw = raw_record(1, 300)+raw_record(2, 200)+raw_record(3, 100)
    result = evaluate(raw, channel_relation='below', direction='down', minimum_efficiency='1')
    assert result['matched'] and result['channel']['close_relation'] == 'below'
    assert result['efficiency']['direction'] == 'down'
    assert not evaluate(raw, direction='up')['matched']


def test_unselected_bad_price_and_amount_do_not_block_quantity():
    raw = raw_record(1, 100)+raw_record(2, 110)+raw_record(3, 120, 200, opening=999, amount=float('nan'))
    result = evaluate(raw, minimum_volume='2')
    assert result['eligible'] and result['matched'] and result['channel']['comparison_reason'] == 'invalid_ohlc'
    blocked = evaluate(raw, minimum_volume='2', channel_relation='above')
    assert not blocked['eligible'] and blocked['conditions']['channel_relation'] is None


def test_target_is_exact_and_unique_and_never_replaced_by_last_cache_date():
    raw = raw_record(1, 100)+raw_record(2, 110)
    assert evaluate(raw)['reason'] == 'target_date_missing'
    repeated = raw+raw_record(3, 120)+raw_record(3, 120)
    assert evaluate(repeated)['reason'] == 'duplicate_target_date'


def test_previous_bad_duplicate_occupies_window_and_is_not_replaced():
    raw = raw_record(1, 100)+raw_record(2, 110)+raw_record(2, 110)+raw_record(3, 120)
    result = evaluate(raw, minimum_volume='1')
    assert not result['eligible'] and result['volume']['reason'] == 'duplicate_date'
    assert result['volume']['history_dates'] == ['2026-09-01', '2026-09-02']
    assert evaluate(raw)['eligible']  # no enabled condition requires these unavailable metrics


def test_readable_future_bad_values_do_not_change_past_features():
    raw = raw_record(1, 100)+raw_record(2, 110)+raw_record(3, 120, 200)
    before = evaluate(raw, minimum_volume='1', direction='up')
    after = evaluate(raw+raw_record(4, 0, 0, opening=999, amount=float('nan')), minimum_volume='1', direction='up')
    assert before == after
    unreadable = raw+day_record(date=20260230)
    assert evaluate(unreadable)['reason'] == 'date_set_integrity_unknown'


@pytest.mark.parametrize('invalid_date',[10101,9991231,0])
def test_native_dates_without_eight_digits_are_unlocated(invalid_date):
    raw=raw_record(1,100)+raw_record(2,110)+raw_record(3,120)+day_record(date=invalid_date)
    assert evaluate(raw)['reason']=='date_set_integrity_unknown'


def test_source_ordinals_preserved_when_dates_are_out_of_order():
    raw = raw_record(3, 120)+raw_record(1, 100)+raw_record(2, 110)
    result = evaluate(raw)
    assert result['ordinal'] == 1
    assert result['channel']['members'][0]['ordinals'] == [2]
    assert result['channel']['members'][1]['ordinals'] == [3]


def test_flat_efficiency_convention_is_not_missing():
    result = evaluate(b''.join(raw_record(day, 100) for day in [1, 2, 3]), minimum_efficiency='0', direction='flat')
    assert result['matched'] and result['efficiency']['reason'] == 'zero_path_convention'


def test_zero_quantity_baseline_only_blocks_enabled_quantity_condition():
    raw=b''.join(raw_record(day,100,0) for day in [1,2,3])
    assert not evaluate(raw,minimum_volume='0')['eligible']
    assert evaluate(raw,minimum_efficiency='0')['matched']


def test_intraday_high_crossing_is_not_close_above_channel():
    raw=struct.pack('<IIIIIfII',20260901,200,400,100,200,1000,100,0)
    raw+=struct.pack('<IIIIIfII',20260902,200,400,100,200,1000,100,0)
    raw+=struct.pack('<IIIIIfII',20260903,300,500,200,300,1000,100,0)
    result=evaluate(raw,channel_relation='above')
    assert result['channel']['range_relation']=='upper_only'
    assert result['channel']['close_relation']=='inside' and not result['matched']


@pytest.mark.parametrize('rules', [dict(source_date='bad'), dict(channel_lookback=True), dict(volume_lookback=1),
    dict(minimum_volume='NaN'), dict(minimum_volume='-1'), dict(minimum_efficiency='1.1'),
    dict(minimum_efficiency='0.1234567890123456789'), dict(direction='buy'), dict(channel_relation='buy')])
def test_invalid_screen_parameters(rules):
    with pytest.raises(AcquireError, match='invalid_daily_screen'):
        daily_screen.validate_parameters(**{**PARAMS, **rules})


def test_collection_counts_keep_whole_pool_and_unprocessed(tmp_path):
    first, snapshot = committed(tmp_path, POOL[0], [20260901, 20260902, 20260903])
    run(tmp_path, 'a'*32, [first, dict(symbol=POOL[1], status='missing')], state='failed')
    result = daily_screen.screen_report(tmp_path, [snapshot], ['a'*32], **PARAMS)
    assert result['counts'] == dict(pool=3, processed=2, committed=1, missing=1, failed=0, unprocessed=1,
        target_unique=1, target_missing=0, target_duplicate=0, date_set_unknown=0, eligible=1, matched=1, not_evaluated=0)
    assert [row['status'] for row in result['rows']] == ['matched', 'missing', 'unprocessed']
    assert result['rows'][0]['snapshot_id'] == snapshot['snapshot_id']


def test_http_screen_preserves_conditions_and_rejects_bad_parameters(tmp_path):
    import asyncio
    from test_workbench import running
    root=tmp_path/'root'
    run(root,'a'*32,[dict(symbol=POOL[0],status='missing')])
    async def scenario():
        async with running(root) as (_,client,auth):
            params=dict(run_ids='a'*32,**PARAMS,minimum_volume='2')
            reply=await client.get('/api/daily-screen',params=params)
            assert reply.status_code==200
            report=reply.json()['screen']
            assert report['parameters']['source_date']=='2026-09-03'
            assert report['enabled_conditions']==['minimum_volume'] and report['counts']['pool']==3
            for field,value in [('minimum_efficiency','1.1'),('source_date','bad'),('volume_lookback','1'),('channel_relation','buy')]:
                bad=await client.get('/api/daily-screen',params={**params,field:value})
                assert bad.status_code==400 and bad.json()['error']=='invalid_daily_screen'
    asyncio.run(scenario())


def test_native_slice_matches_full_stored_query_when_real_samples_exist():
    from pathlib import Path
    from anatrading.store import EvidenceStore
    base = Path(__file__).resolve().parents[1]/'artifacts/qualification/daily-native'
    if not (base/'600059.SH.day').exists(): pytest.skip('private real files are not in public repository')
    import tempfile
    with tempfile.TemporaryDirectory(dir=base.parent.parent/'tmp') as directory:
        with EvidenceStore(directory) as store:
            for symbol in ['600059.SH', '000001.SZ', '920000.BJ']:
                raw=(base/f'{symbol}.day').read_bytes()
                attempt=store.import_bytes(raw,'tdx-public-day-v1', filename=f'{symbol}.day',
                                           interpretation=dict(instrument=symbol,venue=symbol[-2:]))
                sid=attempt['snapshot_id']; context=store.query(sid,cutoff='2026-09-30')
                query=deepcopy(context); query['rows']=[r for r in context['rows'] if r['label']=='2026-09-30']
                actual=daily_screen.screen_values(raw,sid,source_date='2026-09-30',channel_lookback=20,volume_lookback=20,efficiency_lookback=10)
                assert actual['channel'] == channel_report(query,context,20)['rows'][0]
                assert actual['volume'] == daily_volume_report(query,context,20)['rows'][0]
                assert actual['efficiency'] == efficiency_report(query,context,10)['rows'][0]
