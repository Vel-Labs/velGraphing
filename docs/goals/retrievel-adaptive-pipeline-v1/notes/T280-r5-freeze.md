# T280 final-candidate R5 freeze receipt

## Outcome

T280 passed. The final product candidate is integrated into the benchmark
branch. The complete R5 freeze passed independent review and is pushed. No
provider, answer, or grader call ran.

## Git and package identity

- Benchmark branch: `codex/retrievel-four-arm-study-v1`
- Pushed benchmark head:
  `307b2e77dda0af983b05de4cad0abf71be4b915c`
- Product implementation ancestor:
  `6b9d120e74bb0b658d8623bd2ec37bb05096f6b1`
- Package candidate SHA-256:
  `f47d377d6a51d66cd6b790f5d4a900f41719877b84def61e08bc548a5673e4c1`
- Historical R4 result before and after:
  `884dbb95387ff6b49606c2303b2788cb6d80a573eaa5fd4a63571814074f5a54`

The normal product merge is `3404e68e6e3b5a852d8a161ee25b7c9b4cd5f7e2`.
Its parents are the earlier benchmark/product merge `84c7674` and current
product goal head `5367d57`.

## Tracked benchmark changes

- `benchmarks/velgraphing-four-arm-study-v1/README.md`
- `benchmarks/velgraphing-four-arm-study-v1/PROTOCOL.md`
- `benchmarks/velgraphing-four-arm-study-v1/freeze.json`
- `benchmarks/velgraphing-four-arm-study-v1/preflight.json`
- `benchmarks/velgraphing-four-arm-study-v1/successor-ttc-contract.json`
- `scripts/benchmarks/four_arm_study_v1.py`
- `tests/benchmarks/test_four_arm_study_v1.py`

## Freeze identities

- Private run root:
  `.velgraphing-local/velgraphing-four-arm-study-v1/successor-live-r5-6b9d120`
- Freeze raw SHA-256: `d4b7a83fbeaa963269e5853e74cca1b4d6128410f7c4c6e6854f5ce0356d205c`
- Preflight raw SHA-256: `5f8e76e63f094efca842afcf02bda18a4062f29b4aed1cd7040a0129bc337ada`
- Pool artifact raw SHA-256: `3721b7378848d024e073cfa67bce44249b62551835ce236c22837119fee16d7b`
- Successor contract raw SHA-256: `3868fe33a55b66fb2ade9705ff895691bb9778d778e3b90971763150f29ecbbb`
- Successor contract canonical SHA-256:
  `b5d10d3008a2a92288520f2f13512620153f5ced993dec61f19ed046bbd5e44a`
- Lane manifest SHA-256:
  `1953e1ed38206eb4142ad62ae5fe0682779bdcde031149e6b071e7f4fe15d02d`
- Lane setup receipt SHA-256:
  `acc8659fa80b01470e89fd58c8920eb0b74b72f5d532dcaaa5377d3dd0adb745`
- Request-byte-set SHA-256:
  `80b3411f0d30600bc302a59debe36fe66734e4aceca0da6afdae303dc096af94`
- Witness custody bound SHA-256:
  `e042c9ee45c7fcc9e36a7ad693b7f77106f12dd94f06756b9e8ae19e276be38b`
- Frozen Python executable:
  `/opt/homebrew/Cellar/python@3.14/3.14.5/Frameworks/Python.framework/Versions/3.14/bin/python3.14`

## Pools, lanes, and budget

- Eight paired Direct and Graph pools.
- Sixteen frozen trial plans.
- Sixteen fresh Luna medium answer tasks.
- Sixteen fresh Astra high grader tasks.
- Thirty-two unique task IDs.
- Thirty-two exact `READY` setup responses.
- Zero setup tool calls.
- Eight planned Jev calls.
- Zero retries.
- Zero executed R5 calls.
- Exact request bytes: 758,130.
- R5 conservative reservation: USD `0.03184146`.
- Aggregate conservative commitment: USD `0.359789241`.
- Remaining USD 1 budget: USD `0.640210759`.

D-01 Direct pool:
`d5ff853da5725875aa6fa812569ddc02a70b23352d8c59b27fecb79937609fb6`.
D-01 Graph pool:
`b0e2df0e7bae33ec64b909b1bf1f1f2675ab613c576354770cfe668f47deee5b`.
The Graph pool contains one verified relationship candidate and has a distinct
request SHA-256 from Direct.

## Validation

- Focused benchmark and controller tests: 24 passed.
- Historical bundle validation: passed.
- Successor overlay and custody validation: passed.
- Runtime pool, candidate, source-span, request, and budget bindings: passed.
- Live gate correctly rejected the pending approval state.
- Projector ran twice with byte-identical output.
- Clean 87-file package parity passed.
- `git diff --check` passed.
- Independent Luna high freeze audit passed.

## Remaining authority

The contract status is `frozen_pending_final_user_reack`. Before live execution,
the exact request-byte-set hash, eight-call cap, USD `0.359789241` aggregate
reservation, lane-manifest hash, and absolute Python executable require one
post-freeze user reacknowledgement. After that one gate, no per-trial approval
is required.

## Proof boundary

This receipt proves freeze readiness, lane identity, source custody, and budget
binding. It does not prove answer correctness, TTC, Graph or Jev benefit, or any
comparative performance result. R5 has no result or provider telemetry yet.
