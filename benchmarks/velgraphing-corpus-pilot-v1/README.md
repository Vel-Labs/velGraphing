# VelGraphing corpus pilot v1

Status: completed and sealed.

Outcome: `pilot_rejects_jev_promotion_and_does_not_establish_wall_clock_savings`.

The completed pilot records 24 independently scored packet rows and a SHA-256 result seal in `result.json`. Direct retrieval tied Jev-off on required-fact recall but fell from 6/6 to 5/6 passed tasks with Jev on. Graph-assisted retrieval improved recall by 1.85 percentage points without Jev and stayed at 6/6, but graph-assisted plus Jev fell by 3.70 points and by one passed task. Process and telemetry warnings remain visible in the result; unavailable timings, answer tokens, cost, and wall-clock savings remain `unknown`.

This is a six-task pipeline pilot for two bounded claims:

1. Whether VelGraphing helps navigation in a bounded slice of an interconnected code repository.
2. Whether the same route helps on many-small, long-structured, and mixed public content.

It is not a universal knowledge-system benchmark or corpus-level generalization study. Each profile has one task except the CPython profile, which has two. The result can reject graph assistance or show that Jev, not the graph, provides the useful change.

## Frozen inputs

`freeze.json` is the authority for the candidate, pinned commits, snapshot digests, routes, Jev budget, scoring gates, and telemetry. `corpus/questions.json` contains only the six user questions. `corpus/oracle.json` contains the independent required-fact rubric and must not enter an answer lane.

The corpus uses these source profiles:

