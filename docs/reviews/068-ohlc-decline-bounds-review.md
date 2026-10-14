# Independent design review — OHLC compatible maximum proportional decline

2026-10-14 UTC. Reviewed frozen v1 SHA256 `276d0d3593ec3a1b1b3f2eb43235f87f249ce360736f501ec20a78c2e4f08f95` against read-only main `17c9064794969340fcac1210f82e940d760c8bd4`.

## Decision

**Mathematical design GO. Freeze two small adapter-contract clarifications before implementation GO.** Neither requires a new feature, API, UI, cache, dependency or source acquisition. No mathematical redesign is indicated. The useful increment is an exact answer to how much close-only information omits and what remains unidentified by OHLC; it does not establish TradingView superiority, trading utility, or a new predictive metric.

## Required minimal clarifications

### R1: Meaning and completeness of reason counts

V1 §5.2 promises all completed finite reason checks and counts, while asking to reuse `research_series._source_conflict`. That helper returns immediately on code conflict and suppresses adjustment mismatches and failed adjustment checks on the same row. Independent synthetic invocation confirmed this: code WRONG vs RIGHT, adjustment 2 vs 1, and a failed source_adjustment check yield only `source_identity_conflict`. Iterating all source rows repairs duplicate-group masking but cannot repair simultaneous reasons within one row.

Before coding choose and state one of these bounded contracts:
- Preferred: retain existing helper precedence for primary reason, independently collect all true source identity / adjustment mismatch / failed adjustment predicates across all supplied rows. Count each reason at most once per original source row; report batch rejection separately as a source-level flag/count. Deduplicate repeated checks within a row. Do not alter existing shared helper semantics.
- Smaller alternative: explicitly promise only each row's first classified source reason, and identify suppressed predicates as not evaluated. Do not call that exhaustive conflict counting.

Add a fixed synthetic row with all three conflicts, also hidden inside a duplicate-date group and located outside the selected window. The report must remain unavailable; expected supplementary counts follow the selected contract. This prevents a misleading diagnostic claim, even though either implementation would already reject correctly.

### R2: Duplicate-group evidence representation

V1 §5.2 says duplicate groups keep all original query references; §5.3 freezes member fields without any field holding individual original row references. Freeze what this means so implementation does not invent a potentially large unbudgeted payload.

Smallest suitable resolution: explicitly state original query rows remain unchanged and are recovered through top-level query identity plus source-date grouping; duplicate member has ordinal=null, and the report does not embed individual duplicate-row references. If individual references are required, name their finite schema and include them in the existing 256 KiB whole-result limit, retaining controlled whole-call failure rather than truncation. No need to add references merely for mathematical computation, because every duplicate selected group is unavailable.

## What passed

- For any positive compatible path, visiting L forces prior-max/open-to-L decline, and visiting H before terminal C forces H-to-C decline. OLHC attains the joint lower bound. Any current trough is at least L and any preceding peak at most the cumulative H maximum; OHLC attains upper. The first O initialization and interbar C→O gaps are included. Repeated extrema can be represented by independent slots, so degenerate equality cases retain the attainability construction.
- Close observations are a subsequence of every compatible path; close-only ≤ lower follows directly. Upper<1 follows from strictly positive finite source values. Missing bars invalidate a full-real-interval upper-bound interpretation; v1 prominently preserves this limitation.
- The earliest-trough/earliest-equal-peak scan is correct for positive declines: for a fixed positive trough, the deepest prior peak is the largest price, and strict peak updates retain its earliest location. Strict depth updates retain earliest trough. Zero requires no witness. These labels are proof-path slots, never market timestamps.
- Proportional drop d and logarithmic drop ell satisfy d=1-exp(-ell) for the same pair, so an exact rational percentage value must not be substituted for a log difference. V1 uses the correct proportional object. Its whole-window extremum differs from the paper's rolling current-close object.
- DECIMAL(38,18) conversion through normalized tuple to integer units is valid; accepted strictly positive input gives 1≤u≤10^38−1. Cross products and ambiguity-width denominator stay below 10^76<2^253. Global Decimal context is avoidable. The existing parser's accepted equivalent lexemes need no change.
- 253 bars is a resource boundary, not a statistically calibrated horizon. Core scan constant state and O(m) member storage are coherent. Adapter sorting/storage remain O(n log n)/O(n), with n≤20,000; the existing 16 KiB metadata and 256 KiB serialized result gates must be measured, not treated as RSS guarantees.
- Existing 015 describes single-bar geometry; 050 describes close drawdown episodes; 054 a normalized source-average close path; 060 close threshold reversals; 064 exact dispersion. None provides these OHLC-compatible set extrema. The addition has an identifiable mathematical distinction without establishing end-user value.
- Strict endpoint availability, no adjacent-date fallback, bad selected groups invalidating the whole window, and global source/unknown-position blockers are consistent. Source finality, calendar completeness, economic meaning, historical availability and trusted-query authentication stay unresolved as explicitly stated.

