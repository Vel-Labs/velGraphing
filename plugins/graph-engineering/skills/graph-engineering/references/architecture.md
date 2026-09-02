# Graph Engineering Architecture

## Scope

This reference defines the common project graph model. Domain projects extend
it with local types and rules. They do not share one truth store.

## Five Graph Classes

| Class | Nodes | Edges | Main question |
| --- | --- | --- | --- |
| Execution | Tasks, tools, gates, events | Control, retry, join, successor | What can run next? |
| Communication | Agents, roles, sessions | Delegate, tool-call, handoff, notify | Who receives what context? |
| Knowledge | Entities, claims, sources, concepts | Supports, contradicts, describes | What is known and why? |
| Reasoning | Hypotheses, candidates, critiques | Derives, refines, compares, merges | Which candidate survives? |
| Provenance | Activities, agents, artifacts, evidence | Used, generated, attributed, derived | How did this result exist? |

Do not infer one class from another. A dependency edge does not establish factual
support. A support edge does not grant execution authority.

## Runtime Separation

Keep these records distinct:

1. **Template:** Reusable allowed structure and edit space.
2. **Realized graph:** Structure selected for one task or run.
3. **Trace:** Nodes and edges that actually executed.
4. **Mutable state:** Current values used by the runtime.
5. **Append-only events:** Observed transitions, tool calls, and results.
6. **Checkpoint:** Versioned recovery boundary across state and trace.

The trace and events prove observed local execution only when they come from the
runtime. A planned graph or model narration is not a trace.

## Common Exchange Envelope

Every exported node has:

- `record_type: node`;
- stable namespaced `id`;
- declared `node_type`;
- canonical `owner`;
- `source_ref` and optional digest;
- `evidence_state`: `observed`, `asserted`, `inferred`, `verified`, or
  `accepted`;
- `sensitivity`: `public`, `internal`, or `restricted`;
- `exportable`;
- `observed_at` in RFC 3339 form.

Every exported edge adds:

- `record_type: edge`;
- stable namespaced `id`;
- declared `edge_type`;
- `from` and `to` node IDs;
- `authority_ref` when the edge is authority-bearing or accepted.

Local extensions may add fields. They must not change the meaning of the common
fields.

## Edge Vocabulary

Start with the smallest useful set:

- Control: `depends_on`, `blocks`, `retries`, `joins`, `supersedes`.
- Communication: `delegates_to`, `calls_as_tool`, `hands_off_to`,
  `reports_to`.
- Knowledge: `supports`, `contradicts`, `describes`, `applies_to`.
- Reasoning: `derives`, `refines`, `critiques`, `merges`.
- Provenance: `used`, `produced`, `derived_from`, `verified_by`,
  `attributed_to`.
- Authority references: `requires_authority`, `approved_by_ref`,
  `acceptance_ref`.

Do not use `approved_by_ref` or `acceptance_ref` as the decision itself. The
named owner and canonical decision artifact remain authoritative.

## Control Topologies

- Direct loop: one agent or process, tools, exit rule.
- Chain: fixed ordered stages.
- Router: input selects one branch.
- Fan-out and join: independent branches with one merge owner.
- Orchestrator-workers: dynamic bounded decomposition.
- Evaluator-optimizer: candidate, rubric, revise, stop.
- State machine: explicit states and guarded transitions.
- Event graph: append-only events project into current views.

Choose the simplest topology that meets the acceptance need.

## Checkpoint Envelope

A recoverable checkpoint should name:

- run and node identity;
- graph definition version;
- completed action boundary;
- mutable state reference;
- trace and event position;
- pending authority or human decision;
- tool-call identity and external-effect receipt;
- restart method and compatibility marker;
- last verified outcome and next bounded work.

Do not replay an external effect from a checkpoint unless the effect is
idempotent, compensated, or proven not to have occurred.

## Federation Boundary

A project owns its namespace and filtered export. A folder or workspace graph
indexes approved exports and adds parent-owned cross-graph relations. It never
rewrites child truth. Use `graph-steward` for this boundary.
