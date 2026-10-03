# RetrieVEL local checkpoint and resume — October 3, 2026

RetrieVEL and Relay are the active focus projects. This note records a local source checkpoint, not an installation, publication, release or scientific acceptance.

## Source identity and preserved work

Canonical home: `graph-engineering`. Product: VelGraphing / RetrieVEL. Compatibility package: `graph-engineering` 0.1.6.

Checkpoint branch: `checkpoint/retrievel-20261003`. Original branch: `codex/retrievel-baseline-delivery-20260929`. Original HEAD: `07f79841019cc5c36841a19b36a75b66a6882622`. The original branch reference stays at that HEAD. No remote action is part of this checkpoint.

| Artifact | SHA-256 |
| --- | --- |
| Canonical and projected retrieval | `3a43e8dff5678e93d009550e3a32c2f623e4f04d6ad02ea1257a817f676ea28a` |
| Reviewed 89-member package candidate | `103e018d7629dd092eb9b0ea725595d31ea226710302fe2d7f4a345f8459c947` |
| Release-manifest raw file | `df66aecb5a0dc256247f00792765e965441dceb22408bfdd48f272f33c85687b` |

The preserved checkpoint includes four overlapping groups across 16 source/test/generated paths. A later reviewable bring-current change corrects ordinary evidence source-role labels; it is not yet committed. The table above identifies this working source/package. Checkpoint groups:

- A: older offline graph tool-loop skill, reference, script and tests. Preserve this as WIP. Its original author and broader acceptance remain unresolved. Inclusion does not grant new acceptance.
- B: delivery separator admission repair and its UTF-8 regression.
- C: reviewed JSON/anchor containment, progressive separators, distinct public exports and typed invalid-UTF8 rejection, with source/tests and owning projections.
- D: reviewed intent-trigger preservation and unique-tag cap, with four regressions and owning projections.

B precedes C; D depends on C. The final package also contains A. Generated runtime source and metadata are retained as the reviewed source/package consistency unit. Runtime data, caches, raw query output, evaluator work and trials are excluded.

Do not hand-edit projected runtime. Any future source change needs the owning projector and manifest tools for its intended composition. See [source ownership](../architecture/SOURCE_OWNERSHIP_AND_PORTABILITY.md).

## Reused evidence and practical limits

The checkpoint retains 75 retrieval tests, 240 core tests, independent SOL High review and clean 89-file parity. The later source-role correction has two red-before/green-after regressions and 242 passing core tests in the existing project environment. Its owning generation and clean 89-file parity pass. No dependencies were installed. Earlier acceptance and failed evidence remain preserved.

Canonical whole-tree parity intentionally refuses ignored bytecode with `private_or_machine_path`. No cache cleanup or verifier relaxation is authorized by this note.

The retained real-repository question is `Where are source-package parity and retrieval provenance enforced?`. The original and isolated repaired-engine comparison both returned authenticated context, but current enforcement-body coverage was **0/5**. A new provider-free portable CLI canary ran against the checkpoint target. The copied 89-member package imported its own projected runtime. It returned 19 authenticated spans and 3,003 context bytes under the unchanged question/options. The corrected engine changed only source-role labels, with identical target snapshot, rankings, text, ranges, route and budgets; coverage remained 0/5. This is packaged-runtime execution, not installed-host command proof. Direct source fallback is required. Routing and delivery do not assess completeness. Lower context bytes do not prove cost, quality or speed benefit.

The resolved installed skill cache is internally consistent but stale: candidate `b4a4e11d9c0d403c7a3c344502677487c582f5d3613888b6c99eeef69f44a101`, 87 members, version 0.1.6. It differs from both the checkpoint and corrected package. Exact-source installed command execution is blocked pending a supported, explicitly authorized isolated installation/resolution step. No cache or global installation was changed. Native evaluator adoption and matched science remain unproved. The expired trial remains expired. Ground overlap is architecture context, not integration authority.

## One meaningful navigation workflow

Use an explicitly authorized dogfood session. Python >=3.11 and Git are required. No server or provider is needed. From the canonical repository root:

