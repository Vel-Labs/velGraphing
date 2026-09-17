"""Offline Jev contracts and failure behavior. No live provider calls."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("velgraphing_jev", ROOT / "packages/core/jev.py")
jev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jev)


class JevTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, text in {"a.py": "# background\nx = 1\n", "b.py": "def cancel():\n    return 'cancelled'\n", "c.py": "assert cancel() == 'cancelled'\n"}.items():
            (self.root / name).write_text(text)
        self.packet = jev.capture(self.root, "Find cancellation and its test", ["a.py:1:2", "b.py:1:2", "c.py:1:1"])
        self.prepared = jev.prepare(self.packet, self.root)

    def response(self, levels=(0, 2, 1)):
        legend = {str(i): criterion for i, criterion in enumerate(jev._rubric_criteria())}
        return {"model": jev.DEFAULT_MODEL, "answers": {
            f"candidate_{i}": {"type": "score", "score": level,
                "probabilities": {str(j): float(j == level) for j in range(3)},
                "legend": legend, "confidence": 1.0}
            for i, level in enumerate(levels)},
            "usage": {"input_tokens": 1200, "output_tokens": 0}}

    def evaluate(self, **kwargs):
        settings = {"mode": "rerank", "allow_network": True,
                    "approved_request_sha256": self.prepared["request_sha256"],
                    "transport": Mock(return_value=self.response())}
        settings.update(kwargs)
        return jev.evaluate(self.packet, self.root, **settings)

    def replay(self, response=None):
        return {"schema_version": "velgraphing-jev-replay-v1",
                "request_sha256": self.prepared["request_sha256"],
                "response": self.response() if response is None else response}

    def test_off_needs_no_files_key_or_transport(self):
        transport = Mock(side_effect=AssertionError("called"))
        with patch.object(jev, "_read_source", side_effect=AssertionError("read")):
            result = jev.evaluate(self.packet, Path("/does-not-exist"), transport=transport)
        self.assertEqual(result["status"], "off")
        self.assertEqual(result["order"], ["c0", "c1", "c2"])
        transport.assert_not_called()

    def test_network_requires_explicit_flag(self):
        transport = Mock()
        result = self.evaluate(allow_network=False, transport=transport)
        self.assertEqual(result["reason"], "network_not_authorized")
        transport.assert_not_called()

    def test_request_requires_exact_approval(self):
        transport = Mock()
        result = self.evaluate(approved_request_sha256="0" * 64, transport=transport)
        self.assertEqual(result["reason"], "request_not_approved")
        transport.assert_not_called()

    def test_missing_key_does_not_send(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(jev, "_http") as http:
            result = self.evaluate(transport=None)
        self.assertEqual(result["reason"], "missing_or_invalid_api_key")
        http.assert_not_called()

    def test_rerank_is_complete_permutation(self):
        result = self.evaluate()
        self.assertEqual(result["order"], ["c1", "c2", "c0"])
        self.assertEqual(set(result["order"]), set(result["baseline_order"]))
        self.assertFalse(result["authority_bearing"])
        self.assertFalse(result["sufficient"])
        self.assertTrue(result["source_revalidated"])

    def test_shadow_does_not_change_effective_order(self):
        result = self.evaluate(mode="shadow")
        self.assertEqual(result["order"], result["baseline_order"])
        self.assertEqual(result["suggested_order"], ["c1", "c2", "c0"])

    def test_required_candidate_stays_in_its_slot(self):
        self.packet["candidates"][1]["required"] = True
        self.prepared = jev.prepare(self.packet, self.root)
        result = self.evaluate()
        self.assertEqual(result["order"], ["c2", "c1", "c0"])
        self.assertEqual(result["required_ids"], ["c1"])

    def test_all_required_preserves_order(self):
        for candidate in self.packet["candidates"]:
            candidate["required"] = True
        self.prepared = jev.prepare(self.packet, self.root)
        self.assertEqual(self.evaluate()["order"], ["c0", "c1", "c2"])

    def test_ties_keep_baseline_order(self):
        result = self.evaluate(transport=Mock(return_value=self.response((1, 1, 1))))
        self.assertEqual(result["order"], ["c0", "c1", "c2"])

    def test_all_zero_scores_do_not_prune_or_claim_sufficiency(self):
        result = self.evaluate(transport=Mock(return_value=self.response((0, 0, 0))))
        self.assertEqual(result["order"], ["c0", "c1", "c2"])
        self.assertFalse(result["sufficient"])

    def test_questions_use_structured_rubrics_and_explicit_state_references(self):
        for i, question in enumerate(self.prepared["request"]["questions"].values()):
            self.assertEqual(question["type"], "score")
            self.assertIsInstance(question["instructions"], dict)
            self.assertEqual(question["instructions"]["candidate_ref"], f"candidates[{i}]")
            self.assertEqual(question["criteria"], jev._rubric_criteria())

    def test_swapped_or_mutated_legend_falls_back(self):
        canonical = {str(i): criterion for i, criterion in enumerate(jev._rubric_criteria())}
        legends = (
            {"0": canonical["1"], "1": canonical["0"], "2": canonical["2"]},
            {**canonical, "2": {**canonical["2"], "includes": "mutated"}},
        )
        for legend in legends:
            response = self.response()
            response["answers"]["candidate_0"]["legend"] = legend
            result = self.evaluate(replay=self.replay(response))
            self.assertEqual(result["status"], "fallback")
            self.assertEqual(result["reason"], "invalid_score_legend")
            self.assertEqual(result["order"], result["baseline_order"])

    def test_same_payload_has_same_hash(self):
        self.assertEqual(self.prepared["request_sha256"], jev.prepare(self.packet, self.root)["request_sha256"])

    def test_changed_query_invalidates_approval(self):
        self.packet["query"] = "A different question"
        self.assertEqual(self.evaluate()["reason"], "request_not_approved")

    def test_changed_candidate_order_invalidates_approval(self):
        self.packet["candidates"].reverse()
        self.assertEqual(self.evaluate()["reason"], "request_not_approved")

    def test_changed_source_rejected_before_provider(self):
        (self.root / "a.py").write_text("changed\n")
        transport = Mock()
        result = self.evaluate(transport=transport)
        self.assertEqual(result["reason"], "source_digest_mismatch")
        transport.assert_not_called()

    def test_changed_source_during_provider_discards_suggestion(self):
        def transport(*_):
            (self.root / "a.py").write_text("changed\n")
            return self.response()
        result = self.evaluate(transport=transport)
        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["order"], result["baseline_order"])
        self.assertFalse(result["source_revalidated"])

    def test_provider_receives_detached_state(self):
        original = copy.deepcopy(self.packet)
        def transport(payload, _timeout):
            payload["state"]["task"]["query"] = "mutated request"
            return self.response()
        self.evaluate(transport=transport)
        self.assertEqual(self.packet, original)

    def test_provider_errors_do_not_leak_source_or_key(self):
        result = self.evaluate(transport=Mock(side_effect=RuntimeError("secret-key source contents")))
        self.assertEqual(result["status"], "fallback")
        self.assertNotIn("secret-key", json.dumps(result))
        self.assertNotIn("source contents", json.dumps(result))
        self.assertEqual(result["attempted_calls"], 1)

    def test_no_automatic_retries(self):
        transport = Mock(side_effect=TimeoutError())
        self.evaluate(transport=transport)
        self.assertEqual(transport.call_count, 1)

    def test_observation_omits_raw_query_and_source(self):
        encoded = json.dumps(self.evaluate())
        self.assertNotIn(self.packet["query"], encoded)
        self.assertNotIn("return 'cancelled'", encoded)
        self.assertIn("query_sha256", encoded)

    def test_valid_replay_is_labeled_and_never_sends(self):
        with patch.object(jev, "_http", side_effect=AssertionError("live call")):
            result = self.evaluate(replay=self.replay(), transport=None, allow_network=False)
        self.assertEqual(result["execution"], "replay")
        self.assertEqual(result["attempted_calls"], 0)
        self.assertIsNone(result["usage"])
        self.assertEqual(result["replayed_usage"]["input_tokens"], 1200)
        self.assertEqual(result["order"], ["c1", "c2", "c0"])

    def test_replay_for_different_request_falls_back(self):
        replay = self.replay()
        replay["request_sha256"] = "0" * 64
        result = self.evaluate(replay=replay)
        self.assertEqual(result["reason"], "replay_request_mismatch")
        self.assertEqual(result["order"], result["baseline_order"])

    def test_missing_and_extra_answers_rejected(self):
        for extra in (False, True):
            response = self.response()
            if extra:
                response["answers"]["surprise"] = response["answers"]["candidate_0"]
            else:
                del response["answers"]["candidate_0"]
            with self.subTest(extra=extra):
                self.assertEqual(self.evaluate(replay=self.replay(response))["reason"], "provider_question_mismatch")

    def test_invalid_numeric_scores_rejected(self):
        for value in (True, None, "2", -1, 3, float("nan"), float("inf")):
            response = self.response()
            response["answers"]["candidate_0"]["score"] = value
            with self.subTest(value=value):
                self.assertEqual(self.evaluate(replay=self.replay(response))["status"], "fallback")

    def test_invalid_probabilities_rejected(self):
        for probabilities in ({"0": 0.2, "1": 0.2, "2": 0.2}, {"0": 1}, {"0": True, "1": 0, "2": 0}, {"0": -1, "1": 1, "2": 1}):
            response = self.response()
            response["answers"]["candidate_0"]["probabilities"] = probabilities
            with self.subTest(probabilities=probabilities):
                self.assertEqual(self.evaluate(replay=self.replay(response))["status"], "fallback")

    def test_score_must_match_distribution(self):
        response = self.response()
        response["answers"]["candidate_0"]["score"] = 1
        self.assertEqual(self.evaluate(replay=self.replay(response))["reason"], "inconsistent_score")

    def test_invalid_confidence_rejected(self):
        response = self.response()
        response["answers"]["candidate_0"]["confidence"] = 2
        self.assertEqual(self.evaluate(replay=self.replay(response))["reason"], "invalid_provider_number")

    def test_missing_legend_rejected(self):
        response = self.response()
        del response["answers"]["candidate_0"]["legend"]
        self.assertEqual(self.evaluate(replay=self.replay(response))["reason"], "invalid_score_levels")

    def test_invalid_usage_rejected(self):
        for usage in ({}, {"input_tokens": True, "output_tokens": 0}, {"input_tokens": -1, "output_tokens": 0}):
            response = self.response()
            response["usage"] = usage
            with self.subTest(usage=usage):
                self.assertEqual(self.evaluate(replay=self.replay(response))["reason"], "invalid_provider_usage")

    def test_pinned_model_must_match(self):
        response = self.response()
        response["model"] = "jev-99.0.0"
        self.assertEqual(self.evaluate(replay=self.replay(response))["reason"], "provider_model_mismatch")

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(jev.JevError):
            jev.decode(b'{"x": 1, "x": 2}')

    def test_nonfinite_json_rejected(self):
        for raw in (b'{"x": NaN}', b'{"x": Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(jev.JevError):
                jev.decode(raw)

    def test_duplicate_candidate_ids_rejected(self):
        self.packet["candidates"][1]["id"] = "c0"
        with self.assertRaises(jev.JevError):
            jev.validate_packet(self.packet)

    def test_invalid_required_flag_rejected(self):
        self.packet["candidates"][0]["required"] = "yes"
        with self.assertRaises(jev.JevError):
            jev.validate_packet(self.packet)

    def test_bool_span_rejected(self):
        self.packet["candidates"][0]["byte_start"] = False
        with self.assertRaises(jev.JevError):
            jev.validate_packet(self.packet)

    def test_traversal_and_sensitive_paths_rejected(self):
        for path in ("../x.py", "/tmp/x.py", "a//x.py", "a/./x.py", "x\\y.py", ".env", ".env.local", ".ssh/config.txt", "keys/private.pem", "secrets/x.json", "file.bin"):
            packet = copy.deepcopy(self.packet)
            packet["candidates"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(jev.JevError):
                jev.validate_packet(packet)

    def test_source_symlink_rejected(self):
        (self.root / "alias.py").symlink_to(self.root / "a.py")
        with self.assertRaises(jev.JevError):
            jev.capture(self.root, "q", ["alias.py:1:1"])

    def test_parent_symlink_rejected(self):
        (self.root / "alias").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(jev.JevError):
            jev.capture(self.root, "q", ["alias/a.py:1:1"])

    def test_hardlink_rejected(self):
        os.link(self.root / "a.py", self.root / "alias.py")
        with self.assertRaises(jev.JevError):
            jev.capture(self.root, "q", ["alias.py:1:1"])

    def test_non_utf8_span_rejected(self):
        (self.root / "raw.py").write_bytes(b"\xff\n")
        with self.assertRaises(jev.JevError):
            jev.capture(self.root, "q", ["raw.py:1:1"])

    def test_unicode_boundary_split_rejected(self):
        (self.root / "utf.py").write_text("\u00e9\n")
        packet = jev.capture(self.root, "q", ["utf.py:1:1"])
        packet["candidates"][0]["byte_start"] = 1
        with self.assertRaises(jev.JevError):
            jev.prepare(packet, self.root)

    def test_excerpt_budget_rejected(self):
        self.packet["candidates"][0]["byte_end"] = 5000
        with self.assertRaises(jev.JevError):
            jev.validate_packet(self.packet)

    def test_candidate_budget_rejected(self):
        self.packet["candidates"] *= 30
        with self.assertRaises(jev.JevError):
            jev.validate_packet(self.packet)

    def test_request_budget_rejected(self):
        with patch.object(jev, "MAX_REQUEST_BYTES", 10), self.assertRaises(jev.JevError):
            jev.prepare(self.packet, self.root)

    def test_source_budget_rejected(self):
        with patch.object(jev, "MAX_SOURCE_BYTES", 1), self.assertRaises(jev.JevError):
            jev.prepare(self.packet, self.root)

    def test_line_range_rejected(self):
        for span in ("a.py:0:1", "a.py:2:1", "a.py:1:99", "a.py"):
            with self.subTest(span=span), self.assertRaises(jev.JevError):
                jev.capture(self.root, "q", [span])

    def test_unknown_required_id_rejected(self):
        with self.assertRaises(jev.JevError):
            jev.capture(self.root, "q", ["a.py:1:1"], ["c9"])

    def test_invalid_model_rejected(self):
        with self.assertRaises(jev.JevError):
            jev.prepare(self.packet, self.root, "https://example.com")

    def test_invalid_timeout_rejected(self):
        for timeout in (0, 61, True, float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(jev.JevError):
                self.evaluate(timeout_s=timeout)

    def test_status_cli_is_offline_and_does_not_print_key(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "private-api-value"}), patch("sys.stdout", output), patch.object(jev, "_http", side_effect=AssertionError("network")):
            self.assertEqual(jev.main(["status"]), 0)
        self.assertNotIn("private-api-value", output.getvalue())
        self.assertTrue(json.loads(output.getvalue())["api_key_present"])

    def test_cli_defaults_to_off(self):
        packet_path = self.root / "packet.json"
        packet_path.write_bytes(jev.canonical(self.packet))
        completed = subprocess.run([sys.executable, str(ROOT / "packages/core/jev.py"), "evaluate", str(packet_path), "--root", str(self.root)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(completed.stdout)["status"], "off")

    def test_cli_fallback_is_nonzero_and_still_returns_baseline(self):
        packet_path = self.root / "packet.json"
        packet_path.write_bytes(jev.canonical(self.packet))
        output = io.StringIO()
        with patch("sys.stdout", output):
            status = jev.main(["evaluate", str(packet_path), "--root", str(self.root), "--mode", "shadow"])
        self.assertEqual(status, 3)
        self.assertEqual(json.loads(output.getvalue())["order"], ["c0", "c1", "c2"])

    def test_http_pins_endpoint_disables_redirects_and_uses_timeout(self):
        fake = Mock()
        fake.status = 200
        fake.read.return_value = jev.canonical(self.response())
        context = Mock()
        context.__enter__ = Mock(return_value=fake)
        context.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = context
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}), patch.object(jev.urllib.request, "build_opener", return_value=opener) as build:
            jev._http(self.prepared["request"], 3)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, jev.ENDPOINT)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 3)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertIsInstance(build.call_args.args[1], jev._NoRedirect)
        self.assertIsNone(build.call_args.args[1].redirect_request(None, None, 302, "", {}, "https://evil.invalid"))
        self.assertEqual(fake.read.call_args.args[0], jev.MAX_RESPONSE_BYTES + 1)

    def test_http_errors_are_sanitized(self):
        error = urllib.error.HTTPError(jev.ENDPOINT, 429, "secret details", {}, io.BytesIO(b"secret source"))
        opener = Mock()
        opener.open.side_effect = error
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}), patch.object(jev.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(jev.JevError, "^provider_http_429$"):
                jev._http(self.prepared["request"], 3)
        self.assertEqual(opener.open.call_count, 1)


if __name__ == "__main__":
    unittest.main()
