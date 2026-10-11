"""Independent synthetic checks for fixed-cutoff historical path retrieval.

The oracle uses direct Fraction ratios and full sorting, deliberately avoiding
the implementation's common-denominator integer kernel and repeated min scans.
No market files, network access, or predictive-effect claims are involved.
"""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction

import pytest


def _fixture(prices):
    rows = []
    for i, price in enumerate(prices):
        day = (date(2025, 1, 1) + timedelta(days=i)).isoformat()
        text = str(price) if price is not None else None
        rows.append(dict(ordinal=i + 1, label=day, tokens={"source_date": day},
                         values=dict(open=text, high=text, low=text, close=text), checks=[]))
    return dict(snapshot_id="a" * 64, query_id="b" * 64, batch_id="c" * 64,
                metadata=dict(period="1d", source_code="600000.SH"),
                manifest=dict(qualification="synthetic_test_only"), batch_checks=[],
                selection=dict(cutoff=rows[-1]["label"] if rows else "2025-01-01"),
                rows=rows, unlocated=[], counts=dict(batch_unlocated_rows=0))


def _distance(left, right):
    l, r = [Fraction(str(v)) for v in left], [Fraction(str(v)) for v in right]
    differences = [x / l[0] - y / r[0] for x, y in zip(l[1:], r[1:], strict=True)]
    return sum((x * x for x in differences), Fraction()) / 20


def _oracle(prices):
    query = prices[-21:]
    scores = {}
    for start in range(max(0, len(prices) - 41)):
        candidate = prices[start:start + 21]
        if any(p is None for p in candidate):
            continue
        scores[start] = (_distance(query, candidate),
                         abs(Fraction(str(query[-1])) / Fraction(str(query[0]))
                             - Fraction(str(candidate[-1])) / Fraction(str(candidate[0]))))
    selections = {}
    for method, key in (("path", lambda i: (scores[i][0], i)),
                        ("endpoint", lambda i: (scores[i][1], i)),
                        ("recent", lambda i: -i)):
        picked = []
        for start in sorted(scores, key=key):
            if all(abs(start - previous) > 20 for previous in picked):
                picked.append(start)
                if len(picked) == 3:
                    break
        selections[method] = picked
    return scores, selections


def _shown(value):
    with localcontext(Context(prec=12, rounding=ROUND_HALF_EVEN)):
        return format(Decimal(value.numerator) / Decimal(value.denominator), ".11e")


def _report(query):
    from anatrading.historical_path_retrieval import historical_path_report
    return historical_path_report(query, query["selection"]["cutoff"])


def _assert_oracle(prices, result):
    scores, selections = _oracle(prices)
    assert result["selections"] == selections
    for row in result["ledger"]:
        start, reason, distance, endpoint = row[:4]
        statuses, first_invalid = row[4:7], row[7]
        if start not in scores:
            assert reason is not None and distance is None and endpoint is None
            assert statuses == [None, None, None]
            assert first_invalid == next(i for i in range(start, start + 21) if prices[i] is None)
            continue
        assert reason is None and first_invalid is None
        # Do not compare the display by binary floats. It is a rounded rendering
        # of an independently computed exact rational, not a sorting input.
        assert Decimal(distance) == Decimal(_shown(scores[start][0]))
        assert Decimal(endpoint) == Decimal(_shown(scores[start][1]))
        for method, status in zip(("path", "endpoint", "recent"), statuses, strict=True):
            picked = selections[method]
            if start in picked:
                assert status == [picked.index(start) + 1, None]
            else:
                first = next((p for p in picked if abs(start - p) <= 20), None)
                assert status == [None, first]
    for method, picked in selections.items():
        excluded = sum(start not in picked and any(abs(start - p) <= 20 for p in picked)
                       for start in scores)
        total = max(0, len(prices) - 41)
        assert result["counts"][method] == dict(total=total, valid=len(scores),
            invalid=total - len(scores), selected=len(picked), overlap_excluded=excluded,
            remaining=len(scores) - len(picked) - excluded)
    query_values = [Fraction(str(v)) for v in prices[-21:]]
    query_relative = [v / query_values[0] - 1 for v in query_values]
    for window in [result["query"], *result["windows"]]:
        start = window["start_index"]
        values = [Fraction(str(v)) for v in prices[start:start + 21]]
        relative = [v / values[0] - 1 for v in values]
        differences = [q - v for q, v in zip(query_relative, relative, strict=True)]
        assert window["ordinals"] == list(range(start + 1, start + 22))
        assert [Decimal(v) for v in window["relative_path"]] == [Decimal(_shown(v)) for v in relative]
        assert [Decimal(v) for v in window["differences"]] == [Decimal(_shown(v)) for v in differences]
        maximum = max(abs(v) for v in differences)
        witness = window["max_point_difference"]
        assert abs(differences[witness["step"]]) == maximum
        assert Decimal(witness["value"]) == Decimal(_shown(maximum))
        # Exhaustively enumerate every peak/trough pair, unlike the production
        # running-peak recurrence, and validate the supplied witness itself.
        drawdown = max(Fraction(0), *(1 - values[j] / values[i]
                        for i in range(21) for j in range(i, 21)))
        witness = window["max_drawdown"]
        peak, trough = witness["peak_step"], witness["trough_step"]
        assert 0 <= peak <= trough <= 20
        assert 1 - values[trough] / values[peak] == drawdown
        assert Decimal(witness["value"]) == Decimal(_shown(drawdown))


