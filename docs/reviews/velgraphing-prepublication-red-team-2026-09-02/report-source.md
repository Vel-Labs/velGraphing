# VelGraphing pre-publication red-team

Date: 2026-09-02

Audience: maintainers and release decision-makers

Decision: hold the broad performance announcement; continue as an explicit alpha

## Executive verdict

VelGraphing is a credible research asset with a useful product thesis: use a
small, source-bound graph to route an agent to authoritative repository spans.
The current package is not yet a complete public product. It can build, update,
audit, and benchmark graph artifacts, but the installed public flow does not
expose a supported operation that uses the graph to answer the user's core
question: **where should I look next?**

This is the release boundary. Do not add another graph model, database, daemon,
or benchmark generation before it is fixed.

The staged candidate also stores full source content in graph records. This
makes the graph a second copy of the repository instead of a compact directory
to source. It increases footprint, privacy exposure, and staleness risk. The
public product should use the graph to select evidence cards. The repository
broker should then read exact source spans.

```text
question
   |
   v
graph-find -> ranked evidence cards -> broker reads exact source spans
   |                                         |
   +---- uncertainty or missing evidence ----+
                                             v
                                      answer or code change
```

Confidence in this release sequence: **9/10**.

Confidence in a generalized performance claim today: **4/10**.

The difference is empirical. The architecture has a defensible direction, but
the current shipped interface has not yet produced a reproducible, multi-repo
result through the same path that a new user will install and operate.

## Candidate and scope

- Repository: `Vel-Labs/velGraphing`
- Reviewed commit: `da0677c4dfc4a8905a9053821f7c0ee18b4eb982`
- Staged diff SHA-256:
  `993323f5dbd3e4599d99f0b5301953574489730ce2319e432ac39803f439ea87`
- Staged package parity candidate:
  `9f6a02f555fd751573e409f8c9dedbc55c4579943dd93ffaacef02c4fdbf65a2`
- The staged `0.1.5` candidate is not the public GitHub revision.
- This review did not publish, install, commit, push, or modify a consumer.

## What we missed

| Finding | Why it matters | Required response |
|---|---|---|
| No public graph query operation | A user can create and inspect an artifact but cannot use it for normal repository work. | Add one `/graph-find` entry that invokes the existing retrieval path and returns cited evidence cards. |
| Graph records contain full source content | This duplicates repository data and weakens the privacy, footprint, and source-authority story. | Store source identity, structure, tags, and coordinates. Read exact bytes from source through the broker. |
| Installed commands do not prove runtime use | Skill text can exist without an agent discovering or invoking the graph. | Audit installation, discovery, invocation, freshness, exact-source fallback, and result attribution. |
| No clean first-use lifecycle | `npm test` assumes a local `.venv`; the user path does not prove dependency setup, failure recovery, or uninstall. | Test a clean install in a disposable repository and document start, find, update, audit, benchmark, and uninstall. |
| Readiness scanning is not Git-aware | A recursive non-hidden scan can ingest ignored build output or untracked sensitive files. Large files can abort the run. | Default to tracked files. Add explicit include/exclude controls and fail-safe binary, secret, and large-file behavior. |
| No public support matrix | Parser-backed structure currently covers JavaScript-family files only. | Publish the exact language and evidence capabilities. Add parsers only when measured user demand requires them. |
| No persistent product index | `/graph-update` can fall back to a rebuild and does not provide a simple freshness contract. | Persist one project-local index with a version and source-tree identity. Rebuild only invalidated records. |
| Adapter is documented but not an ordinary callable surface | The Orcastrata adapter is useful code, but users do not have one simple invocation example. | Add one stable command or import example after the main product path works. |
| Public API contains historical generations | Multiple navigation and retrieval generations increase audit cost and create ambiguous exports. | Name one supported public API. Mark or remove internal historical surfaces before `1.0`. |
| Release trust files are absent | New users cannot quickly find security reporting, contribution rules, or change history. | Add `SECURITY.md`, `CONTRIBUTING.md`, and `CHANGELOG.md`; add a minimal CI workflow for the documented clean path. |

## What we overlooked

The largest oversight was not another retrieval algorithm. It was the adoption
contract:

> installed -> discovered -> invoked -> fresh -> source-verified -> useful

