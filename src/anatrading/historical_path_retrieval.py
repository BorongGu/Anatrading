"""Fixed-cutoff, amplitude-preserving historical source paths.

Distances are exact integer sums with one rational reduction per window. Only
presentation is rounded. No future labels, learned distance, or return claims.
"""
from datetime import date
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import json

from .pair_research import symbol_identity
from .peer_relative_research import _checks, _IDENTITY, _ADJUSTMENT, _PRICE_CHECKS, _QUANTITY
from .research_series import (
    MAX_RESEARCH_ROWS, _source_date, daily_bars, source_rejection, strict_date,
)

METHOD_ID = 'historical-source-path-retrieval-v1'
STEPS = 20
MAX_MATCHES = 3
MAX_RESULT_BYTES = 4 * 1024 * 1024
MAX_OTHER_BYTES = 256 * 1024
PARAMETERS = dict(steps=STEPS, max_matches=MAX_MATCHES,
                  metric='source_ratio_squared_mean_v1',
                  qualification_rule='strict_daily_groups_v1',
                  display_rule='12_significant_half_even_scientific_v1')
LEDGER_COLUMNS = ['start_index', 'reason', 'distance', 'endpoint_distance',
                  'path', 'endpoint', 'recent', 'first_invalid_index']
PATH_ERRORS = {
    'path_cutoff_missing', 'path_history_insufficient', 'path_query_invalid',
    'path_unreadable_date', 'path_numerical_failure', 'path_result_limit',
    'known_negative_source', 'ordinal_window_not_supported',
    'path_source_check_failed', 'invalid_source_checks',
}
_METHODS = ('path', 'endpoint', 'recent')
_DISPLAY = Context(prec=12, rounding=ROUND_HALF_EVEN)
_SCORE_BOUND = 20 * 10 ** 152


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def _display(value):
    with localcontext(_DISPLAY):
        return format(Decimal(value.numerator) / Decimal(value.denominator), 'E')


def _units(value):
    """DECIMAL(38,18) to 10^-18 integer units without context arithmetic."""
    sign, digits, exponent = value.as_tuple()
    units = int(''.join(map(str, digits))) * 10 ** (exponent + 18)
    if sign or not 0 < units < 10 ** 38:
        raise ValueError('path_numerical_failure')
    return units


def _scores(q, w):
    denominator = q[0] * w[0]
    differences = [a * w[0] - b * q[0] for a, b in zip(q[1:], w[1:], strict=True)]
    numerator = sum(delta * delta for delta in differences)
    squared_denominator = STEPS * denominator * denominator
    if not (0 <= numerator < _SCORE_BOUND and 0 < squared_denominator < _SCORE_BOUND):
        raise ValueError('path_numerical_failure')
    return Fraction(numerator, squared_denominator), Fraction(abs(differences[-1]), denominator)


def _failed_group_reason(failed):
    for checks, reason in (
        (_IDENTITY, 'source_identity_conflict'),
        (_ADJUSTMENT, 'source_adjustment_check_failed'),
        (_PRICE_CHECKS, 'source_price_check_failed'),
        ({'structure'}, 'source_structure_failed'),
        ({'label', 'duplicate_label', 'source_date_range', 'source_order'}, 'source_position_check_failed'),
        ({'known_negative_sample'}, 'known_negative_source'),
    ):
        if failed & checks:
            return reason
    return 'unclassified_source_failure' if failed - _QUANTITY else None


def _window(start, bars, units, raw_prices, q_units, score):
    end = start + STEPS
    values = units[start:end + 1]
    relative = [Fraction(value - values[0], values[0]) for value in values]
    differences = [Fraction(q - q_units[0], q_units[0]) - value
                   for q, value in zip(q_units, relative, strict=True)]
    maximum_step = max(range(STEPS + 1), key=lambda step: abs(differences[step]))
    peak_step = 0
    drawdown, witness = Fraction(0), (0, 0)
    for step, value in enumerate(values):
        if value > values[peak_step]:
            peak_step = step
        current = Fraction(values[peak_step] - value, values[peak_step])
        if current > drawdown:
            drawdown, witness = current, (peak_step, step)
    start_day, end_day = bars[start]['date'], bars[end]['date']
    return dict(start_index=start, end_index=end, start_date=start_day, end_date=end_day,
                calendar_days=(date.fromisoformat(end_day) - date.fromisoformat(start_day)).days,
                ordinals=[b['ordinal'] for b in bars[start:end + 1]],
                prices=raw_prices[start:end + 1], relative_path=[_display(v) for v in relative],
                endpoint_change=_display(relative[-1]),
                max_drawdown=dict(value=_display(drawdown), peak_step=witness[0], trough_step=witness[1]),
                distance=_display(score[0]), endpoint_distance=_display(score[1]),
                max_point_difference=dict(value=_display(abs(differences[maximum_step])), step=maximum_step),
                differences=[_display(v) for v in differences])


def _select(scores, method):
    selected = []
    for _ in range(MAX_MATCHES):
        best, best_score = None, None
        for start, score in enumerate(scores):
            if score is None or any(abs(start - chosen) <= STEPS for chosen in selected):
                continue
            key = score[0] if method == 'path' else score[1] if method == 'endpoint' else -start
            # Ascending traversal and strict improvement retain the earlier
            # start on a true distance tie; display rounding is never involved.
            if best is None or key < best_score:
                best, best_score = start, key
        if best is None:
            break
        selected.append(best)
    return selected


