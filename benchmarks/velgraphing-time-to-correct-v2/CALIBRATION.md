# VelGraphing time-to-correct calibration v2

Status: executed and closed. The retained result is unresolved. See
[`RESULT.md`](RESULT.md) and [`result.json`](result.json).
The immutable `calibration.json` remains the pre-execution freeze.

The v1 host-timing qualification stopped after seven terminal or cancelled
trials. The Jev provider ledger remained empty. The observed native handoffs
exceeded v1 host timeouts: one answer draft arrived after about 139 seconds
against a 120-second limit, another answer completed in about 113 seconds, and
its pre-warmed grader draft existed after about 44 seconds but canonical publish
completed after about 69 seconds against a 60-second limit. One responder also
rejected a request that did not contain the exact response object. These events
invalidate v1 as a host-timing qualification. They do not measure VelGraphing,
Jev, or model performance.

V2 preserves the 24 frozen registrations, source pilot hashes, `gpt-5.6-sol`
medium model, zero retries, and 12-call Jev cap. It changes only the governed
host envelope:

- preparation: 180 seconds;
- Jev approval: 60 seconds;
- answer: 180 seconds;
- grader: 120 seconds;
- total trial wall time: 600 seconds.

Every preparation, answer, and grader request contains a canonical-JSON response
contract. A native task can produce the accepted object without reading benchmark
documentation.

## Offline qualification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmarks/time_to_correct_calibration.py plan \
  --calibration-id velgraphing-ttc-calibration-v2
PYTHONDONTWRITEBYTECODE=1 python3 scripts/benchmarks/time_to_correct_calibration.py qualify \
  --calibration-id velgraphing-ttc-calibration-v2
```

Both commands make zero provider calls and do not read credentials.

## Runtime boundary

V2 uses only this canonical run root:

```text
$VELGRAPHING_ROOT/.velgraphing-local/velgraphing-ttc-calibration-v2
```

The coordinator requires the explicit v2 calibration ID. The run-root identity
and completed-trial identity must both match v2. V1 receipts cannot resume v2.

The Parent owned live execution, credentials, native task creation, each Jev
request-hash approval, and final acceptance. Do not rerun the sealed result from
this document.

Define the repository and exact v4 lane roots before approval or execution:

```sh
export VELGRAPHING_ROOT=/absolute/path/to/graph-engineering
export LANE_ROOT="$VELGRAPHING_ROOT/benchmarks/velgraphing-corpus-pilot-v1/.inputs/lanes/v4"
export RUN_ROOT="$VELGRAPHING_ROOT/.velgraphing-local/velgraphing-ttc-calibration-v2"
```

For each Jev-on request, approve the exact request hash with the v2 selector:

```sh
PYTHONDONTWRITEBYTECODE=1 "$VELGRAPHING_ROOT/.venv/bin/python" \
  "$VELGRAPHING_ROOT/scripts/benchmarks/time_to_correct_calibration.py" approve-jev \
  --calibration-id velgraphing-ttc-calibration-v2 \
  --repo-root "$VELGRAPHING_ROOT" --run-root "$RUN_ROOT" \
  --trial-id "$TRIAL_ID" --request-sha256 "$REQUEST_SHA256" \
  --approved-max-live-jev-calls 12
```

```sh
PYTHONDONTWRITEBYTECODE=1 "$VELGRAPHING_ROOT/.venv/bin/python" \
  "$VELGRAPHING_ROOT/scripts/benchmarks/time_to_correct_calibration.py" run \
  --calibration-id velgraphing-ttc-calibration-v2 \
  --repo-root "$VELGRAPHING_ROOT" --lane-root "$LANE_ROOT" --run-root "$RUN_ROOT" \
  --allow-live-jev --approved-max-live-jev-calls 12
```
