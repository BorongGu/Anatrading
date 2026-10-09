"""Fixed-clock aggregation boundaries, independent of real-time trade qualification."""
import asyncio
from copy import deepcopy
from decimal import localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from anatrading.minute_aggregation import aggregation_report
from anatrading.store import EvidenceStore
from anatrading.workbench import create_app


def row(ordinal, clock, **values):
    return dict(ordinal=ordinal, label='2026-09-28T' + clock, tokens={},
                values=dict(open='10', high='12', low='9', close='11', volume='100', amount='1000') | values)


def query(rows, unlocated=(), **selection):
    return dict(snapshot_id='a' * 64, query_id='b' * 64, metadata=dict(period='1m'),
                manifest=dict(qualification='source_evidence_retrospective_only'), selection=selection,
                rows=list(rows), unlocated=list(unlocated))


def sample():
    return [row(i, f'09:{30 + i:02d}') for i in range(1, 6)]


def test_missing_slot_and_crop_never_reanchor_or_fill():
    q = query(sample()[2:])
    before = deepcopy(q)
    bucket = aggregation_report(q)['buckets'][0]
    assert bucket['first_label'] == '2026-09-28T09:31' and bucket['end_label'] == '2026-09-28T09:35'
    assert bucket['missing_labels'] == ['2026-09-28T09:31', '2026-09-28T09:32']
    assert bucket['membership_reason'] == 'not_in_selected_records'
    assert set(bucket['values'].values()) == {None}
    assert bucket['observed_values']['volume'] == '300' and q == before


def test_partial_future_end_is_distinct_from_observed_asof():
    q = query(sample()[:3], cutoff='2026-09-28T09:33')
    bucket = aggregation_report(q)['buckets'][0]
    assert bucket['future_labels'] == ['2026-09-28T09:34', '2026-09-28T09:35']
    assert bucket['membership_reason'] == 'right_labels_not_observed'
    assert bucket['last_observed_label'] == q['selection']['cutoff']
    assert bucket['values']['close'] is None and bucket['observed_values']['close'] == '11'


def test_duplicate_blocks_all_sums_without_deduplication():
    q = query(sample() + [row(9, '09:33')])
    bucket = aggregation_report(q)['buckets'][0]
    assert bucket['duplicate_labels'] == ['2026-09-28T09:33']
    assert bucket['membership_reason'] == 'duplicate_label'
    assert set(bucket['observed_values'].values()) == {None}
    assert len(bucket['members']) == 6


@pytest.mark.parametrize('field,bad', [('amount', None), ('amount', '-1'), ('amount', 'NaN'),
                                     ('volume', '1.5'), ('volume', '-1'), ('high', '1')])
def test_fields_fail_independently(field, bad):
    rows = sample()
    rows[2]['values'][field] = bad
    bucket = aggregation_report(query(rows))['buckets'][0]
    assert bucket['template_complete'] is True and bucket['membership_reason'] is None
    if field == 'high':
        assert bucket['values']['open'] is None and bucket['values']['volume'] == '500'
    else:
        assert bucket['values'][field] is None and bucket['values']['open'] == '10'
        assert bucket['values']['volume' if field == 'amount' else 'amount'] is not None


def test_empty_buckets_lunch_extra_clocks_and_date_do_not_create_fake_zero():
    rows = [row(1, '11:20'), row(2, '11:30'), row(3, '13:01'), row(4, '13:00')]
    report = aggregation_report(query(rows))
    assert [b['end_label'][11:] for b in report['buckets']] == ['11:20', '11:25', '11:30', '13:05']
    empty = report['buckets'][1]
    assert empty['members'] == [] and set(empty['observed_values'].values()) == {None}
    assert report['excluded'] == [dict(ordinal=4, label='2026-09-28T13:00', reason='outside_observed_template')]
    assert not any('12:' in b['end_label'] for b in report['buckets'])


def test_unlocated_membership_is_scoped_and_retained():
    unlocated = dict(ordinal=10, label=None, tokens=dict(source_date='20260928'), values={})
    bucket = aggregation_report(query(sample(), [unlocated]))['buckets'][0]
    assert bucket['membership_reason'] == 'unlocated_membership_unknown'
    assert bucket['observed_values']['volume'] == '500' and bucket['values']['volume'] is None
    later = {**unlocated, 'tokens': dict(source_date='20260929')}
    report = aggregation_report(query(sample(), [later]))
    assert report['buckets'][0]['template_complete'] is True
    assert report['excluded'][0]['reason'] == 'outside_asof_date'
    unknown = {**unlocated, 'tokens': {}}
    assert aggregation_report(query(sample(), [unknown]))['unknown_date_ordinals'] == [10]


