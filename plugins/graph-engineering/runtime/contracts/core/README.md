# Core Contracts

These schemas describe the serialized V1 record, edge, provenance, and
selection-result interfaces. The Python core is an enforcement consumer of
these contracts. A graph is a derived view. It does not replace its cited
source.

The V2 routing request and decision schemas define a deterministic structural
skill route. The request accepts only typed scope, operation, evidence, and
sensitivity fields. It does not accept task prose, skill names, keywords,
graph nouns, confidence scores, or other free text as routing inputs.

Consequential selection requires verified provenance, an allowed trust class,
current freshness, permitted sensitivity, explicit admission, and eligibility.
Export requires a separate explicit policy and an item-level export grant.
Agent-generated routing evidence also requires explicit verifier promotion.
Any full-versus-authenticated route divergence returns fail-closed `defer`.
`defer` does not activate a skill or grant authority.

The V3 routing design is rejected. Its Python module is a non-callable
historical tombstone. The V3 schemas are historical source records. They do not
define a supported authority, activation, context, admission, resolver,
capability, or token surface.

The V4 policy and snapshot schemas bind supplied policy assertions to supplied
source identities and exact bytes. The recommendation schema records
deterministic advisory planning metadata. Its closed constants state that it
grants no authority, cannot activate a skill, grants no write authority, and
requires separate host task authority. A `current` assertion can participate.
A consequential `stale`, `unknown`, or `ineligible` assertion causes `defer`.

V4 proves only consistency among caller-supplied inputs. It does not prove
policy ownership, human intent, task authority, admission, replay protection,
trust, freshness against a clock, or hostile-host containment. V2 remains a
historical verification surface. No routing generation can replace explicit
current task authority for skill activation or writes.

The source-grounded retrieval V1 schema defines typed repository tags, typed
prompt facets, bounded retrieval hits, and a graph-or-defer result. It is a
knowledge-retrieval contract. It is not the V2 or V4 authority router. Semantic
expansion can select only values that already exist in the source-bound
repository vocabulary. Exact, sparse, wiki, and graph channels use
deterministic rank fusion. `match_score` and facet coverage are ranking
diagnostics. They are not probabilities, authority, or answer confidence.

Graph expansion permits at most one allowlisted typed hop. Every returned
context span is verified against the supplied source snapshot. An insufficient
result can recommend source paths, but it cannot read them. Only an explicit
caller allowlist can activate the existing same-snapshot direct fallback.

The source-bound evidence-index V1 contract adds a closed authority vocabulary,
caller-supplied proof obligations, minimal file cards, and byte-bound evidence
items. Cards contain only deterministic record identity, source identity, and
canonical anchor tags. Every evidence range binds to the supplied source hash
and excerpt hash. Hop-one graph evidence is valid only when it covers an
obligation; an unanchored neighbor is not context. Retrieval is sufficient only
when every obligation has anchored evidence. Uncovered source hints can be
recommended for the caller's explicit same-snapshot fallback.
