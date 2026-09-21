# VelGraphing four-arm study v1

This directory contains the phase-2 pool freeze and the qualified phase-3a
execution adapter for the successor end-to-end study. It targets product commit
`4a4c7bf4f8f000db507117909610fb25bf929949` and package candidate
`f47d377d6a51d66cd6b790f5d4a900f41719877b84def61e08bc548a5673e4c1`.

The study has four public tasks and four arms per task. It requires 16 fresh
answer lanes on `gpt-5.6-luna` at medium reasoning and 16 independent grader
lanes on `gpt-6-astra` at high reasoning. It excludes C-02. An
operator-authorized private host-attested run completed all eight provider
calls, 16 answer calls, and 16 blind grader calls. Its result remains ignored
and private under the protocol publication boundary.

## Retained baseline

This package is the retained pre-optimization baseline. Keep its four tasks,
four arm meanings, product identity, source snapshots, request hashes, and
private diagnostic artifacts unchanged. A later optimization must use a new
versioned study and compare against this package. Do not revise this freeze in
place.

The private diagnostic supplies directional evidence only. It is not a public
performance result or a promotion gate. A successor must seal the strict
controller, use source-aware grading from the start, and capture complete wall
time plus answer and grader usage before it can support comparative product
claims.

Phase 2 made no provider, answer-model, or grader-model call. It materialized
and froze eight source-bearing pools through the merged product scanner,
relation, retrieval, candidate, selection, and Jev-preview seams. Detailed
candidate content remains ignored under
`.velgraphing-local/velgraphing-four-arm-study-v1/phase-2-pools.json`.
The tracked `preflight.json` contains only pool identities, counts, source
snapshot identities, request and candidate hashes, and source-free eligibility
summaries.

The final-candidate pools produced source-witnessed Graph relationship
candidates for D-01 and L-01. S-01 and M-02 recorded no Graph relationship
delta. The controller did not fabricate one. Offline membership analysis found
that a rerank can change final membership for every B and D pool, so phase 3
planned eight Jev calls and zero skips. The private host-attested run used all
eight approved calls with no retry.

## Successor scoring contract

`successor-rubrics.json` leaves the sealed questions and scoring rules
unchanged. The R5 freeze is the retained baseline. The strict result-v2
contract remains pending because its final transport did not seal. The rubric
accepts any source-supported M-02 process-documentation
choice, scores D-01 by the asked identity, ordering mechanism, and duplicate
behavior, gives graders the answer evidence-ID-to-source-path map, and requires
one decision per required fact.

The historical bundle remains available for validation and replay inspection.
Preparation, qualification, lane freezing, and study execution fail closed
because the historical freeze does not bind the current controller and host.
Execution requires a new successor freeze and fresh lane manifest that bind the
current controller, host, rubric, and grader contract.

`validate` reports `validation_scope: historical_bundle` and does not load the
successor overlay. `validate-successor-overlay` reports
`validation_scope: successor_overlay` plus the successor rubric and current
controller, host, and grader-contract identities.

Successor metadata names A and B as edge-disabled frozen-shortlist baselines.
It names C and D as relationship-enabled frozen-shortlist arms. These are not
ordinary unrestricted Direct and Graph repository-use lanes. Jev can reorder
only a frozen pool and cannot recover evidence excluded before pool creation.
For D-01, the relationship-enabled pool added source-verified imported-dependency
context, and Jev recovered it after baseline final selection omitted it. The
historical 1/3 D-D-01 grade is not retrieval-quality evidence because its grader
lacked the successor scoring and citation-mapping contract.

Set the repository and frozen lane roots, then reproduce the phase-2 pools:

```sh
VELGRAPHING_ROOT="$PWD"
LANE_ROOT="$VELGRAPHING_ROOT/benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4"
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/benchmarks/four_arm_study_v1.py \
  prepare --root benchmarks/velgraphing-four-arm-study-v1 \
  --lanes-root "$LANE_ROOT" \
  --local-output "$PWD/.velgraphing-local/velgraphing-four-arm-study-v1/phase-2-pools.json" \
  --preflight-output benchmarks/velgraphing-four-arm-study-v1/preflight.json
```

Validate the tracked freeze with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/benchmarks/four_arm_study_v1.py \
  validate --root benchmarks/velgraphing-four-arm-study-v1