def test_exact_hand_calculation_and_low_decimal_context():
    rows = sample()
    for i, value in enumerate(['10', '13', '12', '14', '11']):
        rows[i]['values'].update(high=value, low='9', open='10', close='10')
    rows[-1]['values']['close'] = '11'
    rows[0]['values'].update(volume='9223372036854775807', amount='99999999999999999999.999999999999999999')
    with localcontext() as arithmetic:
        arithmetic.prec = 3
        bucket = aggregation_report(query(rows))['buckets'][0]
    assert bucket['values'] == dict(open='10', high='14', low='9', close='11',
                                   volume='9223372036854776207', amount='100000000000000003999.999999999999999999')
    for source in rows:
        source['values'].update(volume='0', amount='0')
    assert aggregation_report(query(rows))['buckets'][0]['values']['amount'] == '0'


def test_complete_buckets_are_prefix_invariant_and_cutoff_never_borrows():
    rows = sample() + [row(6, '09:36')]
    complete = aggregation_report(query(rows))['buckets'][0]
    assert complete == aggregation_report(query(rows[:5]))['buckets'][0]
    q = query(rows, cutoff='2026-09-28T09:33')
    prefix = aggregation_report(q)
    assert len(prefix['buckets'][0]['members']) == 3
    assert prefix['buckets'][0]['values']['close'] is None
    assert [e['ordinal'] for e in prefix['excluded']] == [4, 5, 6]


@pytest.mark.parametrize('minutes', [True, 1, 10, 120, '5'])
def test_invalid_period_is_not_silently_coerced(minutes):
    with pytest.raises(ValueError, match='invalid_target_minutes'):
        aggregation_report(query(sample()), minutes)


def test_real_minute_fraction_oracle_and_http_binding(tmp_path):
    folder = Path(__file__).resolve().parents[1] / 'artifacts/qualification/minute-read/20261008T140439Z'
    if not folder.exists():
        pytest.skip('Private real sample unavailable; no compatibility claim')
    raw = (folder / 'response.bin').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '826e7bcca37b7dde90a74f6348877044c77dbc1f678629b1a92c1793a6dba4a2'
    data = json.loads(raw)['result']['Value']['600059.SH']
    bundle = dict(request_utf8=(folder / 'request.json').read_text(), response_utf8=raw.decode())
    root = tmp_path / 'store'
    with EvidenceStore(root) as store:
        sid = store.import_bytes(json.dumps(bundle).encode(), 'tdx-http-market-v1')['snapshot_id']
        q = store.query(sid)
        for minutes, count in [(5, 144), (15, 48), (30, 24), (60, 12)]:
            report = aggregation_report(q, minutes)
            assert len(report['buckets']) == count and all(b['template_complete'] for b in report['buckets'])
            assert [m['ordinal'] for b in report['buckets'] for m in b['members']] == list(range(1, 721))
            for bucket in report['buckets']:
                indexes = [m['ordinal'] - 1 for m in bucket['members']]
                source_labels = [f"{data['Date'][i][:4]}-{data['Date'][i][4:6]}-{data['Date'][i][6:]}T"
                                 + data['Time'][i].zfill(6)[:2] + ':' + data['Time'][i].zfill(6)[2:4] for i in indexes]
                assert [member['label'] for member in bucket['members']] == bucket['expected_labels'] == source_labels
                assert bucket['first_label'] == source_labels[0] and bucket['end_label'] == source_labels[-1]
                assert bucket['segment'] == ('morning_labels' if data['Time'][indexes[0]].zfill(6) < '120000' else 'afternoon_labels')
                expected = dict(open=Fraction(data['Open'][indexes[0]]), close=Fraction(data['Close'][indexes[-1]]),
                                high=max(Fraction(data['High'][i]) for i in indexes),
                                low=min(Fraction(data['Low'][i]) for i in indexes),
                                volume=sum(Fraction(data['Volume'][i]) for i in indexes),
                                amount=sum(Fraction(data['Amount'][i]) for i in indexes))
                assert {key: Fraction(value) for key, value in bucket['values'].items()} == expected
            assert sum(int(b['values']['volume']) for b in report['buckets']) == 325909500
            assert sum(Fraction(b['values']['amount']) for b in report['buckets']) == Fraction('377847.25')
            if minutes == 60:
                assert [b['end_label'][11:] for b in report['buckets']] == ['10:30', '11:30', '14:00', '15:00'] * 3

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8765') as client:
                url = '/api/minute-aggregation/' + sid
                parameters = dict(query_id=q['query_id'], target_minutes='5')
                response = await client.get(url, params=parameters)
                assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
                assert response.json() == aggregation_report(q)
                assert (await client.get(url, params={**parameters, 'query_id': 'old'})).status_code == 409
                for invalid in ('1', '10', 'bad', '5.0'):
                    assert (await client.get(url, params={**parameters, 'target_minutes': invalid})).status_code == 400
                assert (await client.get('/api/query/' + sid)).json()['query'] == q
    asyncio.run(scenario())
