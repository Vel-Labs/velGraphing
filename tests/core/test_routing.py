from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from packages.core import (
    Admission,
    Freshness,
    Provenance,
    RouteDecision,
    RouteFact,
    RouteOperation,
    RouteScope,
    RoutingEvidence,
    RoutingRequest,
    Sensitivity,
    TrustClass,
    resolve_route,
    AssertionKindV4,
    AssertionStatusV4,
    PolicyAssertionV4,
    RecommendationReasonV4,
    RecommendationTargetV4,
    RoutingPolicyV4,
    RoutingRecommendationV4,
    SourceIdentityV4,
    SourceSnapshotV4,
    recommend_route_v4,
    reject_untrusted_routing_payload_v4,
)
from packages.core.routing_v4 import (
    GRAPH_ENGINEERING_OPERATIONS,
    GRAPH_STEWARD_OPERATIONS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIGEST = "b" * 64
FROZEN_WHITE_SPACE_V4 = tuple(
    chr(code_point)
    for code_point in (
        *range(0x0009, 0x000E),
        0x0020,
        0x0085,
        0x00A0,
        0x1680,
        *range(0x2000, 0x200B),
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
    )
)
INVALID_PORTABLE_TEXT_V4 = tuple(
    dict.fromkeys(
        (
            "",
            *FROZEN_WHITE_SPACE_V4,
            "".join(FROZEN_WHITE_SPACE_V4),
            "\n",
            "\r",
            "\r\n",
            "\t",
            "\x00",
            "\x01",
            "\x1f",
            "\x7f",
            "\x80",
            "\x9f",
            "\u2028",
            "\u2029",
            "\ud800",
            "\udfff",
        )
    )
)
VALID_PORTABLE_CASES_V4 = (
    ("plain-id", "docs/route.txt"),
    ("café", "données/résumé.txt"),
    ("東京", "資料/グラフ.md"),
    ("alpha-東京-🙂", "mixed/資料-🙂.txt"),
    ("alpha\u00a0beta\u2028gamma", "unicode/alpha\u3000beta.txt"),
    ("e\u0301", "unicode/e\u0301.txt"),
    ("name with space", "folder with space/item.txt"),
)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class MemoryReader:
    def __init__(self, sources: dict[str, bytes], symlinks: tuple[str, ...] = ()) -> None:
        self.sources = sources
        self.symlinks = set(symlinks)

    def read_bytes(self, project_relative_path: str) -> bytes:
        return self.sources[project_relative_path]

    def is_symlink(self, project_relative_path: str) -> bool:
        return project_relative_path in self.symlinks


def v4_fixture(
    scope: RouteScope = RouteScope.PROJECT,
    operation: RouteOperation = RouteOperation.DESIGN,
    facts: tuple[RouteFact, ...] = (
        RouteFact.PROJECT_SCOPE,
        RouteFact.STRUCTURAL_NEED,
    ),
    assertion_status: AssertionStatusV4 = AssertionStatusV4.CURRENT,
    policy_id: str = "policy-1",
    source_path: str = "docs/route.txt",
    assertion_id_prefix: str = "route",
) -> tuple[RoutingPolicyV4, SourceSnapshotV4, MemoryReader]:
    raw = b"scope operation structural advisory source\n"
    source = SourceIdentityV4(source_path, len(raw), sha256(raw))
    snapshot = SourceSnapshotV4((source,))
    definitions = [
        (f"{assertion_id_prefix}-operation", AssertionKindV4.OPERATION, operation.value),
        (f"{assertion_id_prefix}-scope", AssertionKindV4.SCOPE, scope.value),
        *(
            (f"{assertion_id_prefix}-fact-{fact.value}", AssertionKindV4.STRUCTURAL_FACT, fact.value)
            for fact in facts
        ),
    ]
    assertions = []
    for assertion_id, kind, value in sorted(definitions):
        values: dict[str, object] = {
            "assertion_id": assertion_id,
            "source_path": source.path,
            "source_sha256": source.sha256,
            "byte_start": 0,
            "byte_end": len(raw),
            "excerpt_sha256": sha256(raw),
            "kind": kind,
            "value": value,
            "status": assertion_status if "-fact-" in assertion_id else AssertionStatusV4.CURRENT,
        }
        assertions.append(PolicyAssertionV4(**values))  # type: ignore[arg-type]
    source_set_sha256 = sha256(
        json.dumps(
            {"source_identities": [source.sha256]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    policy = RoutingPolicyV4(policy_id, source_set_sha256, tuple(assertions))
    return policy, snapshot, MemoryReader({source.path: raw})


def evidence(evidence_id: str, fact: RouteFact, **changes: object) -> RoutingEvidence:
    values = {
        "evidence_id": evidence_id,
        "fact": fact,
        "provenance": Provenance("contracts/route.md", DIGEST, "L1-L4", True),
        "trust": TrustClass.VERIFIED_SOURCE,
        "freshness": Freshness.CURRENT,
        "sensitivity": Sensitivity.PUBLIC,
        "admission": Admission.VERIFIER,
        "eligible": True,
        "agent_generated": False,
        "verifier_promoted": False,
    }
    values.update(changes)
    return RoutingEvidence(**values)  # type: ignore[arg-type]


def request(
    *items: RoutingEvidence,
    scope: RouteScope = RouteScope.PROJECT,
    operation: RouteOperation = RouteOperation.DESIGN,
    request_id: str = "R-1",
) -> RoutingRequest:
    return RoutingRequest(request_id, scope, operation, tuple(items))


class PositiveRouteTests(unittest.TestCase):
    def test_routes_project_structural_work(self) -> None:
        decision = resolve_route(
            request(
                evidence("scope", RouteFact.PROJECT_SCOPE),
                evidence("need", RouteFact.STRUCTURAL_NEED),
            )
        )
        self.assertEqual("graph_engineering", decision.route)
        self.assertFalse(decision.fail_closed)
        self.assertEqual(("need", "scope"), decision.used_evidence_ids)

    def test_assess_can_route_on_graph_worthiness_before_graph_exists(self) -> None:
        decision = resolve_route(
            request(
                evidence("scope", RouteFact.PROJECT_SCOPE),
                evidence("worthy", RouteFact.GRAPH_WORTHY),
                operation=RouteOperation.ASSESS,
            )
        )
        self.assertEqual("graph_engineering", decision.route)
        self.assertEqual("project_assessment_route", decision.reason)

    def test_non_assess_operation_requires_structural_need(self) -> None:
        decision = resolve_route(
            request(
                evidence("scope", RouteFact.PROJECT_SCOPE),
                evidence("worthy", RouteFact.GRAPH_WORTHY),
                operation=RouteOperation.DESIGN,
            )
        )
        self.assertEqual("defer", decision.route)
        self.assertEqual("incomplete_evidence", decision.reason)

    def test_routes_federation_work(self) -> None:
        decision = resolve_route(
            request(
                evidence("scope", RouteFact.FEDERATION_SCOPE),
                evidence("registry", RouteFact.REGISTRY_REFERENCE),
                evidence("action", RouteFact.CROSS_PROJECT_ACTION),
                scope=RouteScope.FEDERATION,
                operation=RouteOperation.RECONCILE,
            )
        )
        self.assertEqual("graph_steward", decision.route)
        self.assertFalse(decision.fail_closed)

    def test_routes_verified_direct_baseline_to_no_skill(self) -> None:
        decision = resolve_route(
            request(
                evidence("scope", RouteFact.PROJECT_SCOPE),
                evidence("baseline", RouteFact.DIRECT_BASELINE_SUFFICIENT),
                operation=RouteOperation.ASSESS,
            )
        )
        self.assertEqual("no_skill", decision.route)
        self.assertFalse(decision.fail_closed)

    def test_verifier_promoted_agent_evidence_can_route(self) -> None:
        promoted = {
            "agent_generated": True,
            "verifier_promoted": True,
            "trust": TrustClass.POLICY_ADMITTED,
            "admission": Admission.VERIFIER,
        }
        decision = resolve_route(
            request(
                evidence("scope", RouteFact.PROJECT_SCOPE, **promoted),
                evidence("need", RouteFact.STRUCTURAL_NEED, **promoted),
            )
        )
        self.assertEqual("graph_engineering", decision.route)


class FailClosedRouteTests(unittest.TestCase):
    def test_unknown_scope_fails_closed(self) -> None:
        decision = resolve_route(
            request(
                evidence("scope", RouteFact.PROJECT_SCOPE),
                scope=RouteScope.UNKNOWN,
            )
        )
        self.assertEqual("defer", decision.route)
        self.assertTrue(decision.fail_closed)
        self.assertEqual("unknown_scope", decision.reason)

    def test_incomplete_federation_evidence_fails_closed(self) -> None:
        decision = resolve_route(
            request(
                evidence("scope", RouteFact.FEDERATION_SCOPE),
                evidence("registry", RouteFact.REGISTRY_REFERENCE),
                scope=RouteScope.FEDERATION,
                operation=RouteOperation.INSPECT,
            )
        )
        self.assertEqual("defer", decision.route)
        self.assertEqual("incomplete_evidence", decision.reason)

    def test_conflicting_facts_fail_closed(self) -> None:
        conflicts = (
            request(
                evidence("project", RouteFact.PROJECT_SCOPE),
                evidence("federation", RouteFact.FEDERATION_SCOPE),
            ),
            request(
                evidence("scope", RouteFact.PROJECT_SCOPE),
                evidence("need", RouteFact.STRUCTURAL_NEED),
                evidence("baseline", RouteFact.DIRECT_BASELINE_SUFFICIENT),
            ),
        )
        for item in conflicts:
            with self.subTest(item=item):
                decision = resolve_route(item)
                self.assertEqual("defer", decision.route)
                self.assertEqual("conflicting_evidence", decision.reason)

    def test_untrusted_consequential_evidence_causes_divergence(self) -> None:
        blocked = (
            replace(
                evidence("need", RouteFact.STRUCTURAL_NEED),
                provenance=Provenance("contracts/route.md", DIGEST, "L1", False),
            ),
            replace(
                evidence("need", RouteFact.STRUCTURAL_NEED),
                freshness=Freshness.STALE,
            ),
            replace(
                evidence("need", RouteFact.STRUCTURAL_NEED),
                agent_generated=True,
                trust=TrustClass.AGENT_GENERATED,
                admission=Admission.NONE,
                verifier_promoted=False,
            ),
        )
        for item in blocked:
            with self.subTest(item=item):
                decision = resolve_route(
                    request(evidence("scope", RouteFact.PROJECT_SCOPE), item)
                )
                self.assertEqual("defer", decision.route)
                self.assertEqual("graph_engineering", decision.full_route)
                self.assertEqual("defer", decision.authenticated_route)
                self.assertEqual(("need",), decision.divergent_evidence_ids)
                self.assertEqual("authenticated_route_divergence", decision.reason)

    def test_defer_never_activates_a_skill(self) -> None:
        decision = resolve_route(request())
        self.assertEqual("defer", decision.route)
        self.assertNotIn(decision.route, {"graph_engineering", "graph_steward"})
        self.assertTrue(decision.fail_closed)




class AdvisoryRoutingV4Tests(unittest.TestCase):
    def recommend(self, **changes: object) -> RoutingRecommendationV4:
        policy, snapshot, reader = v4_fixture(**changes)  # type: ignore[arg-type]
        return recommend_route_v4(policy, snapshot, reader)

    def test_project_federation_assessment_and_no_skill_recommendations(self) -> None:
        project = self.recommend()
        assessment = self.recommend(
            operation=RouteOperation.ASSESS,
            facts=(RouteFact.PROJECT_SCOPE, RouteFact.GRAPH_WORTHY),
        )
        federation = self.recommend(
            scope=RouteScope.FEDERATION,
            operation=RouteOperation.RECONCILE,
            facts=(RouteFact.FEDERATION_SCOPE, RouteFact.REGISTRY_REFERENCE, RouteFact.CROSS_PROJECT_ACTION),
        )
        no_skill = self.recommend(
            operation=RouteOperation.ASSESS,
            facts=(RouteFact.PROJECT_SCOPE, RouteFact.DIRECT_BASELINE_SUFFICIENT),
        )
        self.assertEqual(
            ("graph_engineering", "graph_engineering", "graph_steward", "no_skill"),
            tuple(item.recommendation for item in (project, assessment, federation, no_skill)),
        )
        for item in (project, assessment, federation, no_skill):
            self.assertEqual("advisory", item.contract_kind)
            self.assertIs(False, item.grants_authority)
            self.assertIs(False, item.may_activate_skill)
            self.assertEqual("none", item.write_authority)
            self.assertIs(True, item.requires_separate_host_task_authority)

    def test_non_current_and_conflicting_assertions_defer(self) -> None:
        for status in (AssertionStatusV4.STALE, AssertionStatusV4.UNKNOWN, AssertionStatusV4.INELIGIBLE):
            with self.subTest(status=status):
                item = self.recommend(assertion_status=status)
                self.assertEqual("defer", item.recommendation)
                self.assertEqual("non_current_assertion", item.reason)
                self.assertTrue(item.rejected_assertion_ids)
        conflict = self.recommend(
            facts=(RouteFact.PROJECT_SCOPE, RouteFact.STRUCTURAL_NEED, RouteFact.DIRECT_BASELINE_SUFFICIENT)
        )
        self.assertEqual("defer", conflict.recommendation)
        self.assertEqual("conflicting_evidence", conflict.reason)

    def test_exact_bytes_ranges_source_set_and_symlinks_are_enforced(self) -> None:
        policy, snapshot, reader = v4_fixture()
        path = snapshot.sources[0].path
        for bad_reader in (
            MemoryReader({path: reader.sources[path] + b"changed"}),
            MemoryReader(reader.sources, (path,)),
        ):
            with self.subTest(reader=bad_reader), self.assertRaises(ValueError):
                recommend_route_v4(policy, snapshot, bad_reader)
        with self.assertRaises(ValueError):
            recommend_route_v4(replace(policy, source_set_sha256="0" * 64), snapshot, reader)
        changed_assertion = replace(policy.assertions[0], excerpt_sha256="0" * 64)
        with self.assertRaises(ValueError):
            recommend_route_v4(replace(policy, assertions=(changed_assertion, *policy.assertions[1:])), snapshot, reader)

    def test_recursive_payload_rejection_covers_lists_tuples_cycles_and_objects(self) -> None:
        reject_untrusted_routing_payload_v4({"safe": [{"note": ("text", 1, False)}]})
        for key in ("scope", "operation", "route", "recommendation", "fact", "trust", "freshness", "sensitivity", "admission", "eligible", "agent_generated", "verifier_promoted", "authority", "permission", "activate", "write_authority"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                reject_untrusted_routing_payload_v4({"outer": [{"inner": ({key: "x"},)}]})
        cyclic: list[object] = []
        cyclic.append(cyclic)
        with self.assertRaises(ValueError):
            reject_untrusted_routing_payload_v4(cyclic)
        for unsupported in ({"safe": {"set"}}, {"safe": object()}, {"safe": lambda: None}):
            with self.subTest(unsupported=unsupported), self.assertRaises(TypeError):
                reject_untrusted_routing_payload_v4(unsupported)

    def test_identities_order_round_trip_and_exact_types(self) -> None:
        policy, snapshot, reader = v4_fixture()
        recommendation = recommend_route_v4(policy, snapshot, reader)
        self.assertEqual(snapshot, SourceSnapshotV4.from_dict(snapshot.to_dict()))
        self.assertEqual(policy, RoutingPolicyV4.from_dict(policy.to_dict()))
        self.assertEqual(recommendation, RoutingRecommendationV4.from_dict(recommendation.to_dict()))
        with self.assertRaises(ValueError):
            SourceIdentityV4("../escape", 1, "1" * 64)
        with self.assertRaises(ValueError):
            SourceIdentityV4("a", True, "1" * 64)
        with self.assertRaises(ValueError):
            PolicyAssertionV4("a", "a", "1" * 64, False, 1, "2" * 64, AssertionKindV4.SCOPE, "project", AssertionStatusV4.CURRENT)
        forged = recommendation.to_dict()
        forged["grants_authority"] = 0
        with self.assertRaises(ValueError):
            RoutingRecommendationV4.from_dict(forged)
        second = SourceIdentityV4("z", 1, "2" * 64)
        with self.assertRaises(ValueError):
            SourceSnapshotV4((second, snapshot.sources[0]))
        with self.assertRaises(ValueError):
            SourceSnapshotV4((snapshot.sources[0], snapshot.sources[0]))
        with self.assertRaises(ValueError):
            RoutingPolicyV4(
                policy.policy_id,
                policy.source_set_sha256,
                tuple(reversed(policy.assertions)),
            )
        with self.assertRaises(ValueError):
            RoutingPolicyV4(
                policy.policy_id,
                policy.source_set_sha256,
                (policy.assertions[0], policy.assertions[0]),
            )
        unsorted = recommendation.to_dict()
        unsorted["used_assertion_ids"] = list(reversed(recommendation.used_assertion_ids))
        with self.assertRaises(ValueError):
            RoutingRecommendationV4.from_dict(unsorted)
        overlap = recommendation.to_dict()
        overlap.update(
            recommendation="defer",
            reason="non_current_assertion",
            rejected_assertion_ids=[recommendation.used_assertion_ids[0]],
        )
        with self.assertRaises(ValueError):
            RoutingRecommendationV4.from_dict(overlap)

    def test_portable_text_and_identifier_adversarial_matrix(self) -> None:
        policy, snapshot, reader = v4_fixture()
        assertion = policy.assertions[0]
        recommendation = recommend_route_v4(policy, snapshot, reader)
        for invalid in INVALID_PORTABLE_TEXT_V4:
            rejected_constructors = (
                lambda value=invalid: replace(policy, policy_id=value),
                lambda value=invalid: replace(assertion, assertion_id=value),
                lambda value=invalid: replace(recommendation, used_assertion_ids=(value,)),
                lambda value=invalid: replace(
                    recommendation,
                    recommendation="defer",
                    reason="non_current_assertion",
                    used_assertion_ids=(),
                    rejected_assertion_ids=(value,),
                ),
            )
            for constructor in rejected_constructors:
                with self.subTest(invalid=repr(invalid), constructor=constructor), self.assertRaises(ValueError):
                    constructor()

        for embedded_control in ("ok\x00id", "ok\x1fid", "ok\x7fid", "ok\x85id", "ok\ud800id"):
            with self.subTest(embedded=repr(embedded_control)), self.assertRaises(ValueError):
                replace(policy, policy_id=embedded_control)

    def test_portable_path_adversarial_matrix(self) -> None:
        path_failures = (
            "",
            "/absolute/path",
            "folder\\item",
            ".",
            "..",
            "folder/./item",
            "folder/../item",
            "folder//item",
            "folder/",
            *(f"folder/{invalid}/item" for invalid in INVALID_PORTABLE_TEXT_V4),
            "folder/ok\x00item",
            "folder/ok\x1fitem",
            "folder/ok\x7fitem",
            "folder/ok\x85item",
            "folder/ok\ud800item",
        )
        for invalid_path in path_failures:
            with self.subTest(path=repr(invalid_path)), self.assertRaises(ValueError):
                SourceIdentityV4(invalid_path, 1, "1" * 64)

    def test_portable_valid_matrix_preserves_unicode_and_reconstructs(self) -> None:
        schemas = self._load_v4_schemas()
        for identifier, path in VALID_PORTABLE_CASES_V4:
            with self.subTest(identifier=identifier, path=path):
                policy, snapshot, reader = v4_fixture(
                    policy_id=identifier,
                    source_path=path,
                    assertion_id_prefix=identifier,
                )
                recommendation = recommend_route_v4(policy, snapshot, reader)
                self.assertEqual(identifier, policy.policy_id)
                self.assertEqual(path, snapshot.sources[0].path)
                self.assertTrue(all(item.assertion_id.startswith(identifier) for item in policy.assertions))
                self._assert_runtime_serialization_shapes(
                    schemas, policy, snapshot, recommendation
                )
                self.assertEqual(snapshot, SourceSnapshotV4.from_dict(snapshot.to_dict()))
                self.assertEqual(policy, RoutingPolicyV4.from_dict(policy.to_dict()))
                self.assertEqual(
                    recommendation,
                    RoutingRecommendationV4.from_dict(recommendation.to_dict()),
                )

        composed, _, _ = v4_fixture(policy_id="é")
        decomposed, _, _ = v4_fixture(policy_id="e\u0301")
        self.assertEqual("é", composed.policy_id)
        self.assertEqual("e\u0301", decomposed.policy_id)
        self.assertNotEqual(composed.policy_id, decomposed.policy_id)
        self.assertNotEqual(composed.policy_sha256, decomposed.policy_sha256)

    def test_v3_is_a_non_callable_tombstone_and_recommendation_has_no_activation_path(self) -> None:
        import packages.core as core
        import packages.core.routing_v3 as routing_v3

        self.assertEqual((), routing_v3.__all__)
        public_v3 = {name: value for name, value in vars(routing_v3).items() if not name.startswith("__")}
        self.assertEqual({}, public_v3)
        self.assertFalse(any(name.endswith("V3") for name in core.__all__))
        for rejected_name in (
            "resolve_verified_route", "verify_routing_context",
            "reject_untrusted_routing_payload",
        ):
            self.assertNotIn(rejected_name, core.__all__)
        recommendation = self.recommend()
        self.assertFalse(any(callable(value) for value in vars(recommendation).values()))

    def test_v4_schemas_are_closed_and_match_runtime_contracts(self) -> None:
        schemas = {
            name: json.loads((PROJECT_ROOT / "contracts" / "core" / name).read_text(encoding="utf-8"))
            for name in (
                "routing-policy-v4.schema.json",
                "routing-snapshot-v4.schema.json",
                "routing-recommendation-v4.schema.json",
            )
        }
        for schema in schemas.values():
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self._assert_objects_closed(schema)

        policy, snapshot, reader = v4_fixture()
        recommendation = recommend_route_v4(policy, snapshot, reader)
        runtime_and_schema = (
            (snapshot.to_dict(), schemas["routing-snapshot-v4.schema.json"]),
            (policy.to_dict(), schemas["routing-policy-v4.schema.json"]),
            (recommendation.to_dict(), schemas["routing-recommendation-v4.schema.json"]),
        )
        for payload, schema in runtime_and_schema:
            self.assertEqual(set(payload), set(schema["properties"]))
            self.assertEqual(set(payload), set(schema["required"]))

        source_schema = schemas["routing-snapshot-v4.schema.json"]["$defs"]["source"]
        assertion_schema = schemas["routing-policy-v4.schema.json"]["$defs"]["assertion"]
        self.assertEqual(set(snapshot.sources[0].to_dict()), set(source_schema["properties"]))
        self.assertEqual(set(source_schema["properties"]), set(source_schema["required"]))
        self.assertEqual(set(policy.assertions[0].to_dict()), set(assertion_schema["properties"]))
        self.assertEqual(set(assertion_schema["properties"]), set(assertion_schema["required"]))

        self.assertEqual(
            {item.value for item in AssertionKindV4},
            set(assertion_schema["properties"]["kind"]["enum"]),
        )
        self.assertEqual(
            {item.value for item in AssertionStatusV4},
            set(assertion_schema["properties"]["status"]["enum"]),
        )
        assertion_values = {
            rule["if"]["properties"]["kind"]["const"]:
                set(rule["then"]["properties"]["value"]["enum"])
            for rule in assertion_schema["allOf"]
        }
        self.assertEqual({item.value for item in RouteScope}, assertion_values["scope"])
        self.assertEqual({item.value for item in RouteOperation}, assertion_values["operation"])
        self.assertEqual({item.value for item in RouteFact}, assertion_values["structural_fact"])

        recommendation_schema = schemas["routing-recommendation-v4.schema.json"]
        recommendation_properties = recommendation_schema["properties"]
        self.assertEqual(
            {item.value for item in RecommendationTargetV4},
            set(recommendation_properties["recommendation"]["enum"]),
        )
        self.assertEqual(
            {item.value for item in RecommendationReasonV4},
            set(recommendation_properties["reason"]["enum"]),
        )
        self.assertEqual(
            {item.value for item in RouteScope} | {None},
            set(recommendation_properties["scope"]["enum"]),
        )
        self.assertEqual(
            {item.value for item in RouteOperation} | {None},
            set(recommendation_properties["operation"]["enum"]),
        )
        recommendation_rules = {
            rule["if"]["properties"]["recommendation"]["const"]: rule["then"]["properties"]
            for rule in recommendation_schema["allOf"]
            if "recommendation" in rule["if"]["properties"]
        }
        self.assertEqual(
            {item.value for item in GRAPH_ENGINEERING_OPERATIONS},
            set(recommendation_rules["graph_engineering"]["operation"]["enum"]),
        )
        self.assertEqual(
            {item.value for item in GRAPH_STEWARD_OPERATIONS},
            set(recommendation_rules["graph_steward"]["operation"]["enum"]),
        )
        self.assertEqual(
            {item.value for item in RouteOperation},
            set(recommendation_rules["no_skill"]["operation"]["enum"]),
        )
        constants = {
            "contract_kind": "advisory",
            "grants_authority": False,
            "may_activate_skill": False,
            "write_authority": "none",
            "requires_separate_host_task_authority": True,
        }
        for field, expected in constants.items():
            self.assertEqual(expected, recommendation_properties[field]["const"])
            self.assertEqual(expected, recommendation.to_dict()[field])

        for schema in schemas.values():
            self.assertIn("Runtime PortableTextV4 and PortablePathV4 validation is mandatory", schema["$comment"])
            self.assertIn("does not claim lexical admission", schema["$comment"])
        lexical_shape_nodes = (
            schemas["routing-snapshot-v4.schema.json"]["$defs"]["source"]["properties"]["path"],
            schemas["routing-policy-v4.schema.json"]["properties"]["policy_id"],
            assertion_schema["properties"]["assertion_id"],
            assertion_schema["properties"]["source_path"],
            assertion_schema["properties"]["value"],
            recommendation_properties["used_assertion_ids"]["items"],
            recommendation_properties["rejected_assertion_ids"]["items"],
        )
        for node in lexical_shape_nodes:
            self.assertEqual(1, node["minLength"])
            self.assertNotIn("pattern", node)

        self.assertEqual(snapshot, SourceSnapshotV4.from_dict(snapshot.to_dict()))
        self.assertEqual(policy, RoutingPolicyV4.from_dict(policy.to_dict()))
        self.assertEqual(
            recommendation,
            RoutingRecommendationV4.from_dict(recommendation.to_dict()),
        )

    def test_schema_shape_valid_runtime_lexically_invalid_payloads_fail_closed(self) -> None:
        schemas = self._load_v4_schemas()
        policy, snapshot, reader = v4_fixture()
        recommendation = recommend_route_v4(policy, snapshot, reader)
        stale_policy, stale_snapshot, stale_reader = v4_fixture(
            assertion_status=AssertionStatusV4.STALE
        )
        stale_recommendation = recommend_route_v4(
            stale_policy, stale_snapshot, stale_reader
        )

        snapshot_payload = json.loads(json.dumps(snapshot.to_dict()))
        snapshot_payload["sources"][0]["path"] = "folder//item"
        policy_id_payload = json.loads(json.dumps(policy.to_dict()))
        policy_id_payload["policy_id"] = "\u00a0"
        assertion_id_payload = json.loads(json.dumps(policy.to_dict()))
        assertion_id_payload["assertions"][0]["assertion_id"] = "bad\x7fid"
        assertion_path_payload = json.loads(json.dumps(policy.to_dict()))
        assertion_path_payload["assertions"][0]["source_path"] = "folder\\item"
        used_payload = json.loads(json.dumps(recommendation.to_dict()))
        used_payload["used_assertion_ids"][0] = "\u2028"
        rejected_payload = json.loads(json.dumps(stale_recommendation.to_dict()))
        rejected_payload["rejected_assertion_ids"][0] = "\ud800"

        layered_cases = (
            (snapshot_payload, schemas["routing-snapshot-v4.schema.json"], SourceSnapshotV4.from_dict),
            (policy_id_payload, schemas["routing-policy-v4.schema.json"], RoutingPolicyV4.from_dict),
            (assertion_id_payload, schemas["routing-policy-v4.schema.json"], RoutingPolicyV4.from_dict),
            (assertion_path_payload, schemas["routing-policy-v4.schema.json"], RoutingPolicyV4.from_dict),
            (used_payload, schemas["routing-recommendation-v4.schema.json"], RoutingRecommendationV4.from_dict),
            (rejected_payload, schemas["routing-recommendation-v4.schema.json"], RoutingRecommendationV4.from_dict),
        )
        for payload, schema, reconstruct in layered_cases:
            with self.subTest(payload=repr(payload)):
                self.assertEqual(set(schema["properties"]), set(schema["required"]))
                self.assertEqual(set(schema["properties"]), set(payload))
                with self.assertRaises(ValueError):
                    reconstruct(payload)

    def test_recommendation_schema_and_runtime_relationships_agree(self) -> None:
        schema = json.loads(
            (PROJECT_ROOT / "contracts" / "core" / "routing-recommendation-v4.schema.json")
            .read_text(encoding="utf-8")
        )
        valid = [
            self.recommend().to_dict(),
            self.recommend(
                operation=RouteOperation.ASSESS,
                facts=(RouteFact.PROJECT_SCOPE, RouteFact.GRAPH_WORTHY),
            ).to_dict(),
            self.recommend(
                scope=RouteScope.FEDERATION,
                operation=RouteOperation.RECONCILE,
                facts=(RouteFact.FEDERATION_SCOPE, RouteFact.REGISTRY_REFERENCE, RouteFact.CROSS_PROJECT_ACTION),
            ).to_dict(),
            self.recommend(
                operation=RouteOperation.ASSESS,
                facts=(RouteFact.PROJECT_SCOPE, RouteFact.DIRECT_BASELINE_SUFFICIENT),
            ).to_dict(),
            self.recommend(assertion_status=AssertionStatusV4.STALE).to_dict(),
        ]
        for payload in valid:
            with self.subTest(valid=payload["recommendation"]):
                self.assertTrue(self._schema_relationships_accept(schema, payload))
                self.assertEqual(payload, RoutingRecommendationV4.from_dict(payload).to_dict())

        project = valid[0]
        federation = valid[2]
        non_current = valid[4]
        invalid: list[dict[str, object]] = []
        for field, value in (
            ("scope", "federation"),
            ("operation", "inspect"),
            ("reason", "project_assessment_route"),
            ("rejected_assertion_ids", ["rejected"]),
        ):
            item = dict(project)
            item[field] = value
            invalid.append(item)
        for field, value in (("scope", "project"), ("operation", "design")):
            item = dict(federation)
            item[field] = value
            invalid.append(item)
        no_skill_wrong_scope = dict(valid[3])
        no_skill_wrong_scope["scope"] = "federation"
        invalid.append(no_skill_wrong_scope)
        non_current_without_rejected = dict(non_current)
        non_current_without_rejected["rejected_assertion_ids"] = []
        invalid.append(non_current_without_rejected)
        rejected_without_non_current = dict(project)
        rejected_without_non_current.update(
            recommendation="defer",
            reason="incomplete_evidence",
            rejected_assertion_ids=["rejected"],
        )
        invalid.append(rejected_without_non_current)

        for payload in invalid:
            with self.subTest(invalid=payload):
                self.assertFalse(self._schema_relationships_accept(schema, payload))
                with self.assertRaises(ValueError):
                    RoutingRecommendationV4.from_dict(payload)

    def _load_v4_schemas(self) -> dict[str, dict[str, object]]:
        return {
            name: json.loads(
                (PROJECT_ROOT / "contracts" / "core" / name).read_text(
                    encoding="utf-8"
                )
            )
            for name in (
                "routing-policy-v4.schema.json",
                "routing-snapshot-v4.schema.json",
                "routing-recommendation-v4.schema.json",
            )
        }

    def _assert_runtime_serialization_shapes(
        self,
        schemas: dict[str, dict[str, object]],
        policy: RoutingPolicyV4,
        snapshot: SourceSnapshotV4,
        recommendation: RoutingRecommendationV4,
    ) -> None:
        serializations = (
            (snapshot.to_dict(), schemas["routing-snapshot-v4.schema.json"]),
            (policy.to_dict(), schemas["routing-policy-v4.schema.json"]),
            (recommendation.to_dict(), schemas["routing-recommendation-v4.schema.json"]),
        )
        for payload, schema in serializations:
            self.assertEqual(set(payload), set(schema["properties"]))
            self.assertEqual(set(payload), set(schema["required"]))
        source_schema = schemas["routing-snapshot-v4.schema.json"]["$defs"]["source"]
        assertion_schema = schemas["routing-policy-v4.schema.json"]["$defs"]["assertion"]
        self.assertEqual(set(snapshot.sources[0].to_dict()), set(source_schema["properties"]))
        self.assertEqual(set(policy.assertions[0].to_dict()), set(assertion_schema["properties"]))
        recommendation_schema = schemas["routing-recommendation-v4.schema.json"]
        recommendation_payload = recommendation.to_dict()
        for field in (
            "contract_kind",
            "grants_authority",
            "may_activate_skill",
            "write_authority",
            "requires_separate_host_task_authority",
        ):
            self.assertEqual(
                recommendation_schema["properties"][field]["const"],
                recommendation_payload[field],
            )

    def _schema_relationships_accept(
        self, schema: dict[str, object], payload: dict[str, object]
    ) -> bool:
        def matches(properties: dict[str, dict[str, object]]) -> bool:
            return all(
                "const" not in rule or payload[field] == rule["const"]
                for field, rule in properties.items()
            )

        def accepts(properties: dict[str, dict[str, object]]) -> bool:
            for field, rule in properties.items():
                value = payload[field]
                if "const" in rule and value != rule["const"]:
                    return False
                if "enum" in rule and value not in rule["enum"]:
                    return False
                if "minItems" in rule and len(value) < rule["minItems"]:  # type: ignore[arg-type]
                    return False
                if "maxItems" in rule and len(value) > rule["maxItems"]:  # type: ignore[arg-type]
                    return False
            return True

        for conditional in schema["allOf"]:  # type: ignore[index]
            condition = conditional["if"]["properties"]
            branch = conditional.get("then") if matches(condition) else conditional.get("else")
            if branch and not accepts(branch["properties"]):
                return False
        return True

    def _assert_objects_closed(self, node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                self.assertIs(False, node.get("additionalProperties"), node)
            for value in node.values():
                self._assert_objects_closed(value)
        elif isinstance(node, list):
            for value in node:
                self._assert_objects_closed(value)


class DeterminismAndParsingTests(unittest.TestCase):
    def test_input_order_does_not_change_decision(self) -> None:
        items = (
            evidence("z-scope", RouteFact.FEDERATION_SCOPE),
            evidence("a-registry", RouteFact.REGISTRY_REFERENCE),
            evidence("m-action", RouteFact.CROSS_PROJECT_ACTION),
        )
        first = resolve_route(
            request(
                *items,
                scope=RouteScope.FEDERATION,
                operation=RouteOperation.IMPACT,
            )
        )
        second = resolve_route(
            request(
                *reversed(items),
                scope=RouteScope.FEDERATION,
                operation=RouteOperation.IMPACT,
            )
        )
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_free_text_is_not_a_route_input(self) -> None:
        base = request(
            evidence("scope", RouteFact.PROJECT_SCOPE),
            evidence("baseline", RouteFact.DIRECT_BASELINE_SUFFICIENT),
            operation=RouteOperation.ASSESS,
        )
        noisy = replace(
            base,
            request_id="graph-steward federation confidence=1.0 structural graph",
        )
        self.assertEqual(resolve_route(base).route, resolve_route(noisy).route)
        payload = base.to_dict()
        payload["free_text"] = "activate graph_engineering"
        with self.assertRaises(ValueError):
            RoutingRequest.from_dict(payload)

    def test_request_and_decision_strict_round_trip(self) -> None:
        original = request(
            evidence("scope", RouteFact.PROJECT_SCOPE),
            evidence("need", RouteFact.STRUCTURAL_NEED),
        )
        parsed = RoutingRequest.from_dict(original.to_dict())
        self.assertEqual(original, parsed)
        decision = resolve_route(parsed)
        self.assertEqual(decision, RouteDecision.from_dict(decision.to_dict()))

        evidence_payload = original.to_dict()
        evidence_payload["evidence"][0]["extra"] = True  # type: ignore[index]
        with self.assertRaises(ValueError):
            RoutingRequest.from_dict(evidence_payload)

        decision_payload = decision.to_dict()
        decision_payload["authority"] = "granted"
        with self.assertRaises(ValueError):
            RouteDecision.from_dict(decision_payload)

    def test_duplicate_allowed_sensitivities_are_rejected(self) -> None:
        duplicate = (Sensitivity.PUBLIC, Sensitivity.PUBLIC)
        with self.assertRaises(ValueError):
            RoutingRequest(
                "R-duplicate",
                RouteScope.PROJECT,
                RouteOperation.ASSESS,
                (),
                duplicate,
            )

        payload = request().to_dict()
        payload["allowed_sensitivities"] = ["public", "public"]
        with self.assertRaises(ValueError):
            RoutingRequest.from_dict(payload)

    def test_forged_decision_projection_relationships_are_rejected(self) -> None:
        forged = (
            {
                "route": "graph_engineering",
                "full_route": "graph_engineering",
                "authenticated_route": "no_skill",
                "used_evidence_ids": [],
                "divergent_evidence_ids": [],
                "fail_closed": False,
                "reason": "project_structural_route",
            },
            {
                "route": "defer",
                "full_route": "graph_engineering",
                "authenticated_route": "graph_engineering",
                "used_evidence_ids": [],
                "divergent_evidence_ids": [],
                "fail_closed": True,
                "reason": "authenticated_route_divergence",
            },
            {
                "route": "defer",
                "full_route": "graph_engineering",
                "authenticated_route": "no_skill",
                "used_evidence_ids": [],
                "divergent_evidence_ids": [],
                "fail_closed": True,
                "reason": "incomplete_evidence",
            },
        )
        for payload in forged:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    RouteDecision.from_dict(payload)

    def test_blank_decision_evidence_ids_are_rejected(self) -> None:
        for field in ("used_evidence_ids", "divergent_evidence_ids"):
            payload = {
                "route": "defer",
                "full_route": "graph_engineering",
                "authenticated_route": "defer",
                "used_evidence_ids": [],
                "divergent_evidence_ids": [],
                "fail_closed": True,
                "reason": "authenticated_route_divergence",
            }
            payload[field] = ["  "]
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    RouteDecision.from_dict(payload)

        with self.assertRaises(ValueError):
            RouteDecision(
                route="no_skill",
                full_route="no_skill",
                authenticated_route="no_skill",
                used_evidence_ids=("",),
                divergent_evidence_ids=(),
                fail_closed=False,
                reason="direct_baseline_route",
            )

    def test_v2_schemas_close_every_object(self) -> None:
        for name in (
            "routing-request-v2.schema.json",
            "routing-decision-v2.schema.json",
        ):
            schema = json.loads(
                (PROJECT_ROOT / "contracts" / "core" / name).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                "https://json-schema.org/draft/2020-12/schema", schema["$schema"]
            )
            self._assert_objects_closed(schema)

    def _assert_objects_closed(self, node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                self.assertIs(False, node.get("additionalProperties"), node)
            for value in node.values():
                self._assert_objects_closed(value)
        elif isinstance(node, list):
            for value in node:
                self._assert_objects_closed(value)


if __name__ == "__main__":
    unittest.main()
