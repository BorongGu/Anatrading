# Independent dispersion review audit

This directory was saved after the original two JavaScript executions. It is not a contemporaneous pre-execution filesystem freeze. Original protocol evidence is the written protocol recorded before the boundary execution. Original outputs below were transcribed from tool results. No claim about file creation timestamps proving the freeze is made.

Original executions: one basic-fixture/source-collision run, then one separately frozen boundary-extension run. `audit.mjs` consolidates those two original scripts, replacing only the tool `text` output helper with a JSONL console adapter and renaming the first fixture map to avoid a combined-script name collision. No execution of this saved script has occurred as of initial persistence. No repository, market data, Store, dependency installation, benchmark or product test was involved.

## Original freeze: reviewer-boundary-extension-v1

The following protocol was sent to the primary researcher before its execution:

n=20; lattice u=x×10^18; six fixtures: constant u=1, constant u=10^38−1, alternating 1/2, alternating (max−1)/max, nineteen 1s plus max, and nineteen 10^18s plus 100×10^18. Independent oracle Dpair=Σ(i<j)(ui−uj)^2 equals Dsum=20Σu^2−S^2; check D≥0, zero iff constant, bit length≤264, lower negative iff S^2<4D for positive S. Source zero/negative/out-of-range reject. Retain slots in a 60-position series with invalid index25; first19 insufficient, invalid25..44, recovery45. JS BigInt only, no repository/dependencies/Store.

## Limitations

The input-domain boolean check is a standalone lattice boundary check, not execution of the repository Decimal parser. Source eligibility and rounding/square-root display remain implementation work. Missing-position checks test fixed-window indexing, not the repository adapter. `bits` uses binary string length, so zero is displayed as one character rather than a mathematical nonzero bit requirement. No wall time/RSS inference is made.

## Publication clarification

The assigned historical checkout was unavailable; source review used GitHub exact ref 1d694cf45b4e37a0f9331d651b9ee964e2c34681. Private executor paths are omitted from this public copy. The original boundary ceiling was 264 bits; the later algebraic bound is 262 bits. The frozen audit is unchanged.