Each transition needs observable evidence. A graph that exists but is not used
has zero product value. Graphify users report this exact failure mode: the graph
can be present while an agent ignores it. Other users report excessive output,
generic high-degree nodes, and monolithic indexes that defeat the context-saving
goal. These are product-shape warnings, not reasons to copy Graphify's design.

We also overlooked a negative decision. Selective retrieval research shows that
retrieval is sometimes harmful. `/graph-find` must be allowed to return
`insufficient evidence` or `use direct source` instead of always returning a
graph packet. That no-op is a feature.

## The most credible FUD

| Criticism | True today? | Preemption |
|---|---:|---|
| “It is promptware around a Python library.” | Partly | Ship one callable graph-find path and prove the installed agent invokes it. |
| “The benchmarks are harness artifacts.” | Material risk | Publish a frozen, runnable benchmark that exercises the shipped interface and retains sanitized raw traces. |
| “You call a lexical source mirror a graph.” | Partly | Use typed structural relations and source pointers. State when scoring is lexical. Never let tags stand in for proof. |
| “The 30% / 55% headline is cherry-picked.” | Yes, if generalized | Label the existing result as one controlled task. Do not lead the release with it. Publish distributions and failures. |
| “It leaks my private code into another store.” | Plausible | Make the local-only data flow explicit. Default to Git-tracked inputs. Do not store source bytes in the graph. |
| “It only understands JavaScript.” | Parser-backed support is narrow | Publish the support matrix. Use path and text fallback for other languages without implying structural parity. |
| “It becomes stale immediately.” | Not yet disproved | Bind every index to the source tree and expose freshness in every result. Refuse consequential results from stale data. |
| “It saves context but adds latency and setup cost.” | Possible | Report cold build, warm query, fallback, tool, token, byte, and wall-clock costs separately. |
| “The repo contains years of abandoned experiments.” | Visible in API and benchmark history | Keep research evidence, but move unsupported generations out of the public API and document the one supported path. |
| “It cannot prove better coding outcomes.” | True today | Add executable task outcomes after retrieval quality passes. Do not equate retrieval recall with task success. |

## The obvious missing feature

The missing feature is **graph-assisted find with proof**.

The smallest useful response is a ranked list of evidence cards. Each card
contains:

- path;
- symbol or structural unit;
- exact line or byte range;
- why the item was selected;
- typed relation, when used;
- source-tree identity and source hash;
- freshness state;
- route used;
- whether direct source fallback is required.

The command should not answer from graph topology. It should help the agent
exclude irrelevant areas, then read the smallest authoritative source spans.
This is the product's clearest distinction from a repository summary or vector
search wrapper.

## Release gates

Complete these gates in order. Test after each gate because each one can
invalidate the next.

| Gate | Task | Done? | Exit condition |
|---:|---|:---:|---|
| 1 | Expose `/graph-find` through the installed package. | No | A fresh Codex session discovers it, invokes the current retrieval code, and returns exact cited spans or a direct-source decision. |
| 2 | Convert the graph from a source mirror to a source-pointer index. | No | Exported graph data contains no full source body; exact source retrieval still passes freshness and hash checks. |
| 3 | Finish the real user lifecycle. | No | In a disposable repo: install -> start -> find -> edit -> update -> find -> audit -> uninstall, with observable attribution and safe failure behavior. |
| 4 | Close privacy and supply-chain gaps. | No | Git-aware scope, excludes, binary/secret/large-file rules, clean dependency bootstrap, minimal CI, security policy, and rollback are documented and tested. |
| 5 | Run the public benchmark through the shipped interface. | No | Direct, graph-only, graph-assisted, and graph-plus-fallback run on frozen realistic tasks with exact spans, outcomes, repeats, cold/warm costs, negative controls, and sanitized raw evidence. |

After Gate 5, add only the languages and integrations that measured failures
justify. Do not add a vector database, daemon, cloud service, multi-repository
federation, autonomous hooks, or more schema layers before these gates pass.

## Benchmark required for a public claim

The benchmark must answer three separate questions:

1. Did the agent retrieve the required evidence?
2. Did the agent produce the correct answer or code change?
3. What did retrieval cost?

Use four routes on identical frozen repository states:

- Direct source tools.
- Graph only.
- Graph-assisted exact source reads.
- Graph-assisted reads with targeted direct fallback.

Required measures:

