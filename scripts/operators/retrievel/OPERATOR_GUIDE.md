# Launch and reopen the source operator

Start at the maintained VelGraphing checkout root. Use its existing Python
environment with the project dependencies. Do not install another package for
this workflow. Choose an owned evidence directory outside the checkout and
outside the repository you want to inspect.

```sh
retrievel_repo="$PWD"
retrievel_python="$retrievel_repo/.venv/bin/python"
retrievel_source="$retrievel_repo"
retrievel_operator="$retrievel_repo/scripts/operators/retrievel"
retrievel_adapter="$retrievel_repo/plugins/graph-engineering/skills/graph-find/scripts/graph_find.py"
retrievel_native="$retrievel_repo/plugins/graph-engineering/skills/graph-find/scripts/graph_tools.py"
retrievel_runs="$HOME/Documents/RetrieVEL-runs"
mkdir -p "$retrievel_runs"
```

The evidence root must be an existing absolute directory owned by the current
user, without a symlink alias. `--output` must resolve to a new empty directory
below that root. The output cannot be the evidence root itself or any source or
operator directory. Use fresh names for each request. Existing evidence stays
unchanged when a destination is refused.

## One useful two-file request

```sh
"$retrievel_python" -B "$retrievel_adapter" \
  --root "$retrievel_source" \
  --prompt 'Compare .github/workflows/ci.yml and docs/INDEX.md.' \
  --deliver --byte-budget 32768 > "$retrievel_runs/request-01-handoff.json"
"$retrievel_python" -B "$retrievel_operator/handoff_client.py" \
  --handoff "$retrievel_runs/request-01-handoff.json" \
  --root "$retrievel_source" --python "$retrievel_python" \
  --tool "$retrievel_native" --evidence-root "$retrievel_runs" \
  --output "$retrievel_runs/request-01-source"
"$retrievel_python" -B "$retrievel_operator/inspect_evidence.py" \
  "$retrievel_runs/request-01-source"
```

The adapter returns JSON. The client prints the actual source status, accepted
file references and hashes, last accepted shared content charge, observed
native bytes, receipt location and any failure reason. Read the reported totals
for this exact source snapshot. Source edits change the document sizes and
snapshot; historical byte totals are not promises for a new run.

COMPLETE/exit 0 means the requested source actions completed. PARTIAL/exit 2
retains accepted source or observed delivery when a later action fails. A
missing or ambiguous target reports FAILED/exit 2 before native startup.
An allowance too small for the second file keeps the first file and its charge.
Already delivered bytes are not refunded. Invalid root/output configuration
refuses with exit 2 and stderr before creating a new receipt.

The terminal result does not answer the comparison question. Complete bodies
are retained in `responses.jsonl`, under `result.document.text`. If the adapter
already delivered a requested body, it remains in the input handoff; native
responses contain only later delivery. Preserve both files.

## Stop and reopen

Press Ctrl-C once for an active owned foreground client. Allow its cleanup to
finish. Interruption reports INTERRUPTED/exit 130. A reaped process leader does
not prove every descendant is absent. Do not retry a denied signal.

Reopen the saved directory with the inspector command above. It needs no new
source admission or provider call. Its existing custody check covers retained
native complete-file text/hash/bounds/charge. It is not a new validator of all
requested target fields or prior handoff delivery. On failure it reports the
saved failure and returns the saved exit code.

## Limits

The client validates source, snapshot, inherited allowance and native response
observations before accepting a file. Observed native bytes can include a
rejected body. The displayed ledger is the last accepted ledger; a rejected
later ledger grants no usable credit. No answer/evaluator stage is attempted.
Semantic completeness is not assessed.

`--follow-imports` is optional for one pending uniquely admitted Python target.
It uses a cached syntactic sibling witness. Multiple pending targets with that
flag refuse. Current importer freshness, runtime binding, dynamic imports and
broader language resolution are unproved. Large source pairs can exceed the
unchanged 32,768-byte limit. Do not increase the allowance to imitate a
historical success example. Ambiguous `.gitignore` candidates still require a
separate explicit-path question; automatic selection is absent.

Terminal presentation is best effort if stdout is unavailable. Earlier
evidence-write, cleanup and source-hash errors can prevent a durable receipt;
no durability is promised for an unwritable destination. This source operator
does not install or replace the packaged plugin, renew a provider trial, or
prove answer quality, cost savings or native evaluator adoption.
