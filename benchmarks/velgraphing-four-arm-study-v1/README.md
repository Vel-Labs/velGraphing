# Historical four-arm source recovery

This candidate preserves controller source and frozen contracts, not a completed study or run authorization. Private results and research notes remain excluded. These command examples are retained for source/API inspection only; providers, lanes and hooks stay held.

```sh
VELGRAPHING_ROOT="$PWD"
LANE_ROOT="$VELGRAPHING_ROOT/benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4"
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/benchmarks/four_arm_study_v1.py \
  prepare --root benchmarks/velgraphing-four-arm-study-v1 \
  --lanes-root "$LANE_ROOT" \
  --local-output "$PWD/.velgraphing-local/velgraphing-four-arm-study-v1/phase-2-pools.json" \
  --preflight-output benchmarks/velgraphing-four-arm-study-v1/preflight.json
```

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/benchmarks/four_arm_study_v1.py \
  validate --root benchmarks/velgraphing-four-arm-study-v1
```

```sh
WITNESS_CUSTODY="$PWD/.velgraphing-local/velgraphing-four-arm-study-v1/successor-ttc-witness-custody.json"
```

```sh
python3 -B scripts/benchmarks/four_arm_study_v1.py \
  validate-successor-overlay --root benchmarks/velgraphing-four-arm-study-v1 \
  --witness-custody "$WITNESS_CUSTODY"
```

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
