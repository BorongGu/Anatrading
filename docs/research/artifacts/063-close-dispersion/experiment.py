import math,json,sys
from fractions import Fraction
from decimal import Decimal,localcontext
from pathlib import Path
P=Path(__file__).parent
N=20
fixtures={'constant':[100.]*60,'zero':[0.]*40,'alternating':[99.,101.]*30,'sparse_extremes':([99.,101.]+[100.]*18)*3,'level_shift':[100.]*30+[120.]*30,'linear_trend':[100.+i for i in range(60)],'tiny_variance':[1.+(i%2)*2**-40 for i in range(60)],'large_offset':[1e12+(i%2)*2**-12 for i in range(60)],'tiny_magnitude':[(1+i%2)*1e-200 for i in range(60)],'large_magnitude':[(1+i%2)*1e200 for i in range(60)]}
def ref(w):
 q=list(map(Fraction.from_float,w)); m=sum(q)/N; v=sum((x-m)**2 for x in q)/N
 with localcontext() as c:
  c.prec=100
  sd=(Decimal(v.numerator)/Decimal(v.denominator)).sqrt()
 return float(m),float(sd)
def candidate(w):
 a=w[0]; ds=[x-a for x in w]; s=max(map(abs,ds))
 if s==0:return (a,0.,a,a)
 z=[d/s for d in ds]; zm=math.fsum(z)/N
 m=a+s*zm; sd=s*math.sqrt(math.fsum((x-zm)**2 for x in z)/N)
 return (m,sd,m-2*sd,m+2*sd)
def allout(xs):
 out=[]
 for i in range(len(xs)):
  w=xs[max(0,i-N+1):i+1]
  out.append(candidate(w) if len(w)==N and all(x is not None and math.isfinite(x) for x in w) else None)
 return out
res={}; failures=[]
for name,xs in fixtures.items():
 outs=allout(xs); maxerr=0.; naive_bad=0; twopass_err=0.
 for i,o in enumerate(outs):
  if o is None:continue
  w=xs[i-N+1:i+1]; rm,rs=ref(w); m,sd,lo,hi=o
  err=abs(sd-rs)/rs if rs else abs(sd)
  maxerr=max(maxerr,err)
  if err>64*sys.float_info.epsilon:failures.append([name,i,'sigma',err])
  if abs(m-rm)>2*math.ulp(rm):failures.append([name,i,'mean',m,rm])
  if not all(map(math.isfinite,o)):failures.append([name,i,'nonfinite'])
  try:
   mn=sum(w)/N; vn=sum(v*v for v in w)/N-mn*mn
   sn=math.sqrt(vn); ne=abs(sn-rs)/rs if rs else abs(sn)
   if not math.isfinite(sn) or ne>64*sys.float_info.epsilon:naive_bad+=1
  except (OverflowError,ValueError):naive_bad+=1
  try:
   mt=math.fsum(w)/N; st=math.sqrt(math.fsum((v-mt)**2 for v in w)/N)
   te=abs(st-rs)/rs if rs else abs(st)
   twopass_err=max(twopass_err,te)
  except OverflowError:twopass_err=float('inf')
 for k in range(len(xs)+1):
  if allout(xs[:k])!=outs[:k]:failures.append([name,k,'prefix'])
 o=outs[-1];w=xs[-20:]
 res[name]={'valid_windows':sum(v is not None for v in outs),'max_candidate_sigma_relative_error':maxerr,'naive_bad_windows':naive_bad,'ordinary_two_pass_max_sigma_relative_error':str(twopass_err),'last':{'mean':o[0],'sigma':o[1],'lower':o[2],'upper':o[3],'close_min':min(w),'close_max':max(w)}}
 if name=='level_shift':res[name]['selected']={str(i):outs[i] for i in [29,30,39,48,49,50]}
for missing in [None,float('nan'),float('inf')]:
 xs=fixtures['alternating'].copy();xs[25]=missing;o=allout(xs)
 wrong=[i for i,v in enumerate(o) if (v is None)!=(i<19 or 25<=i<=44)]
 if wrong:failures.append(['missing',str(missing),wrong])
 for k in range(len(xs)+1):
  if allout(xs[:k])!=o[:k]:failures.append(['missing',str(missing),k,'prefix'])
 res['missing_'+str(missing)]={'valid_windows':sum(x is not None for x in o),'selected':{str(i):o[i] for i in [24,25,44,45]}}
r={'protocol_sha256':'5dcdb7d5e2daa6ca9be449478672e96b0e8ce9c25c9f221fcbef4e5bb572f57c','failures':failures,'fixtures':res}
(P/'results.json').write_text(json.dumps(r,indent=2,allow_nan=False));print(json.dumps(r,indent=2,allow_nan=False))
