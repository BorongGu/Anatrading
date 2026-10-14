import itertools,json,hashlib
from fractions import Fraction as F
from pathlib import Path
root=Path(__file__).resolve().parent
assert hashlib.sha256((root/'preregister.txt').read_bytes()).hexdigest()=='069c78475ff2df357ed29532161e937f487420c73d8438acc7adf3d77baea3a7'
def filt(y): return [(a+b)/F(2) for a,b in zip(y,y[1:])]
errors={k:[] for k in ['A_raw','A_filter','B_raw','B_filter','rough_raw','rough_filter']}
paths=[]; prefix_ok=True
for signs in itertools.product((-1,1),repeat=8):
    y=[F(100+2*s) for s in signs]; paths.append([int(v) for v in y]); f=filt(y)
    for n in range(2,9): prefix_ok &= filt(y[:n])==f[:n-1]
    for t in range(1,8):
        errors['A_raw'].append((y[t]-100)**2)
        errors['A_filter'].append((f[t-1]-100)**2)
        errors['B_raw'].append((y[t]-y[t])**2)
        errors['B_filter'].append((f[t-1]-y[t])**2)
    for t in range(2,8):
        errors['rough_raw'].append((y[t]-y[t-1])**2)
        errors['rough_filter'].append((f[t-1]-f[t-2])**2)
m={k:sum(v)/len(v) for k,v in errors.items()}
obs_A=json.dumps(paths,separators=(',',':')).encode(); obs_B=json.dumps(paths,separators=(',',':')).encode()
checks={'same_observed_inputs':obs_A==obs_B,'prefix_invariance':prefix_ok,'roughness_reduction_at_least_50pct':m['rough_filter']<=m['rough_raw']/2,'A_mse_reduction_at_least_25pct':m['A_filter']<=m['A_raw']*F(3,4),'B_latent_error_worse':m['B_filter']>m['B_raw']}
out={'kind':'exhaustive_counterexample_not_market_evidence','paths':len(paths),'mse_exact':{k:str(v) for k,v in m.items()},'observations_sha256':hashlib.sha256(obs_A).hexdigest(),'checks':checks,'decision':'COUNTEREXAMPLE_CONFIRMED' if all(checks.values()) else 'COUNTEREXAMPLE_FAILED','scientific_negative_result':'Observed smoothness does not identify whether removed variation was measurement error or genuine value movement. No model promotion.'}
(root/'result.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
