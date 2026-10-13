"""Original standalone zero-inclusive synthetic correction, standard library only."""
from fractions import Fraction
from pathlib import Path
import hashlib
import json

P = Path(__file__).parent
N = 20
SCALE = 10**18
MAX = 10**38 - 1
fixtures = {
    'all_zero': [0] * N,
    'alternating_zero_unit_price': [0, SCALE] * 10,
    'alternating_zero_minimum': [0, 1] * 10,
    'alternating_minimum_maximum': [1, MAX] * 10,
    'nineteen_zero_one_unit_price': [0] * 19 + [SCALE],
}
results = {}
for name, values in fixtures.items():
    assert len(values) == N and all(0 <= v <= MAX for v in values)
    s = sum(values)
    q = sum(v * v for v in values)
    d = N * q - s * s
    pair = sum((values[i] - values[j])**2 for i in range(N) for j in range(i + 1, N))
    prices = [Fraction(v, SCALE) for v in values]
    mean = sum(prices) / N
    centered_variance = sum((v - mean)**2 for v in prices) / N
    variance = Fraction(d, N*N*SCALE*SCALE)
    assert d == pair and d >= 0 and d.bit_length() <= 262
    assert (d == 0) == all(v == values[0] for v in values)
    assert variance == centered_variance and mean == Fraction(s, N*SCALE)
    results[name] = dict(mean=str(mean), variance=str(variance), D=str(d),
                         D_bits=d.bit_length(), pairwise_equal=d == pair,
                         centered_fraction_equal=variance == centered_variance,
                         lower_negative=s*s < 4*d, zero_coincident_bounds=d == 0 and s == 0)
assert results['all_zero']['variance'] == '0'
assert results['alternating_zero_unit_price']['variance'] == '1/4'
assert results['alternating_zero_minimum']['variance'] == str(Fraction(1, 4*10**36))
assert results['nineteen_zero_one_unit_price']['variance'] == '19/400'
assert results['nineteen_zero_one_unit_price']['lower_negative']
report = dict(protocol_sha256=hashlib.sha256((P / 'protocol.md').read_bytes()).hexdigest(),
              boundary=[dict(lattice=str(v), accepted=0 <= v <= MAX) for v in [-1, 0, 1, MAX, MAX + 1]],
              fixtures=results,
              limitations=['lattice predicate only; no product Decimal parser or adapter',
                           'no square-root display rounding test',
                           'no market, Store, performance or product test'])
(P / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