def _validate_result_budget(result):
    # Each comma is included in the frozen per-row/date bound. The small
    # remainder includes selected paths, provenance, counts and column names.
    if (any(len(_json_bytes(row)) + 1 > 160 for row in result['ledger'])
            or any(len(_json_bytes(day)) + 1 > 13 for day in result['groups'])
            or len(_json_bytes({k: v for k, v in result.items() if k not in {'ledger', 'groups'}})) > MAX_OTHER_BYTES
            or len(_json_bytes(result)) > MAX_RESULT_BYTES):
        raise ValueError('path_result_limit')


def historical_path_report(query, cutoff):
    """Use the complete same-source daily prefix; reject an unusable query.

    Ledger starts index the single date mapping. Each method cell is either
    null (invalid), [one-based selected rank, null], [null, overlapping selected
    start], or [null, null] (valid remaining). Invalid slots are never removed.
    """
    strict_date(cutoff, 'invalid_cutoff')
    rows = [*query.get('rows', ()), *query.get('unlocated', ())]
    if len(rows) > MAX_RESEARCH_ROWS:
        raise ValueError('research_row_limit')
    selection = query.get('selection') or {}
    if selection.get('cutoff') is not None and selection['cutoff'] != cutoff:
        raise ValueError('research_cutoff_mismatch')
    identity = symbol_identity(query)
    source_failed = _checks(query.get('batch_checks', ()))
    rejection = source_rejection(query)
    if rejection:
        raise ValueError(rejection)
    if source_failed - _QUANTITY:
        raise ValueError('path_source_check_failed')
    nonprice_failures = {name: 1 for name in source_failed & _QUANTITY}
    failed_by_day = {}
    selected, raw_by_day = [], {}
    for row in rows:
        day = _source_date(row)
        if day is None:
            raise ValueError('path_unreadable_date')
        if day <= cutoff:
            selected.append(row)
            raw_by_day[day] = (row.get('values') or {}).get('close')
            failed = _checks(row.get('checks', ()))
            failed_by_day.setdefault(day, set()).update(failed)
            for name in failed & _QUANTITY:
                nonprice_failures[name] = nonprice_failures.get(name, 0) + 1
    prefix = dict(query, rows=selected, unlocated=[], selection=dict(selection, cutoff=cutoff))
    bars = daily_bars(prefix)
    for bar in bars:
        bar['reason'] = bar['reason'] or _failed_group_reason(failed_by_day[bar['date']])
    if not bars or bars[-1]['date'] != cutoff:
        raise ValueError('path_cutoff_missing')
    if len(bars) < STEPS + 1:
        raise ValueError('path_history_insufficient')
    query_start = len(bars) - STEPS - 1
    if any(bar['reason'] for bar in bars[query_start:]):
        raise ValueError('path_query_invalid')
    units = [_units(bar['close']) if bar['reason'] is None else None for bar in bars]
    raw_prices = [str(raw_by_day[bar['date']]) if bar['reason'] is None else None for bar in bars]
    q_units = units[query_start:]
    scores, ledger = [], []
    # W_end < Q_start, including the shared-endpoint prohibition.
    for start in range(max(0, query_start - STEPS)):
        failed = next((i for i in range(start, start + STEPS + 1) if bars[i]['reason']), None)
        reason = bars[failed]['reason'] if failed is not None else None
        score = None if reason else _scores(q_units, units[start:start + STEPS + 1])
        scores.append(score)
        ledger.append([start, reason, _display(score[0]) if score else None,
                       _display(score[1]) if score else None, None, None, None, failed])
    selections = {method: _select(scores, method) for method in _METHODS}
    counts = {}
    valid = sum(score is not None for score in scores)
    for column, method in enumerate(_METHODS, 4):
        chosen = selections[method]
        overlap_count = 0
        for start, score in enumerate(scores):
            if score is None:
                continue
            if start in chosen:
                ledger[start][column] = [chosen.index(start) + 1, None]
            else:
                overlap = next((value for value in chosen if abs(start - value) <= STEPS), None)
                ledger[start][column] = [None, overlap]
                overlap_count += overlap is not None
        counts[method] = dict(total=len(scores), valid=valid, invalid=len(scores) - valid,
                              selected=len(chosen), overlap_excluded=overlap_count,
                              remaining=valid - len(chosen) - overlap_count)
    # Insertion order preserves path, endpoint, then recent selections; shared
    # windows are expanded once, while each method retains its independent IDs.
    unique = dict.fromkeys(start for method in _METHODS for start in selections[method])
    result = dict(identity=identity, cutoff=cutoff, parameters=dict(PARAMETERS),
                  groups=[bar['date'] for bar in bars],
                  query=_window(query_start, bars, units, raw_prices, q_units, (Fraction(0), Fraction(0))),
                  windows=[_window(start, bars, units, raw_prices, q_units, scores[start]) for start in unique],
                  selections=selections, counts=counts, ledger_columns=list(LEDGER_COLUMNS), ledger=ledger,
                  qualification='conditional_source_close_paths',
                  unknowns=['adjustment', 'corporate_actions', 'calendar', 'coverage', 'bar_closure', 'known_at'],
                  selection_rule='three_greedy_nonoverlapping_windows_not_global_optimum',
                  ranking_rule='exact_distance_then_earlier_start',
                  difference_direction='query_minus_candidate',
                  display_policy='rounded_display_exact_ranking')
    result['nonprice_check_failures'] = dict(sorted(nonprice_failures.items()))
    _validate_result_budget(result)
    return result