```sh
retrievel_output="$(mktemp -d /tmp/retrievel-dogfood.XXXXXX)"
GIT_OPTIONAL_LOCKS=0 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false \
python3 -B plugins/graph-engineering/skills/graph-find/scripts/graph_find.py \
  --root "$PWD" \
  --prompt 'Where are source-package parity and retrieval provenance enforced?' \
  --deliver --byte-budget 16000 --maximum-results 6 \
  > "$retrievel_output/context.json"
printf 'Retain locally: %s/context.json\n' "$retrievel_output"
```

Inspect paths, byte ranges, hashes, omissions and budget counters. Follow useful pointers, then read the current bodies directly:

- `scripts/package/verify_source_package_parity.py`: `verify`, `build_manifest`, `_verify_projection`.
- `packages/core/routing_v4.py`: `_read_verified_source_bytes`.
- `packages/core/retrieval.py`: `_validate_retrieval_custody`, `_verified_spans`, `GraphFindResult.to_delivery_dict`.

Record one useful pointer and each missing enforcement group. Do not execute historical manifest-writing examples from retrieved text. Keep source-containing result JSON local. The process exits on completion; Ctrl-C stops it. There is no daemon or persistent index to stop. `/tmp` is not durable storage.

## Next bounded closeout

Verify the actual installed package identity and all 89 member hashes before a separately authorized installed-command canary. The README installer targets `main`; that does not prove this checkpoint is installed. A package script run alone does not establish installed command resolution.

Then run one unchanged question/options canary through the actual installed command. Authenticate output and document missing bodies. The parent/user chooses the acceptance boundary: authenticated navigation with disclosed direct fallback, or the stronger frozen oracle requiring all five complete current enforcement-body groups in delivered context. Preserve 0/5 until new evidence establishes another result.

Do not start tuning, install a package, renew a trial or invoke a provider from this note alone. New work needs current source identity and the necessary scope/authority. Remote backup, merge and release remain separate decisions.


## Pending bounded tool-loop successor, October 3

Offline CLI build, inspect, explicit read on the already selected retrieval file exposed a Python multiline-signature defect: _verified_spans returned a 427-byte signature as an ok unit, while its independent AST function spans 6,614 bytes. The task-owned successor uses standard-library AST declaration bounds for valid Python, including decorators and nested units; other formats and invalid-Python fallback retain their existing behavior. Ordinary navigation still uses its existing line windows and ranking.

The successor is isolated for the parent tester and hygiene reviewer. Protocol regressions exercise complete UTF-8 multiline units, decorated async/class/nested containment, duplicate budget behavior, oversized refusal before a freshness read, changed bytes, and a missing disposable file. Source freshness and fail-closed delivery logic are unchanged. This does not establish installed/native adoption, ordinary answer completeness, or cost/quality benefit. The accepted label packet remains the sealed baseline. Parent acceptance and guarded integration are still required; no Git decision is implied.


### Independent rejection and second isolated successor

The first Python unit-bounds successor was rejected for integration: valid functions in configuration-like Python filenames bypassed AST handling, and Unicode separators inside string literals shifted the AST-to-byte line map. The second isolated successor considers valid Python declarations before basename heuristics and maps physical source lines from raw CR/LF byte endings. Generic configuration-name and Unicode-literal/physical-line-ending regressions preserve the rejecting guard and final return. Original independent failing inputs and logs remain retained. No new real-repository query replay, canonical integration, installed-host run or science trial occurred. Parent tester and hygiene acceptance remain required.


### Complete-unit refusal boundary, third isolated successor

V2 was independently rejected because decoded-string parsing rejected a valid UTF-8 BOM file and then delivered an indentation fragment as a unit. The third successor enforces a generic rule: parse exact Python bytes and return only complete supported units; otherwise return no unit. No complete-unit helper or obligation consumer may substitute a line-window fallback. Tool discovery exposes unresolved unit nodes; their reads defer with an explicit complete-file fallback obligation and zero charge. Valid Python byte encoding/BOM semantics and physical CR/LF byte custody remain intact. The maintained JavaScript grammar, validated JSON containers and plain ATX structural sections establish their own complete units; unavailable or unestablished grammar paths refuse. Ordinary navigation ranking and snippet semantics remain unchanged. The historical long valid Python assignment is now fully delivered when its complete unit fits, and refused without credit when it does not. Rejected candidates/repros remain preserved. No canonical integration, Git action, install, model/provider call or real-query replay occurred. Parent tester/hygiene acceptance is pending.