| Profile | Source | Frozen material | Reuse boundary |
|---|---|---|---|
| Bounded CPython code slice | [python/cpython](https://github.com/python/cpython) | CPython asyncio and importlib documentation plus implementation files | PSF license notices remain in the snapshot; this is not the full code-product benchmark |
| Many-small negative control | [TheAlgorithms/Python](https://github.com/TheAlgorithms/Python) | 149 Python files from `graphs`, `searches`, and `sorts`, plus README and license | MIT attribution remains; graph-negative is a hypothesis, not a result |
| Long structured work | [Engineering Handbook](https://github.com/handbook-academy/engineering-handbook) | 179 HLD Markdown files, README, style guide, and license | CC BY-SA 4.0; preserve attribution and ShareAlike terms |
| Mixed public reference material | [OpenChain Reference-Material](https://github.com/OpenChain-Project/Reference-Material) | Pinned UTF-8 Markdown files covering FAQ, process, playbook, explainers, merger guidance, and self-certification material | CC0 is stated by the repository license for covered reference material; this is an inquisitive/community documentation case, not the later marketing corpus |

Each source is pinned to a full commit. Each manifest records the selected paths, byte lengths, file SHA-256 values, and a canonical snapshot digest. The benchmark uses source text only. It does not redistribute binaries or crawl live pages.

The materialized roots are disposable Git clones. They contain only the manifest paths in their tracked index. The source object checkouts remain separate and are never used as lane roots or mutated by materialization. Oracle isolation is procedural: packets forbid parent-directory and benchmark-artifact reads, but this pilot does not claim an OS sandbox.

Frozen files use logical runtime placeholders. `$VELGRAPHING_ROOT` is the product checkout, `$SOURCE_ROOT/<corpus-id>` is a source object checkout, `$LANE_ROOT/<corpus-id>` is a materialized lane, and `$RUN_ROOT/<packet-id>` is the packet and observation working directory. The parent resolves these placeholders at execution time and records the bindings in its local result or receipt. It must not rewrite `freeze.json` or `packets.json`; packet hashes therefore remain portable.

## Arms and scoring

Run each question once in each arm, with fresh host-native lanes and no inherited conversation history:

| Arm | Retrieval | Jev |
|---|---|---|
| A | Direct | Off |
| B | Direct | On |
| C | Graph-assisted | Off |
| D | Graph-assisted | On |

Compare Jev within retrieval route (`B-A`, `D-C`) and graph assistance separately (`C-A`, `D-B`). Score required facts independently. Record source support, context bytes, source operations, cold and warm graph cost, retrieval and answer time, fallback reads, Jev calls/tokens/latency, and proof or authority errors. Use `unknown` for unavailable values.

The Jev budget is 12 live calls: one request for each Jev-on arm and task. The parent owns exact request preview, request hash, operator approval, and provider-key custody. Do not retry without a distinct diagnosed cause.

Answer lanes must not read the freeze, oracle, result, labels, or scorer artifacts. Direct lanes must not inspect graph artifacts. Graph-assisted lanes must use returned source pointers and caller-declared fallback. All lanes are read-only and use the same pinned snapshots.

## Reproduction

From any checkout, set runtime roots without writing them into the frozen files. Create fresh source object checkouts under the ignored `$SOURCE_ROOT` directory. Use the pinned commit from `freeze.json` when fetching a commit that is not in the initial clone. Then choose a new empty child under `$LANE_ROOT`; the commands below use `v4`, which must be absent or empty before the first command.

```sh
BENCHMARK_ROOT=/path/to/graph-engineering/benchmarks/velgraphing-corpus-pilot-v1
SOURCE_ROOT="$BENCHMARK_ROOT/.inputs/sources"
LANE_ROOT="$BENCHMARK_ROOT/.inputs/lanes"
RUN_ROOT="$BENCHMARK_ROOT/.inputs/runs"
VELGRAPHING_ROOT=/path/to/graph-engineering
git clone --no-checkout --filter=blob:none https://github.com/python/cpython "$SOURCE_ROOT/cpython"
git clone --no-checkout --filter=blob:none https://github.com/TheAlgorithms/Python "$SOURCE_ROOT/thealgorithms-python"
git clone --no-checkout --filter=blob:none https://github.com/handbook-academy/engineering-handbook "$SOURCE_ROOT/engineering-handbook"
git clone --no-checkout --filter=blob:none https://github.com/OpenChain-Project/Reference-Material "$SOURCE_ROOT/openchain-reference-material"
```

Materialize the four roots with the existing stdlib-only helper:

```sh
python3 "$VELGRAPHING_ROOT/scripts/benchmarks/velgraphing_corpus_pilot_v1.py" --repo "$SOURCE_ROOT/cpython" --materialize-manifest "$VELGRAPHING_ROOT/benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests/cpython.json" --destination "$LANE_ROOT/v4/cpython" --lane-root "$LANE_ROOT"
python3 "$VELGRAPHING_ROOT/scripts/benchmarks/velgraphing_corpus_pilot_v1.py" --repo "$SOURCE_ROOT/thealgorithms-python" --materialize-manifest "$VELGRAPHING_ROOT/benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests/thealgorithms-python.json" --destination "$LANE_ROOT/v4/thealgorithms-python" --lane-root "$LANE_ROOT"
python3 "$VELGRAPHING_ROOT/scripts/benchmarks/velgraphing_corpus_pilot_v1.py" --repo "$SOURCE_ROOT/engineering-handbook" --materialize-manifest "$VELGRAPHING_ROOT/benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests/engineering-handbook.json" --destination "$LANE_ROOT/v4/engineering-handbook" --lane-root "$LANE_ROOT"
python3 "$VELGRAPHING_ROOT/scripts/benchmarks/velgraphing_corpus_pilot_v1.py" --repo "$SOURCE_ROOT/openchain-reference-material" --materialize-manifest "$VELGRAPHING_ROOT/benchmarks/velgraphing-corpus-pilot-v1/corpus/manifests/openchain.json" --destination "$LANE_ROOT/v4/openchain-reference-material" --lane-root "$LANE_ROOT"
```

The helper rejects absolute or escaped manifest paths, symlink components, Git symlink modes, non-regular modes, digest mismatches, non-empty destinations, and destinations outside `.inputs/lanes`. Its JSON result includes source checkout HEAD, index, and status hashes before and after materialization. They must match. The destination index must contain only manifest paths.

The exact include patterns and resulting digests are frozen in `corpus/manifests/` and `freeze.json`. The packet generator is:

```sh
python3 "$VELGRAPHING_ROOT/scripts/benchmarks/velgraphing_corpus_pilot_v1.py" --write-packets --questions "$VELGRAPHING_ROOT/benchmarks/velgraphing-corpus-pilot-v1/corpus/questions.json" --freeze "$VELGRAPHING_ROOT/benchmarks/velgraphing-corpus-pilot-v1/freeze.json" --output "$VELGRAPHING_ROOT/benchmarks/velgraphing-corpus-pilot-v1/packets.json"
```

The frozen preparation and the fresh four-arm pilot are complete. `result.json` contains the per-packet evidence, aggregate comparisons, provider summary, known warnings, preserved unknowns, and result seal.
