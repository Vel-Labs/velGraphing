# Quality And Evaluation Gates

## Validation Ladder

### Gate 0: Worthiness

- Name the question the graph must answer.
- Name the direct, list, table, chain, state-machine, lexical, or vector
  baseline.
- Identify the cost or failure that the graph should reduce.
- Reject the graph if no measurable advantage is expected.

### Gate 1: Ownership

- Every type and record has one canonical owner.
- Derived views point to canonical sources.
- The graph does not copy another board, ledger, wiki, or repository as truth.
- Cross-owner decisions use references, not copied authority.

### Gate 2: Structure

- IDs are stable and namespaced.
- Node and edge types are declared.
- Endpoint types are valid.
- Acyclic relation classes contain no cycles.
- Generic relations do not control work or consequential retrieval.

### Gate 3: Provenance And Trust

- Every derived record has a source reference and evidence state.
- Accepted records name authority evidence.
- Edge writes have provenance and authorization.
- Consequential selection runs on the authorized subgraph.
- Summaries retain recoverable source detail.

### Gate 4: Execution

- Template, realized graph, trace, state, events, and checkpoints are distinct.
- Routes state whether they are deterministic or model-selected.
- Parallel branches have disjoint writes or a merge owner.
- Retries, budgets, stop rules, and external-effect idempotency are explicit.
- Outcome evidence comes from the environment, not agent narration.

### Gate 5: Context And Communication

- Each agent receives only required context and tools.
- Artifact references replace repeated summaries where practical.
- Manager tool calls and execution handoffs use different edge types.
- Communication density and token cost are measured.
- A branch is kept only when its removal reduces useful quality.

### Gate 6: Retrieval And Serialization

- Evaluate lexical, vector, hierarchical, and graph retrieval where applicable.
- Test adjacency, edge-list, path, neighborhood, and summary views when models
  must reason over the graph.
- Measure answer quality, source support, context tokens, and latency.
- Do not assume one serialization works for every query class.

### Gate 7: Recovery

- A checkpoint identifies the completed action boundary and definition version.
- Conversation, execution, filesystem, and board references align.
- Pending human authority remains pending after resume.
- External effects use idempotency, compensation, or separate confirmation.
- Resume is tested from a real checkpoint fixture.

### Gate 8: Export And Federation

- Export defaults to deny.
- Types and sensitivity are allowlisted.
- Private payloads and secrets are excluded.
- Export digest and definition version are recorded.
- Parent admission remains `not_run` until `graph-steward` accepts it.

## Evaluation Design

Measure at least:

- acceptance rate or task quality;
- critical-path latency;
- model, token, and tool cost;
- retry and invalid-transition counts;
- recovery success;
- evidence completeness and audit time;
- graph construction and storage cost;
- communication density;
- unused nodes and edges;
- state-race or reconciliation failures.

For stochastic behavior, use repeated trials when the decision stakes justify
them. Do not require an identical trajectory unless process compliance is the
behavior under test.

## Ablations

Compare:

1. Direct baseline.
2. Minimal loop or state machine.
3. Fixed graph.
4. Candidate graph change.
5. Component-removal variants.

Remove each optional agent, edge class, memory layer, retrieval path, and judge
in turn. Keep it only when an important result degrades or a required safety
boundary disappears.

## Promotion Decision

Accept a graph candidate only when:

- focused structural validation passes;
- held-out observable behavior meets the stated threshold;
- cost and latency remain within budget;
- provenance and authority stay intact;
- recovery and export boundaries pass where applicable;
- the owning project accepts the change.

A source-linked proposal, passing schema check, or attractive visualization is
not runtime, federation, provider, release, or product acceptance proof.