## Independent finite checks

Recorded `CRITERIA.md` before executing `check.py`, neither in product repository. Executed once with exit 0. Enumerated all 20 valid OHLC types on {1,2,3}, all 8,000 ordered three-bar combinations and all 64,000 extremum-order paths. Independent all-prior/later-pairs Fraction oracle matched formula minima/maxima and both designated attainments. 16,000 extremizer scan versus oracle value/witness comparisons passed, plus 8 fixed gap/open/large-integer cases. Mathematical mismatches: 0. Repeated paths across combinations are not independent samples. This extends finite adversarial depth, not an arbitrary-real-path proof or product acceptance.

Original 129,960-path/420-group experiment was not rerun or edited. This review inspected its protocol. No old database, Store, real captures, market fetches, product mutations, branch changes or publication. Final git status was clean.

## Primary sources independently checked

- Proietti, *Ups and (Draw)Downs*, Definition 1 and §6.1–6.2 start: https://ceistorvergata.it/RePEc/rpaper/RP576.pdf . The paper uses logarithmic rolling-close drawdown and high/low envelopes; its random tie handling is not adopted. The proposed project bounds are not presented as paper replication.
- TradingView official broker-emulator documentation: https://www.tradingview.com/pine-script-docs/concepts/strategies/#broker-emulator . Its default inferred intrabar ordering and optional finer historical data justify avoiding one assumed actual path. This source does not prove that no TradingView script can compute the proposed bounds.

## Remaining gates

After R1/R2 text is frozen, the proposed minimal module is suitable to implement and independently test. Product parsing, query adapter, source identity projection, serialization limits and bounded-resource process tests remain unrun. Real sources, historical access, API/UI, browser, Windows, prediction/financial value and user efficiency remain unverified. An implementation GO does not authorize expanding these scopes.
# V2 follow-up decision

2026-10-14 UTC. Verified DESIGN-v2.md SHA256 `f25ebf37b9019ded8decacaea5d8757508cd287f3703654258e632bad1cfbda4` and inspected the complete v1→v2 diff.

**GO for the frozen minimal pure module and trusted-query adapter implementation, subject to the responsible parent's authorization.** R1 and R2 are closed.

R1 chooses the explicitly permitted smaller contract: first classified conflict per original row, batch source-rejected flag separately, existing date-group first reasons separately, and suppressed predicates explicitly unevaluated. Count semantics do not imply exhaustive concurrent diagnostics. The simultaneous-three-conflicts/duplicate-group/out-of-window counterexample is now part of frozen acceptance.

R2 explicitly retains original query rows unchanged and resolves duplicate members through top-level query identity plus date; ordinal stays null and no per-original-row payload is invented.

No mathematical, input-domain, witness, resource-budget, real-source or product-scope expansion occurred. Previous mathematical GO stands. No further experiment was needed or performed. Product implementation and resource/adapter tests remain future gates; implementation GO is not product acceptance, deployment approval, market qualification or predictive-value evidence.

# Independent implementation review

