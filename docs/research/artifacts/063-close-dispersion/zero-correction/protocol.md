# Zero-inclusive boundary correction: pre-execution protocol

2026-10-13. This new synthetic protocol precedes its execution and does not replace the earlier positive-only protocol or original outputs.

Source review: candle_geometry.ohlc_values and true_range._price reject values below zero, allowing zero. In contrast research_series._bar rejects values at or below zero. The repository has different eligibility contracts. The earlier audit's positive-only domain is narrower than the channel/geometry contract and must not be described as universal source eligibility. No product code or eligibility will change in this study.

Fix n=20 and integer lattice u=price*10^18. For source-domain boundary demonstration accept 0<=u<=10^38-1; reject negative and 10^38. Check boundary inputs -1,0,1,10^38-1,10^38. This is an explicit lattice predicate, not execution of the Decimal parser or product adapter.

Freeze five exact fixtures: twenty zeros; ten alternating zero/one-price values (lattice 0 and10^18); ten alternating zero/minimum-positive-price values (lattice0 and1); ten alternating minimum/maximum-positive lattice values (1 and10^38-1); nineteen zeros plus one unit price(lattice10^18).

For each window calculate S=sum(u), Q=sum(u*u), D=20Q-S*S. Independently sum all190 pair differences squared and require equality to D. Require nonnegative D, D=0 iff constant, D.bit_length<=262; exact mean S/(20*10^18), population variance D/(400*10^36). Compare the latter also with an independently centered Fraction calculation. Test negative derived lower envelope using exact condition S*S<4*D; zero must give coincident zero bands, not source rejection. Square-root display rounding and actual adapter behavior remain untested.

Expected exact invariants: all-zero D=0; alternating0/1 price variance1/4; alternating0/min variance1/(4*10^36); nineteen0+one1 price variance19/400 and negative lower envelope. Negative or out-of-range source values are not inserted into eligible windows. No parameter search, market data, Store, product module import, dependencies, benchmarks or source writes. One original run of this new correction script; publication reruns must be logged separately.
