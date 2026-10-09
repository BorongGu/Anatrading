"""Ex-post changes of source closes, without a trading-return interpretation."""
from collections import Counter
from datetime import date
from fractions import Fraction
import struct

from .daily_coverage import _native_date_label
from .formats import _day
from .numeric import decimal_text
from .path_efficiency import _member
from .tdx_acquisition import AcquireError
from .volume_at_time import _fraction


def validate_interval(source_date, evaluation_date):
    try:
        if (not isinstance(source_date, str) or not isinstance(evaluation_date, str)
                or date.fromisoformat(source_date).isoformat() != source_date
                or date.fromisoformat(evaluation_date).isoformat() != evaluation_date
                or evaluation_date <= source_date):
            raise ValueError()
    except (ValueError, TypeError):
        raise AcquireError('invalid_daily_followup') from None


def signed_fraction(value):
    text = _fraction(abs(value.numerator)*100, value.denominator)['display']
    if value < 0 and text != '0.0000':
        text = '-'+text
    return dict(numerator=str(value.numerator), denominator=str(value.denominator), percent_display=text)


def source_change(raw, source_date, evaluation_date):
    validate_interval(source_date, evaluation_date)
    if not raw or len(raw) % 32:
        raise AcquireError('daily_cache_evidence_mismatch')
    indices, unknown = {source_date: [], evaluation_date: []}, 0
    for index, (value,) in enumerate(struct.iter_unpack('<I28x', raw)):
        label = _native_date_label(value)
        if label is None:
            unknown += 1
        elif label in indices:
            indices[label].append(index)
    result = dict(status='not_evaluated', reason=None, start=None, end=None, change=None)
    if unknown:
        result['reason'] = 'date_set_integrity_unknown'
        return result
    members = []
    for name, day in [('start', source_date), ('end', evaluation_date)]:
        positions = indices[day]
        if not positions:
            result['reason'] = name+'_date_missing'
            return result
        if len(positions) != 1:
            result['reason'] = 'duplicate_'+name+'_date'
            return result
        index = positions[0]
        _, decoded = _day(raw[index*32:(index+1)*32])
        row = decoded[0]
        member = _member(day, [dict(ordinal=index+1, label=row.label,
            values={field: None if value is None else decimal_text(value) for field, value in row.values.items()})])
        result[name] = member
        if member['reason']:
            result['reason'] = member['reason']
            return result
        members.append(Fraction(member['close']))
    if members[0] == 0:
        result['reason'] = 'zero_start_close'
        return result
    result.update(status='computed', change=signed_fraction((members[1]-members[0])/members[0]))
    return result


def _quantile(values, probability):
    if not values:
        return None
    position = (len(values)-1)*probability
    left = position.numerator//position.denominator
    weight = position-left
    value = values[left] if weight == 0 else values[left]*(1-weight)+values[left+1]*weight
    return signed_fraction(value)


def group_summary(rows, group):
    selected = [row['observation'] for row in rows if row['group'] == group]
    known = sorted(Fraction(int(item['change']['numerator']), int(item['change']['denominator']))
                   for item in selected if item['status'] == 'computed')
    signs = dict(positive=sum(value > 0 for value in known), zero=sum(value == 0 for value in known),
                 negative=sum(value < 0 for value in known))
    return dict(selected=len(selected), observed=len(known), missing=len(selected)-len(known),
        coverage=signed_fraction(Fraction(len(known), len(selected))) if selected else None,
        missing_reasons=dict(sorted(Counter(item['reason'] for item in selected if item['status'] != 'computed').items())),
        quantiles={name: _quantile(known, p) for name, p in [('q1', Fraction(1,4)), ('median', Fraction(1,2)), ('q3', Fraction(3,4))]},
        sign_counts=signs, sign_proportions={name: signed_fraction(Fraction(count, len(known))) if known else None for name, count in signs.items()})