2026-10-14 UTC. **Final code-review GO**, bound to `src/anatrading/ohlc_decline_bounds.py` SHA256 `f39188c2be75f3c641290b9a414e84043d7186542e7727e72a9006b4511cf9b2`, design v2 SHA256 `f25ebf37b9019ded8decacaea5d8757508cd287f3703654258e632bad1cfbda4`.

No product defect or frozen-scope expansion found. Reviewed complete module, source parser/research-series/identity helpers, focused tests, qualification and review documents, and independent implementation acceptance REPORT.md (16,293 primary plus 34 supplemental assertions) with three bounded resource observations. I did not rerun the full suite or claim independent execution of the tester's checks.

- Integer tuple conversion exactly preserves source DECIMAL(38,18), validates the whole window before bound scans, rejects nonpositive and invalid geometry, and avoids caller Decimal context arithmetic and floats.
- Both extremizer scans match the proved orders. Strict depth and peak updates correctly implement earliest trough and earliest prior equal-height peak. Duplicate slots retain their independent positions. Zero witnesses remain null; close-only baseline is separately scanned. Fraction reduction, identification and ambiguity subtraction stay within the derived bounds.
- Query validation, exact endpoint presence, 253-date-group maximum, unknown coverage rejection and source-global conflicts preserve v2. Global conflict scan sees all supplied rows including duplicate groups and outside-window rows; first reason per source row and suppressed predicates are explicitly labeled. Ordinary dated outside-window invalid prices remain nonblocking. No source/market identity or historical qualification is upgraded.
- Invalid selected groups/ordinals reject the whole window, all five mathematical fields are null, and members/invalid evidence are retained without filtering. Duplicate-date ordinal is null with query identity/date backreference. Witness date and ordinal are resolved from generated members.
- Metadata and selection use bounded projection; source qualification is deep-copied. Existing query/member objects are not mutated. Same identity does not authenticate prices or create a cache.
- Resource account is appropriate: two 4m scans and one close scan, O(m) parsed/member evidence; shared daily sorting remains O(n log n) and storage O(n). No Store, network, API, UI, CLI, dependency, generic cache, ranking or prediction additions.

## Final result serialization guard: static verification

At the sole successful report return, after all fields and witness date/ordinal augmentation, `_json_size` invokes `json.dumps(..., ensure_ascii=False, separators=(',', ':'), allow_nan=False)` and UTF-8 encodes the complete representation. A length strictly greater than `256*1024` raises `ValueError('ohlc_result_limit')`; otherwise the complete report is returned. No clipping or partial serialization path exists. Invalid JSON/Unicode shapes are controlled failures.

This rejection branch was statically inspected, **not dynamically exercised by a naturally reachable oversized valid bounded report**. Three actual complete reports were independently serialized and remained within the limit. No fake bypass of the upstream 253-member/16 KiB identity bounds was introduced to claim coverage.

## Remaining reporting gates at review time

Independent resource observations used Linux/Python 3.12.14; product regression used the restored Python 3.14 environment. These facts must remain distinct. Resource time is aggregate parsing/sorting/core/serialization, not separate stage timing; RSS is whole-process high-water memory, not incremental function RSS.

Writer reported final affected tests 357 passed/2 missing-private-fixture skips, and qualification 234 plus 112 subtests with nine guarded processes and zero network attempts. Complete allowed product regression was still running when this code review was issued. Final qualification documents must incorporate its actual final outcome and retain static-only guard disclosure. This GO does not claim full regression completion, real-source compatibility, market availability, browser/Windows qualification, sustained performance, economic interpretation, execution or predictive value.

No product writes, private data/old database reads, market fetches or publication were performed by this reviewer.

## Writer's later final regression record

After the review above, the unchanged reviewed module and final 66-test file completed the full allowed product set: 3,825 passed, 49 skipped (48 private fixtures, one Windows-native), two known real-socket tests deselected, one existing Starlette/httpx warning, 146.45 s. This is the writer's execution, not a new independent reviewer rerun. See qualification 068 for commands, retained initial logs and boundaries.
