"""One bounded synthetic validation; deliberately no repository imports/models."""
import hashlib
import itertools
import json
import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from math import gcd
from pathlib import Path

ROOT = Path(__file__).parent
PROTOCOL = 'ec987441166106bc93ce9e4846cd14b8017b13b049c845a1bb36a5f108da78d1'
assert hashlib.sha256((ROOT/'protocol.txt').read_bytes()).hexdigest() == PROTOCOL

def oracle(closes, origin, cutoff):
    window = closes[:cutoff+1][origin:origin+6]
    if cutoff < origin+5 or len(window) != 6:
        return None
    parsed = []
    for value in window:
        if not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?', value):
            return None
        whole, _, decimal = value.partition('.')
        integer = int(whole+decimal)
        if integer <= 0:
            return None
        parsed.append((integer, len(decimal)))
    scale = max(item[1] for item in parsed)
    numbers = [n*10**(scale-s) for n,s in parsed]
    n, d = max(0, numbers[0]-min(numbers[1:])), numbers[0]
    common = gcd(n,d)
    return (n//common, d//common)

def reference(closes, origin, cutoff):
    if cutoff < origin+5 or len(closes) <= origin+5:
        return None
    values = []
    for text in closes[origin:origin+6]:
        if type(text) is not str:
            return None
        try:
            value = Decimal(text)
        except InvalidOperation:
            return None
        if not value.is_finite() or value <= 0:
            return None
        values.append(Fraction(value))
    result = max([Fraction(0)] + [1-price/values[0] for price in values[1:]])
    return result.numerator, result.denominator

def record(prefix, origin, cutoff, supplied_prediction):
    # This accepts only a prefix; no access to labels or full-series qualification.
    if cutoff != origin or len(prefix) != origin+1:
        raise ValueError('origin_cutoff_mismatch')
    raw = json.dumps(prefix, separators=(',',':')).encode()
    return json.dumps(dict(origin=origin, input_cutoff=cutoff,
        prefix_sha256=hashlib.sha256(raw).hexdigest(),
        prediction=supplied_prediction, qualification='synthetic_only'),
        sort_keys=True, separators=(',',':')).encode()

checks = {}
def check(name, condition):
    assert condition, name
    checks[name] = checks.get(name, 0)+1

fixtures = [(['100','101','102','103','104','105'],(0,1)),
 (['100','99','98','97','96','95'],(1,20)),
 (['100','105','90','105','100','110'],(1,10)),
 (['100','99',None,'101','102','103'],None),
 (['100']*6,(0,1)),
 (['100','120','110','115','118','119'],(0,1)),
 (['0.1','0.099','0.098','0.097','0.096','0.095'],(1,20))]
for values, expected in fixtures:
    check('fixed_fixtures', oracle(values,0,5) == reference(values,0,5) == expected)
for values in itertools.product(['90','100','110'], repeat=6):
    check('exhaustive_arithmetic', oracle(values,0,5) == reference(values,0,5))
for bad in [None,'0','-1','NaN','Infinity',True,100.0]:
    for i in range(6):
        values = ['100']*6
        values[i] = bad
        check('invalid_slot', oracle(values,0,5) is reference(values,0,5) is None)
for cutoff in range(5):
    check('immature_cutoff', oracle(fixtures[1][0],0,cutoff) is reference(fixtures[1][0],0,cutoff) is None)
for length in range(6):
    check('missing_tail', oracle(['100']*length,0,5) is reference(['100']*length,0,5) is None)
values = ['80','85']+fixtures[1][0]
check('nonzero_origin', oracle(values,2,7) == reference(values,2,7) == (1,20))
# Persist external prediction fixture before connecting any label to this origin.
base = ['100']*6
saved = record(base[:1],0,0,'1/20')
(ROOT/'origin_record.json').write_bytes(saved)
changed_labels = 0
for offset in range(1,6):
    for replacement in ['90','110',None]:
        mutated = base.copy()
        mutated[offset] = replacement
        check('saved_record_unchanged', (ROOT/'origin_record.json').read_bytes() == saved)
        check('prefix_reconstruction_unchanged', record(mutated[:1],0,0,'1/20') == saved)
        check('mutated_reference_agrees', oracle(mutated,0,5) == reference(mutated,0,5))
        changed_labels += oracle(mutated,0,5) != oracle(base,0,5)
check('future_can_change_label', changed_labels == 10)
for appended in ['1','1000',None]:
    check('fixed_cutoff_after_append', oracle(fixtures[1][0]+[appended],0,5) == (1,20))
try:
    record(base,0,5,'1/20')
except ValueError as error:
    check('reject_future_origin_input', str(error) == 'origin_cutoff_mismatch')
else:
    raise AssertionError('future input accepted')
# Distinguish three targets on the exact same synthetic path.
path = list(map(Fraction, fixtures[2][0]))
peak_drawdown = max(1-path[j]/max(path[:j+1]) for j in range(len(path)))
check('target_distinction', (oracle(fixtures[2][0],0,5), path[-1]/path[0]-1, peak_drawdown) == ((1,10), Fraction(1,10), Fraction(1,7)))
result = dict(status='PASS_SYNTHETIC_LABEL_ONLY',protocol_sha256=PROTOCOL,
    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    checks=checks, total_assertions=sum(checks.values()), changed_mutation_labels=changed_labels,
    fixed_results=[dict(input=v,result=e) for v,e in fixtures],
    limits=['no_predictor_test','no_real_data','no_PIT_claim','no_product_tests','no_new_model','no_publication'])
(ROOT/'result.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
