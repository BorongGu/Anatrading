from fractions import Fraction
from decimal import Decimal,localcontext
from pathlib import Path
import json, math
P=Path(__file__).parent
cases={'unit_collision':['1','1.000000000000000001']*10,'large_offset_collision':['10000000000000000000','10000000000000000001']*10,'minimum_scale':['0.000000000000000001','0.000000000000000002']*10,'sparse':['99','101']+['100']*18,'constant':['100']*20}
r={};fail=[]
for name,ss in cases.items():
 q=list(map(Fraction,ss));mean=sum(q)/20;var=sum((x-mean)**2 for x in q)/20
 u=[x*10**18 for x in q];assert all(x.denominator==1 for x in u);u=[x.numerator for x in u];S=sum(u);Q=sum(x*x for x in u);D=20*Q-S*S;iv=Fraction(D,400*10**36)
 assert D>=0 and iv==var and Fraction(S,20*10**18)==mean
 with localcontext() as ctx:
  ctx.prec=100
  sd=(Decimal(var.numerator)/Decimal(var.denominator)).sqrt()
 fs=list(map(float,ss));fm=math.fsum(fs)/20;fv=math.fsum((x-fm)**2 for x in fs)/20
 r[name]={'exact_variance':str(var),'integer_formula_equal':iv==var,'D_bits':D.bit_length(),'sigma_decimal100':str(sd),'float_input_sigma':math.sqrt(fv),'source_distinct_values':len(set(ss)),'float_distinct_values':len(set(fs))}
alt=[99,101]*30;sparse=([99,101]+[100]*18)*3
r['existing_channel_proxy']={'qualification':'synthetic flat valid positiveOHLC with consecutive source dates; no production import','alternating_prior20':[min(alt[39:59]),max(alt[39:59])],'sparse_prior20':[min(sparse[39:59]),max(sparse[39:59])]}
(P/'source-results.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
