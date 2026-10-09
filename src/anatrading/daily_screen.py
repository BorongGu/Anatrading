"""Exact, explicitly dated conditions on a fixed current-source collection."""
from datetime import date
from fractions import Fraction
from functools import lru_cache
import struct

from .daily_coverage import selected_collection, verified_cache
from .daily_volume import daily_volume_report
from .formats import _day
from .numeric import NumericError, decimal_text, decimal_value
from .path_efficiency import efficiency_report
from .price_channel import channel_report
from .store import _identity
from .tdx_acquisition import AcquireError


@lru_cache(maxsize=32768)
def _date_label(value):
    if not 10000000 <= value <= 99999999:
        return None
    try:
        return date(value//10000, value//100 % 100, value % 100).isoformat()
    except ValueError:
        return None


def validate_parameters(*, source_date, channel_lookback=20, volume_lookback=20, efficiency_lookback=10,
                        channel_relation=None, minimum_volume=None, minimum_efficiency=None, direction=None):
    try:
        if not isinstance(source_date, str) or date.fromisoformat(source_date).isoformat() != source_date:
            raise ValueError()
        if any(type(n) is not int or not 2 <= n <= 252 for n in (channel_lookback, volume_lookback, efficiency_lookback)):
            raise ValueError()
        if channel_relation not in (None, 'above', 'below', 'inside', 'touch_upper', 'touch_lower', 'touch_both') or direction not in (None, 'up', 'down', 'flat'):
            raise ValueError()
        thresholds = {}
        for name, value in (('minimum_volume', minimum_volume), ('minimum_efficiency', minimum_efficiency)):
            if value is None:
                thresholds[name] = None
            else:
                number = decimal_value(value)
                if number < 0 or name == 'minimum_efficiency' and number > 1:
                    raise ValueError()
                thresholds[name] = decimal_text(number)
        return dict(source_date=source_date, channel_lookback=channel_lookback, volume_lookback=volume_lookback,
                    efficiency_lookback=efficiency_lookback, channel_relation=channel_relation, direction=direction, **thresholds)
    except (ValueError, TypeError, NumericError):
        raise AcquireError('invalid_daily_screen') from None


def screen_values(raw, snapshot_id, **parameters):
    params = validate_parameters(**parameters)
    result = dict(ordinal=None, close=None, channel=None, volume=None, efficiency=None,
                  conditions={}, eligible=False, matched=False, reason=None)
    if not raw or len(raw) % 32:
        raise AcquireError('daily_cache_evidence_mismatch')
    dates, unknown = {}, 0
    for index, (value,) in enumerate(struct.iter_unpack('<I28x', raw)):
        day = _date_label(value)
        if day is None:
            unknown += 1
            continue
        if day <= params['source_date']:
            dates.setdefault(day, []).append(index)
    target = dates.get(params['source_date'], [])
    reason = ('date_set_integrity_unknown' if unknown else 'target_date_missing' if not target
              else 'duplicate_target_date' if len(target) != 1 else None)
    if reason:
        result['reason'] = reason
        return result
    # Select date slots before validating fields; keep all records in duplicate slots.
    length = max(params['channel_lookback'], params['volume_lookback'], params['efficiency_lookback'])+1
    window = sorted(dates)[-length:]
    indices = [index for day in window for index in dates[day]]
    _, decoded = _day(b''.join(raw[index*32:(index+1)*32] for index in indices))
    rows = [dict(ordinal=index+1, label=row.label, tokens=row.tokens,
                 values={name: None if value is None else decimal_text(value) for name, value in row.values.items()})
            for index, row in zip(indices, decoded)]
    anchor = next(row for row in rows if row['ordinal'] == target[0]+1)
    context = dict(snapshot_id=snapshot_id, query_id=_identity(dict(scope='screen-source-window-v1',
        snapshot_id=snapshot_id, source_date=params['source_date'], ordinals=[row['ordinal'] for row in rows])),
        metadata=dict(period='1d'), rows=rows, unlocated=[])
    query = dict(context, rows=[anchor])
    channel = channel_report(query, context, params['channel_lookback'])['rows'][0]
    volume = daily_volume_report(query, context, params['volume_lookback'])['rows'][0]
    efficiency = efficiency_report(query, context, params['efficiency_lookback'])['rows'][0]
    conditions = {}
    if params['channel_relation'] is not None:
        conditions['channel_relation'] = None if channel['close_relation'] is None else channel['close_relation'] == params['channel_relation']
    if params['direction'] is not None:
        conditions['direction'] = None if efficiency['direction'] is None else efficiency['direction'] == params['direction']
    for name, ratio in (('minimum_volume', volume['ratio']), ('minimum_efficiency', efficiency['efficiency'])):
        if params[name] is not None:
            conditions[name] = None if ratio is None else Fraction(int(ratio['numerator']), int(ratio['denominator'])) >= Fraction(params[name])
    eligible = all(value is not None for value in conditions.values())
    result.update(ordinal=anchor['ordinal'], close=anchor['values']['close'], channel=channel, volume=volume,
                  efficiency=efficiency, conditions=conditions, eligible=eligible,
                  matched=eligible and all(conditions.values()), reason=None if eligible else 'condition_unavailable')
    return result


def screen_report(root, snapshots, run_ids, **parameters):
    params = validate_parameters(**parameters)
    pool, pool_sha, outcomes = selected_collection(root, run_ids)
    catalog = {snapshot['snapshot_id']: snapshot for snapshot in snapshots}
    counts = dict(pool=len(pool), processed=len(outcomes), committed=0, missing=0, failed=0,
                  unprocessed=len(pool)-len(outcomes), target_unique=0, target_missing=0, target_duplicate=0,
                  date_set_unknown=0, eligible=0, matched=0, not_evaluated=0)
    rows = []
    for symbol in pool:
        item = outcomes.get(symbol, dict(status='unprocessed'))
        row = dict(symbol=symbol, status=item['status'], snapshot_id=None, raw_sha256=None, analysis=None)
        if item['status'] == 'committed':
            try:
                snapshot = catalog[item['snapshot_id']]
            except KeyError:
                raise AcquireError('daily_cache_evidence_mismatch') from None
            raw = verified_cache(root, snapshot, item)
            analysis = screen_values(raw, item['snapshot_id'], **params)
            counts['committed'] += 1
            reason_count = {'target_date_missing': 'target_missing', 'duplicate_target_date': 'target_duplicate',
                            'date_set_integrity_unknown': 'date_set_unknown'}.get(analysis['reason'])
            counts[reason_count or 'target_unique'] += 1
            counts['eligible'] += int(analysis['eligible'])
            counts['matched'] += int(analysis['matched'])
            counts['not_evaluated'] += int(not analysis['eligible'])
            state = 'matched' if analysis['matched'] else 'unmatched' if analysis['eligible'] else 'not_evaluated'
            row.update(status=state, snapshot_id=item['snapshot_id'], raw_sha256=item['raw_sha256'], analysis=analysis)
        elif item['status'] != 'unprocessed':
            counts['missing' if item['status'] == 'missing' else 'failed'] += 1
        rows.append(row)
    report = dict(method_id='current-pool-daily-screen-v1', parameters=params, run_ids=sorted(run_ids),
                  pool_sha256=pool_sha, scope='current_source_market_5_not_historical_universe',
                  qualification='conditional_source_values', counts=counts, rows=rows,
                  assumptions=['constant_price_scale', 'comparable_adjustment_basis', 'constant_quantity_scale', 'comparable_share_basis'],
                  unknowns=['historical_universe', 'known_at', 'bar_closure', 'adjustment', 'quantity_unit', 'calendar_coverage', 'synchronous_capture'],
                  flat_policy='zero_with_explicit_reason', enabled_conditions=[name for name in
                      ('channel_relation', 'minimum_volume', 'minimum_efficiency', 'direction') if params[name] is not None])
    return dict(report, screen_id=_identity(report))
