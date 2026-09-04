# P2-0 · Parametric First-Hop — LongMemEval Non-Regression

## Status

**non-regression pending**

The parametric first-hop stage has been added to `unifiedCascadeSearch`
but has NOT yet been validated against the LongMemEval benchmark.
No improvement numbers are claimed or should be inferred.

## What changed

An optional stage was prepended to `unifiedCascadeSearch` in
`local/src/core/search.mjs`. When all three conditions are met:

1. `opts.parametricFirstHop === true` (explicitly enabled by the caller)
2. A parametric broker is attached (`setParametricBroker()` or
   `options.parametricBroker` in the constructor)
3. The broker has an active session and returns a non-null hit

…then O(1) parametric exact recall runs first and returns directly,
skipping the E5 + FTS5 cascade. On any miss, absence, or failure, the
existing cascade runs with zero behavioural change.

The switch defaults **off**. With it off, no broker, or no snapshot,
the cascade is bit-identical to the pre-change code path.

## What this layer is for

The value of the parametric first-hop is **O(1) hot-zone reads and
exact key→value binding**, not semantic retrieval quality. It is not
expected to improve LongMemEval Recall@5 — the E5 + FTS5 cascade
already handles semantic and keyword recall. The parametric layer
complements it for exact-match scenarios (e.g. "what is the user's
favorite color" → exact binding, no embedding needed).

## Non-regression gate

Before merging any PR that touches `unifiedCascadeSearch`, the
LongMemEval benchmark must be run and **R@5 must not drop below the
96.0 baseline**.

| Metric | Baseline | With first-hop (pending) |
|--------|----------|--------------------------|
| R@5    | 96.0     | pending — not yet run    |

Until the benchmark is run and R@5 ≥ 96.0 is confirmed, this feature
must not be enabled by default.

## How to run the benchmark

```bash
cd local
node src/benchmark/recall-eval.mjs --benchmark longmemeval
```

Compare R@5 with and without `parametricFirstHop: true`.

## What must NOT change

- The E5 embedding channel (`_embeddingSearch`) — not touched.
- The SQLite FTS5 channel (`_ftsSearch`) — not touched.
- The RRF fusion logic (`_rrfFusion`, `_rrfFuseMany`) — not touched.
- The budget-tier shaping (`_shapeByBudgetTier`, `_shapeByRatio`) — not touched.
- The existing `recall()` method — not touched.

The first-hop stage is a **pure prepend**: it either short-circuits
the cascade (on hit) or is invisible (on miss/failure/off).
