# Evidence Base

Date checked: 2026-08-25

## Evidence Classes

Use three evidence classes.

- **A — Formal:** standards, peer-reviewed work, arXiv papers, or official
  research reports with stated methods.
- **B — Frontier-lab engineering:** first-party technical guidance, product
  documentation, or production reports from frontier labs.
- **C — Practitioner:** primary essays, talks, repositories, and implementation
  notes from named builders.

Class C can motivate a default or example. It cannot establish a universal or
quantitative claim. A universal rule needs A or B evidence plus local
validation. Local evidence can reject any imported default.

## Standards And Formal Research

- [W3C PROV-O](https://www.w3.org/TR/prov-o/), W3C Recommendation, 2013.
  Use `Entity`, `Activity`, `Agent`, `used`, `wasGeneratedBy`,
  `wasDerivedFrom`, attribution, and bundles as provenance references. Adopt
  only the subset needed by the project.
- [From Static Templates to Dynamic Runtime Graphs](https://arxiv.org/abs/2603.22386),
  Yue et al., 2026. Separate templates, run-specific realized graphs, and
  traces. Evaluate structure, cost, robustness, and variation.
- [StateFlow](https://arxiv.org/abs/2403.11322), Wu et al., 2024. Separate
  process grounding through states and transitions from local task solving.
- [MermaidFlow](https://arxiv.org/abs/2505.22967), Zheng et al., 2025. Use a
  typed, statically checked intermediate representation before candidate graph
  evolution. Static validity does not prove semantic or operational safety.
- [From Agent Traces to Trust](https://arxiv.org/abs/2606.04990), Wang et al.,
  2026. Treat execution provenance as a typed graph and evidence tracing as a
  support projection.
- [Selection Integrity for LLM Graph Memory](https://arxiv.org/abs/2606.12290),
  Fei et al., 2026. Authenticate selection structure, not only retrieved facts.
- [Adaptive Graph Pruning](https://arxiv.org/abs/2506.02951), Li et al., 2025,
  and [AgentPrune](https://arxiv.org/abs/2410.02506), Zhang et al., 2024.
  Agent and edge count are costs. Dense communication is not a quality metric.
- [From Local to Global: GraphRAG](https://arxiv.org/abs/2404.16130), Edge et
  al., 2024/2025. Graph retrieval can help global corpus questions. Compare it
  with lexical, vector, and hierarchical baselines for the local query class.

Reported paper results belong to their benchmark settings. They are not local
replications.

## Frontier-Lab Engineering Evidence

- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents),
  Anthropic, 2024. Start with the simplest successful pattern. Add routing,
  parallelism, evaluation loops, or autonomy only when the task warrants them.
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system),
  Anthropic, 2025. Use parallel agents for independent breadth-first work.
  Preserve artifacts and one synthesis owner. Do not generalize internal gains.
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents),
  Anthropic, 2025. Persist requirements, progress, restart state, version
  history, verification, and the next bounded unit of work.
- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents),
  Anthropic, 2026. Separate task, trial, grader, trace, environment outcome,
  agent harness, and evaluation harness. Inspect outcomes, not narration.
- [A practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/),
  OpenAI. Distinguish manager tool calls from handoffs. Retain one named owner
  of user interaction and completion.
- [OpenAI Agents SDK human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/).
  Persist resumable approval state without putting secrets in graph metadata.
- [Agent Development Kit](https://developers.googleblog.com/agent-development-kit-easy-to-build-multi-agent-applications/),
  Google, 2025. Declare deterministic and model-routed control separately.
  Parallel state writes need disjoint keys or a merge policy.
- [Magentic-One](https://www.microsoft.com/en-us/research/publication/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/),
  Microsoft Research, 2024. Record plan, progress, re-plan, retry, and isolated
  evaluation. More agents do not prove better results.
- [Talk like a graph](https://research.google/blog/talk-like-a-graph-encoding-graphs-for-large-language-models/),
  Google Research, 2024. Test graph serialization against the actual query
  class. Do not feed raw graph dumps to a model by default.
- [A Human-Inspired Reading Agent with Gist Memory](https://deepmind.google/research/publications/74917/),
  Google DeepMind, 2024. Treat summaries as navigation. Preserve recoverable
  links to source detail.

## Named Practitioner Evidence

### Andrej Karpathy

Karpathy has important formal research in other ML fields. No reviewed
Karpathy-authored paper was found that establishes current graph-engineering or
agent-harness practice. Use these as Class C sources:

- [Software 2.0](https://karpathy.medium.com/software-2-0-a64152b37c35),
  2017. Version the data, evaluators, interfaces, and infrastructure around
  probabilistic program components.
- [Software Is Changing (Again)](https://www.youtube.com/watch?v=LCEmiRjPEtQ),
  YC talk, 2025. Prefer partial autonomy, fast human verification, and
  agent-readable interfaces.
- [autoresearch](https://github.com/karpathy/autoresearch), 2026. Begin with a
  minimal bounded loop: declared mutable surface, immutable utilities and
  verifier, fixed budget, objective metric, experiment log, and keep-or-discard
  rule. It does not validate open-ended graph systems.

### Peter Steinberger

The user's “Pete Steinberg” likely refers to Peter Steinberger (`@steipete`).
This identity was not confirmed by the user. No relevant peer-reviewed or arXiv
publication by Steinberger was found. Pi is authored by Mario Zechner;
Steinberger is not Pi's author. Use these Class C sources:

- [Just Talk To It — the no-bs Way of Agentic Engineering](https://steipete.me/posts/just-talk-to-it),
  2025. Favor visible state, interruption, examples, low-context CLIs, tests,
  and environment feedback. Do not copy his concurrency practice as policy.
- [Shipping at Inference-Speed](https://steipete.me/posts/2025/shipping-at-inference-speed),
  2025. Prefer CLI-first, machine-readable, verifier-friendly capabilities.
- [OpenClaw agent runtime](https://github.com/openclaw/openclaw/blob/main/docs/concepts/agent.md),
  [multi-agent routing](https://github.com/openclaw/openclaw/blob/main/docs/concepts/multi-agent.md),
  and [sub-agents](https://github.com/openclaw/openclaw/blob/main/docs/tools/subagents.md).
  Treat workspace identity, durable sessions, routing identity, child lifecycle,
  completion events, and least-privilege tools as separate contracts.

Steinberger's short public question about moving from loops to graphs is a
vocabulary signal only. It is not a technical specification or research result.

## Local Evidence Rule

For every imported design rule, record:

- evidence class and source;
- mechanism it supports;
- known limit or counter-evidence;
- local hypothesis;
- baseline and held-out task;
- observed result;
- keep, revise, or reject decision.