- file, symbol, line, and exact source-span recall;
- required-fact coverage and unsupported claims;
- executable task outcome where a task changes code;
- fallback and abstention rate;
- source reads, searches, listings, and total repository operations;
- source bytes and answer-visible context bytes;
- runtime-reported input and output tokens or cost; do not estimate missing use;
- cold index-build time and bytes;
- warm query time and bytes;
- end-to-end wall-clock time;
- safety, authority, stale-source, and prohibited-write errors;
- per-task results, median, tail, variance, and paired regressions.

Include no-gold and wrong-repository controls. Repeat stochastic answer trials.
Keep task creation, agent execution, grading, and harness validation separate.
Publish the failures with the passes.

This follows the direction of Agent Retrieval Bench, which freezes repository
commits and includes positive, no-gold, and wrong-repository controls across 427
samples and 25 repositories. It also follows SWE-Explore, which scores ranked
code regions under a fixed line budget. Both measure localization directly
instead of assuming that a plausible answer proves good retrieval.

## What the research says

| Evidence | Practical implication for VelGraphing |
|---|---|
| [Agent Retrieval Bench](https://arxiv.org/abs/2607.24882) reports that no retrieval family dominates and that agent traces can miss all gold files. | Publish controls and failure distributions. Do not market one aggregate percentage as universal. |
| [SWE-Explore](https://arxiv.org/abs/2606.07297) evaluates ranked code regions under a fixed line budget and connects retrieval to downstream repair. | Score exact regions and executable outcomes, not only file recall. |
| [LocAgent](https://arxiv.org/abs/2503.09089) makes graph exploration an explicit agent action and uses hierarchical preview/fold/full views. | Make graph use callable and budgeted. Do not inject the whole graph into context. |
| [RepoGraph](https://arxiv.org/abs/2410.14684) adds repository graphs to the agent action space and still observes contextual and regression failures after localization. | A correct location is necessary, not sufficient. Keep source reads and tests in the loop. |
| [Repoformer](https://arxiv.org/abs/2403.10059) finds that unconditional retrieval can be unhelpful or harmful. | Add an explicit no-op/direct-source route and measure routing precision. |
| [RepoCoder](https://arxiv.org/abs/2303.12570) uses iterative retrieval and generation. | Support progressive narrowing instead of a single large packet. |
| [RAGAS](https://arxiv.org/abs/2309.15217) separates retrieval, context, and generation quality. | Keep retrieval recall, answer correctness, and faithfulness as separate gates. |
| [ALCE](https://arxiv.org/abs/2305.14627) measures citation correctness and completeness. | Score whether each consequential claim is supported by the cited exact span. |
| [Anthropic's agent evaluation guidance](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) separates task, trial, grader, trace, environment outcome, agent harness, and evaluation harness. | Preserve these identities and repeat stochastic trials. |
| [Aider's repository map](https://aider.chat/docs/repomap.html) combines parser structure, dependency ranking, a token budget, and exact file follow-up. | A compact structural map plus source follow-up is a proven product shape. |
| [Sourcegraph CodeScaleBench](https://github.com/sourcegraph/CodeScaleBench) provides real repository tasks and verifiers. | Reuse established task forms instead of inventing only repository trivia. |
| [Graphify's public benchmark discussion](https://github.com/Graphify-Labs/graphify/discussions/1677) reports improved key-fact coverage on its own harness. | This is useful market evidence, not independent proof. Match its transparency and exceed it with shipped-interface and negative-control evidence. |
| [A Graphify community report](https://github.com/Graphify-Labs/graphify/issues/425) describes oversized context reports, generic high-degree nodes, and better per-project than monolithic graphs. | Cap output, suppress generic nodes, and keep project indexes separate. |
| [GitNexus](https://github.com/nxpatterns/gitnexus/blob/main/README.md) exposes MCP, skills, freshness checks, and cleanup. | Users now expect a callable tool, stale-index visibility, and removal support. |
| [JetBrains Context](https://blog.jetbrains.com/ai/2026/07/introducing-jetbrains-context-repository-intelligence-for-coding-agents/) emphasizes incremental indexing and measurable repository intelligence. | Cold build and warm refresh are product metrics, not implementation details. |
| [Martin Fowler / Thoughtworks on context engineering](https://martinfowler.com/articles/exploring-gen-ai/context-engineering-coding-agents.html) notes that rules, skills, and tools consume context. | Measure the plugin's own instruction and routing overhead. |

## Practitioner and social signals

The strongest public signals are not generic “AI coding” posts. They are people
asking whether repository context is actually invoked, current, smaller, and
better than grep or direct reads.

- Graphify discussion: [Claude ignoring Graphify](https://github.com/Graphify-Labs/graphify/discussions/921).
- Graphify issue: [semantic extraction can exceed an agent output limit](https://github.com/Graphify-Labs/graphify/issues/1758).
- Graphify benchmark question: [task success versus graph compression](https://github.com/Graphify-Labs/graphify/discussions/1328).
- LinkedIn practitioner post: [context signals and agent navigation](https://www.linkedin.com/posts/dinesh-raghupatruni-44a021184_ai-genai-developertools-activity-7455576329405784064-mz1b).
- X documentation itself now uses a short `llms.txt` map before full content:
  [X developer documentation](https://docs.x.com/tools/llms-txt).

Potential outreach targets after the release gates pass are the maintainers and
communities around Aider, Sourcegraph/CodeScaleBench, Graphify, GitNexus, and
JetBrains Context. They have direct topical reach and can challenge the work on
its merits. This review did not verify individual follower counts, so it does
not rank people by audience size. A technical invitation to reproduce the
benchmark is more credible than an influencer pitch.

## Outside-model review outcome

The requested cross-provider review did not produce admissible analysis. Do
not claim provider consensus.

| Requested reviewer | Route outcome | Review accepted? | Reason |
|---|---|:---:|---|
| Claude Sonnet 5 | Provider returned | No | Response did not satisfy the closed JSON contract and did not perform the requested review. |
| Grok 4.5 | Provider timed out at 300 seconds | No | No output was returned. |
| DeepSeek v4 Pro | Provider timed out at 300 seconds | No | No output was returned. |
| MiniMax M3 | Provider was not called | No | The configured route could not prove the requested model identity. A safe pre-provider retry also failed identity verification. |

Orcastrata's single-attempt contract forbids replay after a provider was called
or its execution state is ambiguous. Only the proven pre-provider MiniMax
failure was retried. The raw routing evidence remains under the local untracked
`reports/` directory. It can contain machine-specific paths and is not a public
release artifact.

Two independent Codex read-only reviews did complete. They agreed on the main
gaps: no callable query path, no shipped-interface benchmark, narrow language
support, incomplete privacy and clean-install proof, and the need to separate
retrieval quality from answer quality. A separate research pass reached the
same product position: graph as a selectable navigation action, followed by
source verification.

## Marketing boundary

Do not lead the public release with:

> 30% less context and 55% fewer tool operations with the same quality.

That result is real for one controlled task, but it is not a generalized
product result. The current public benchmark evidence does not support that
interpretation.

A truthful alpha statement is:

> VelGraphing is an early, source-verified repository navigation experiment.
> It builds a local structural index, routes agents toward likely evidence, and
> keeps exact source reads as authority. Our next public gate is a reproducible
> shipped-interface benchmark across multiple repositories.

After all five release gates pass, a stronger statement may report the paired
median and tail results from the public benchmark. It must name the repositories,
tasks, route, model, repeats, cold/warm split, failures, and exact comparison.

## Final recommendation

Proceed, but change the publication order:

1. Ship `/graph-find` as the one supported value operation.
2. Remove full source bodies from the graph export.
3. Prove the clean installed lifecycle and privacy boundary.
4. Run the public benchmark through that exact interface.
5. Publish the alpha with reproducible evidence and explicit limitations.

This is not a call for more architecture. It is a call to connect the existing
retrieval code to the user's workflow, shrink the artifact to its intended role,
and test the product that people will actually install.

## Validation and remaining risk

Current candidate checks performed during this review:

- full repository suite: 222 tests passed;
- source/package parity: 70 files passed;
- staged diff check: passed;
- relative Markdown link scan before this report: passed.

This report changes documentation only. It does not invalidate those product
checks. It does not establish installation, runtime adoption, multi-language
quality, public benchmark reproducibility, or generalized performance.

Remaining risks:

- The staged candidate and public repository differ.
- Outside-provider consensus is unavailable because all four routed reviews
  failed acceptance.
- Vendor and project benchmark claims cited here are not independent validation.
- The final release gates have not run.