def test_constant_series_has_three_distinct_greedy_sets_and_exhaustive_ledger():
    prices = ["100"] * 125
    query = _fixture(prices)
    before = deepcopy(query)
    result = _report(query)
    _assert_oracle(prices, result)
    assert result["selections"] == dict(path=[0, 21, 42], endpoint=[0, 21, 42], recent=[83, 62, 41])
    assert all(c == dict(total=84, valid=84, invalid=0, selected=3,
                        overlap_excluded=60, remaining=21) for c in result["counts"].values())
    assert query == before


@pytest.mark.parametrize("length,total", [(21, 0), (41, 0), (42, 1)])
def test_query_and_candidate_cannot_share_even_one_endpoint(length, total):
    prices = ["10"] * length
    result = _report(_fixture(prices))
    _assert_oracle(prices, result)
    assert result["counts"]["path"]["total"] == total


def test_full_source_slots_are_not_compressed_after_invalid_prices():
    prices = [str(100 + (i * 7) % 19) for i in range(125)]
    prices[40] = None
    result = _report(_fixture(prices))
    _assert_oracle(prices, result)
    assert result["counts"]["path"]["invalid"] == 21
    assert [row[0] for row in result["ledger"] if row[1] is not None] == list(range(20, 41))


def test_duplicate_group_invalidates_its_full_windows_and_never_adds_a_step():
    prices = [str(100 + (i * 7) % 19) for i in range(125)]
    query = _fixture(prices)
    duplicate = deepcopy(query["rows"][40])
    duplicate["ordinal"] = 126
    query["rows"].append(duplicate)
    prices[40] = None  # The oracle keeps the original slot, marked unusable.
    result = _report(query)
    _assert_oracle(prices, result)
    assert len(result["groups"]) == 125
    assert all(row[1] == "duplicate_date" for row in result["ledger"] if row[1] is not None)


def test_input_order_and_price_units_do_not_change_exact_rankings():
    prices = [100 + (i * 7) % 19 for i in range(125)]
    query = _fixture(prices)
    original = _report(query)
    query["rows"].reverse()
    assert _report(query) == original
    scaled = _report(_fixture([p * 10 for p in prices]))
    assert scaled["selections"] == original["selections"]
    assert scaled["counts"] == original["counts"]
    assert scaled["ledger"] == original["ledger"]


def test_close_scores_with_equal_twelve_digit_displays_still_rank_exactly():
    worse = ["100"] + ["110.000000000000000002"] * 20
    better = ["100"] + ["110.000000000000000001"] * 20
    prices = worse + [None] + better + [None] + ["100"] * 21
    result = _report(_fixture(prices))
    _assert_oracle(prices, result)
    valid = [row for row in result["ledger"] if row[1] is None]
    assert [row[0] for row in valid] == [0, 22]
    assert valid[0][2] == valid[1][2] and valid[0][3] == valid[1][3]
    assert result["selections"]["path"] == [22, 0]
    assert result["selections"]["endpoint"] == [22, 0]