```

Bind the private canonical witness custody once in the operator shell:

```sh
WITNESS_CUSTODY="$PWD/.velgraphing-local/velgraphing-four-arm-study-v1/successor-ttc-witness-custody.json"
```

Validate the successor overlay with:

```sh
python3 -B scripts/benchmarks/four_arm_study_v1.py \
  validate-successor-overlay --root benchmarks/velgraphing-four-arm-study-v1 \
  --witness-custody "$WITNESS_CUSTODY"
```

The adapter qualified all four treatment shapes with fixture lanes. It retained
four terminal receipts, resumed them without replay, exercised one Jev fallback,
and recorded zero external calls and zero retries. This does not prove live
execution or product performance.

T300 supplied 16 fresh Luna answer thread IDs and 16 fresh Astra grader
thread IDs for R6. Separate live-provider authority is still required. The IDs
are in a private canonical JSON file with schema
`velgraphing-four-arm-lane-bindings-v1` and one `trial_id`,
`answer_thread_id`, and `grader_thread_id` row for each frozen dispatch.
The exact 32 lane commands can be reproduced with:

```sh
PYTHON_EXECUTABLE="$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.executable).resolve())')"
RUN_ROOT="$PWD/.velgraphing-local/velgraphing-four-arm-study-v1/<RUN_ID>"
python3 -B scripts/benchmarks/four_arm_study_v1.py freeze-lanes \
  --root benchmarks/velgraphing-four-arm-study-v1 \
  --bindings <ABSOLUTE_PRIVATE_BINDINGS_JSON> \
  --run-root "$RUN_ROOT" --python-executable "$PYTHON_EXECUTABLE" \
  --witness-custody "$WITNESS_CUSTODY"
MANIFEST_SHA256="$(shasum -a 256 "$RUN_ROOT/lane-manifest.json" | awk '{print $1}')"
```

Parent sends the exact canonical request bytes inline to the model task. The
task does not read or write a benchmark file. Parent passes the exact final
assistant bytes to `time_to_correct_handoff.py capture`. The helper first
retains those bytes as `assistant-response.raw`. It then parses one JSON object,
validates the frozen identity and embedded role contract, and writes canonical
`draft.json` bytes without changing the parsed content. Parent then uses the
existing `attest` and `respond` commands.

After Parent verifies the manifest hash and grants the exact provider budget,
run the serial study with:

```sh
"$PYTHON_EXECUTABLE" -B scripts/benchmarks/four_arm_study_v1.py run \
  --root benchmarks/velgraphing-four-arm-study-v1 \
  --pool-artifact "$PWD/.velgraphing-local/velgraphing-four-arm-study-v1/phase-2-pools.json" \
  --lane-root "$LANE_ROOT" \
  --run-root "$RUN_ROOT" --lane-manifest "$RUN_ROOT/lane-manifest.json" \
  --witness-custody "$WITNESS_CUSTODY" \
  --allow-live-jev --approved-max-live-jev-calls 8 \
  --approved-lane-manifest-sha256 "$MANIFEST_SHA256" \
  --approved-python-executable "$PYTHON_EXECUTABLE" \
  --approved-request-byte-set-sha256 80b3411f0d30600bc302a59debe36fe66734e4aceca0da6afdae303dc096af94 \
  --approved-budget-usd 0.359789241
```

The strict controller did not produce a valid result-v2 seal. Its R8 through
R10 task-envelope attempts returned empty or malformed model responses before
provider execution. The tracked contract is therefore reset to pending instead
of pointing at an abandoned manifest.

The private host-attested run used the same frozen pools, custody, source
revalidation, selector, answer model, grader model, call cap, and no-retry
policy. The model returned semantic answer and grade content only. Parent bound
task identity and timing outside the model response. This transport completed,
but it is not the strict controller result-v2 transport. Treat its ignored
`result.json` as diagnostic evidence, not as a public product-performance seal.

A separate private source-aware regrade gives each fresh blind grader only the
retained answer, frozen rubric, and exact cited source records. It makes no
provider or answer call, retains raw grader output, preserves the original
result hash, and binds the A-S-01 Markdown-only normalization. Its numeric
results remain private under the same publication boundary.

Provider performance detail must not be published without separate provider
permission. Public documentation can state execution counts and controls, but
not provider-specific performance results.
