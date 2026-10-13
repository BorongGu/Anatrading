# Independent frozen protocol, 2026-10-13 19:46 UTC

This is a NEW protocol. The prior 18:47 report and unexecuted protocol are unavailable in this executor and have not been read, replaced, or claimed as executed. No market data is involved. Repository is read-only through the GitHub connector; experiments use Python standard library and files only in this directory.

## Question and fixed convention
Does a 20-position, current-close-inclusive, population dispersion envelope add a distinct descriptive measurement over a 20-position close extrema channel? No forecasting, profitable trading, calibrated coverage, noise identification, or cross-symbol ranking claim is tested. Fixed 20 and multiplier 2 throughout; no parameter search or threshold tuning.

Each eligible window consists of exactly the current and prior 19 supplied positions. If any value is missing/nonfinite, return unavailable; never compress missing positions or fill gaps. Fewer than 20 positions: unavailable. Missing timestamps entirely absent from input require upstream calendar treatment and are outside this arithmetic test. Finalized bar data assumed; no intrabar stability claim.

Output: mean, population sigma, lower=mean-2sigma, upper=mean+2sigma. Zero sigma gives coincident bounds, not failure. Percent-b undefined when sigma=0; fractional BandWidth undefined when mean<=0. These optional ratios are not needed to establish value and are excluded from initial minimal design.

## Arithmetic references and alternatives
Reference exact mean and variance use Fraction.from_float for each supplied binary64 value; reference sigma uses 100-digit Decimal square root of exact variance. Test three independent arithmetic routes: naive E[x²]-E[x]²; ordinary two-pass fsum centered on rounded unshifted mean; candidate per-window shifted/scaled two-pass using first value as anchor, maximum absolute shifted delta as scale, fsum normalized deltas and squared centered deltas, and sigma=scale*sqrt(sum/n). No sliding subtract/add variance state. Population variance is sigma² only when representable; sigma is primary to avoid gratuitous underflow/overflow. Report numerical errors, do not silently clamp negatives or tiny dispersion to zero.

Acceptance fixed before execution: candidate sigma relative error <=64 binary64 epsilon against exact sigma for each finite nonzero reference, zero exactly for constant data. Candidate mean error <=2 ulps of rounded exact mean (absolute 2*ulp(0) at exact zero). Finite bounds required when mathematically representable in binary64. Prefix recomputation must equal full-run corresponding outputs exactly for every prefix. Missing-containing windows must all be unavailable and recovery occurs exactly 20 positions after missing point.

## Frozen deterministic fixtures
- Constant: 60 closes at 100; zero: 40 closes at 0.
- Alternating: 60 closes 99,101 repeated.
- Sparse extremes: 60 closes formed by [99,101]+18*[100], repeated three times. Same exact 20-window range and mean as alternating, different occupancy.
- Level shift: 30 closes100 followed by30 closes120. Inspect shift positions30,39,49 and departure edge.
- Linear trend: 60 closes100+i, demonstrates dispersion without stochastic noise.
- Tiny variance: 60 closes 1+(i mod2)*2^-40.
- Large offset: 60 closes 1e12+(i mod2)*2^-12.
- Tiny magnitude: 60 closes (1+(i mod2))*1e-200; variance underflows binary64 but sigma representable.
- Large magnitude: 60 closes (1+(i mod2))*1e200; variance overflows binary64 but sigma and bounds representable.
- Missing: alternating fixture with index25=None; repeat for NaN and +infinity. Inspect eligible outputs24,25,44,45.

For each finite fixture compare the last20 close min/max channel, mean, sigma, envelope width and available window counts. Compare trend and levelshift interpretation to simple extrema channel. Repo-specific ATR/EWMA comparisons require independently verified definitions and are qualitative unless all input conventions are available.

## Decision rule
Recommend a narrow descriptive build only if numerical/reference/causal tests pass and fixtures establish information not recoverable from the extrema channel alone, and current repository contains no equivalent output. If distinctness cannot be verified, or practical usefulness is merely another trading signal, defer/no-build. Never claim superiority to TradingView or infer alpha from synthetic tests. Stop at report and minimal design; no repository implementation.