def test_known_future_bad_label_and_batch_counter_do_not_rewrite_fixed_cutoff():
    query = _fixture([str(100 + (i * 11) % 17) for i in range(104)])
    before = _report(query)
    # A malformed public label with a recoverable later source date is known
    # future data, despite the batch's global unlocated count increasing.
    query["unlocated"].append(dict(ordinal=105, label=None,
        tokens=dict(source_date="2050-01-01"), values=dict(close="bad"), checks=[]))
    query["counts"]["batch_unlocated_rows"] = 1
    query["rows"].append(dict(ordinal=106, label="2050-01-02", tokens={}, values={}))
    assert _report(query) == before


def test_genuinely_unreadable_date_cannot_be_assumed_future():
    query = _fixture(["10"] * 70)
    query["unlocated"].append(dict(ordinal=71, label=None, tokens={}, values={}))
    with pytest.raises(ValueError, match="path_unreadable_date"):
        _report(query)


def test_unknown_failed_source_check_cannot_silently_gain_search_qualification():
    query = _fixture(["10"] * 70)
    query["batch_checks"] = [dict(name="unrecognized_source_integrity_check", outcome="fail")]
    with pytest.raises(ValueError, match="path_source_check_failed"):
        _report(query)


def test_missing_invalid_and_short_cutoffs_never_roll_back():
    query = _fixture(["10"] * 70)
    query["selection"]["cutoff"] = "2050-01-01"
    with pytest.raises(ValueError, match="path_cutoff_missing"):
        _report(query)
    query = _fixture(["10"] * 69 + [None])
    with pytest.raises(ValueError, match="path_query_invalid"):
        _report(query)
    with pytest.raises(ValueError, match="path_history_insufficient"):
        _report(_fixture(["10"] * 20))


def test_distances_and_extreme_domain_survive_host_decimal_context_changes():
    small = "0.000000000000000001"
    large = "99999999999999999999.999999999999999999"
    prices = [small if i % 3 else large for i in range(88)]
    query = _fixture(prices)
    expected = _report(query)
    _assert_oracle(prices, expected)
    with localcontext() as context:
        context.prec, context.Emax, context.Emin = 3, 9, -9
        context.rounding = "ROUND_DOWN"
        assert _report(query) == expected
    # Independently check the unreduced numerator/denominator boundary rather
    # than relying on the implementation's already-reduced Fraction checks.
    upper = 10 ** 38 - 1
    numerator = 20 * (upper * upper - 1) ** 2
    denominator = 20 * upper ** 4
    assert numerator.bit_length() <= 512 and denominator.bit_length() <= 512
    assert (numerator * denominator).bit_length() <= 1024


def test_no_automatic_adjustment_of_mechanical_or_economic_price_jumps():
    # Identical observed paths cannot identify a split versus an actual fall.
    candidate = ["100"] * 10 + ["50"] * 11
    prices = candidate + [None] + candidate
    result = _report(_fixture(prices))
    _assert_oracle(prices, result)
    window = result["windows"][0]
    assert window["prices"] == candidate
    assert Decimal(window["max_drawdown"]["value"]) == Decimal("0.5")
    assert 0 <= window["max_drawdown"]["peak_step"] < 10
    assert 10 <= window["max_drawdown"]["trough_step"] <= 20
    assert Decimal(window["distance"]) == 0


def test_source_gaps_and_equivalent_decimal_spellings_are_preserved():
    prices = ["1E-18", "0.0000000000000000010", "10.0000000000000000000"] * 21
    query = _fixture(prices)
    for index, row in enumerate(query["rows"]):
        row["label"] = row["tokens"]["source_date"] = (
            date(2025, 1, 1) + timedelta(days=index * 3)).isoformat()
    query["selection"]["cutoff"] = query["rows"][-1]["label"]
    result = _report(query)
    _assert_oracle(prices, result)
    assert result["query"]["calendar_days"] == 60
    assert result["query"]["prices"] == prices[-21:]
    assert all(window["calendar_days"] == 60 for window in result["windows"])
    assert "calendar" in result["unknowns"]
