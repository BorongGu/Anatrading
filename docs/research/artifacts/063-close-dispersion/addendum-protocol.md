# Separately frozen source-domain addendum, 2026-10-13 19:48 UTC

Original experiment is complete and remains unchanged. GitHub exact-ref review established Decimal(38,18) source inputs, so binary64 fixtures do not validate source preservation. No threshold changes or replacing failed inputs. This new experiment checks that specific concern.

Freeze four exact source cases of20 closes: alternating 1 /1.000000000000000001; alternating10000000000000000000 /10000000000000000001; alternating0.000000000000000001 /0.000000000000000002; sparse99/101/18*100. All in domain. Compare exact Fraction(str) variance vs float conversion and an integer-lattice formula: set u=close*10^18 exactly, D=20*sum(u²)−sum(u)²; exact mean=sum(u)/(20*10^18), variance=D/(400*10^36). Require exact equality to Fraction reference, D>=0, constant sourcesD=0. Decimal square root output is approximate; do not call it exact. This validates algebra, not repository integration or its chosen numeric rounding contract.

Also compare last query of frozen alternating/sparse60-point fixtures against an exact proxy of existing prior20 source-date high/low channel, assigning flat positiveOHLC=close to every syntheticdate. Unlike original simpleclose baseline, this prior20 excludes currentposition. Require identical bounds99/101 but different proposed current20 sigma. Do not import Store or repository modules.
