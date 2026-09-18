"""Real Jev evaluator integration, local synthetic source, no credentials/network."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/benchmarks'))
from time_to_correct import Answer, Grade, Trial, Budget
from time_to_correct_jev import evaluate_offline, load_jev


def identity():
    return dict(run_id='fixture-run', trial_id='jev-fixture', task_id='cancel', arm='D',
                repository_id='synthetic', repository_commit='a'*40,
                source_snapshot_sha256='b'*64, dirty_state_sha256='c'*64,
                answer_model='fixture-answer', reasoning='none', prompt_sha256='d'*64,
                rubric_sha256='e'*64, rubric_version='fixture-v1', answer_lane_id='answer-lane')


class JevTimingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'a.py').write_text('BACKGROUND = 1\n')
        (self.root/'b.py').write_text('def cancel():\n    return True\n')
        (self.root/'c.py').write_text('assert cancel()\n')
        self.module = load_jev(ROOT)
        self.packet = self.module.capture(self.root, 'Find cancellation and its test.',
                                         ['a.py:1:1', 'b.py:1:2', 'c.py:1:1'], ['c2'])
        prepared = self.module.prepare(self.packet, self.root)
        legend = {str(i): v for i, v in enumerate(self.module._rubric_criteria())}
        self.envelope = dict(schema_version='velgraphing-jev-replay-v1',
                             request_sha256=prepared['request_sha256'], response={
            'model': self.module.DEFAULT_MODEL,
            'answers': {f'candidate_{i}': dict(type='score', score=score, confidence=1.0,
                 probabilities={str(k): int(k == score) for k in range(3)}, legend=legend)
                 for i, score in enumerate([0,2,2])},
            'usage': {'input_tokens': 99, 'output_tokens': 7}})

    def run_fixture(self, *, provider=False, mode='rerank', stale=False,
                    retain_packet_telemetry=False):
        trial = Trial(identity(), Budget(0, 5_000_000_000), execution='fixture')
        seen = []
        def prep(t, n):
            if stale:
                (self.root/'a.py').write_text('CHANGED = True\n')
            # Patching getenv to fail does not inspect or enumerate real values.
            with patch('os.environ.get', side_effect=AssertionError('credential lookup prohibited')):
                result = evaluate_offline(t, ROOT, self.packet, self.root,
                                          envelope=self.envelope, mode=mode,
                                          fixture_provider=provider,
                                          retain_packet_telemetry=retain_packet_telemetry)
            seen.append(result)
            return result['order']
        def answer(t, order, n):
            return Answer(' '.join(order))
        def grade(t, answer, n):
            return Grade(True, 1, 1, True, 0, 'independent-grader', 'e'*64)
        result = trial.run(prep, answer, grade)
        return result, seen

    def test_replay_real_evaluator_has_no_provider_interval(self):
        result, observations = self.run_fixture()
        self.assertEqual(result['terminal_reason'], 'passed')
        self.assertEqual(observations[0]['order'], ['c1','c0','c2'])
        self.assertEqual(result['phases']['provider']['status'], 'not_applicable')
        self.assertEqual(result['phases']['jev_preparation']['status'], 'observed')
        self.assertEqual(result['phases']['source_revalidation']['status'], 'observed')
        self.assertEqual(result['phases']['response_validation']['status'], 'observed')
        self.assertEqual(len(result['attempts'][0]['source_operations']), 6)
        self.assertIsNone(result['total_input_tokens'])
        self.assertEqual(result['attempts'][0]['model_calls'][0]['provenance'], 'fixture')

    def test_fixture_transport_times_local_work_not_a_live_call(self):
        result, observations = self.run_fixture(provider=True)
        self.assertEqual(result['terminal_reason'], 'passed')
        self.assertEqual(result['phases']['provider']['status'], 'observed')
        self.assertEqual(observations[0]['execution'], 'injected_transport')
        self.assertEqual(result['attempts'][0]['jev_observation']['measurement_execution'], 'fixture_provider')
        self.assertEqual(observations[0]['order'], ['c1','c0','c2'])

    def test_observation_retains_source_free_v3_packet_telemetry(self):
        result, _ = self.run_fixture(provider=True, retain_packet_telemetry=True)
        observation = result['attempts'][0]['jev_observation']
        prepared = self.module.prepare(self.packet, self.root)
        self.assertEqual(set(observation), {
            'status', 'reason', 'baseline_order', 'order', 'required_ids',
            'candidate_set_sha256', 'request_sha256', 'source_revalidated',
            'resolved_model', 'request_bytes', 'shared_state_bytes',
            'questions_bytes', 'candidate_count', 'question_count',
            'rubric_version', 'shared_state_tokens', 'question_suffix_tokens',
            'source_bytes_verified', 'scores', 'elapsed_ms', 'attempted_calls',
            'measurement_execution',
        })
        self.assertEqual(observation['request_bytes'], prepared['request_bytes'])
        self.assertEqual(observation['shared_state_bytes'],
                         len(self.module.canonical(prepared['request']['state'])))
        self.assertEqual(observation['questions_bytes'],
                         len(self.module.canonical(prepared['request']['questions'])))
        self.assertEqual((observation['candidate_count'], observation['question_count']), (3, 3))
        self.assertEqual(observation['rubric_version'], self.module.RUBRIC_VERSION)
        self.assertEqual(observation['source_bytes_verified'],
                         2 * sum((self.root / name).stat().st_size for name in ('a.py', 'b.py', 'c.py')))
        self.assertIsNone(observation['shared_state_tokens'])
        self.assertIsNone(observation['question_suffix_tokens'])
        self.assertEqual(observation['scores'][0]['probabilities'], {'0': 1.0, '1': 0.0, '2': 0.0})
        retained = json.dumps(observation, sort_keys=True)
        for private in ('Find cancellation', 'a.py', 'BACKGROUND = 1', str(self.root)):
            self.assertNotIn(private, retained)

    def test_shadow_preserves_every_candidate_and_order(self):
        result, observations = self.run_fixture(mode='shadow')
        self.assertEqual(result['terminal_reason'], 'passed')
        self.assertEqual(observations[0]['order'], ['c0','c1','c2'])

    def test_off_does_no_jev_source_reads(self):
        result, observations = self.run_fixture(mode='off')
        self.assertEqual(result['terminal_reason'], 'passed')
        self.assertEqual(observations[0]['order'], ['c0','c1','c2'])
        self.assertEqual(result['attempts'][0]['source_operations'], [])
        self.assertEqual(result['attempts'][0]['model_calls'], [])

    def test_stale_source_retains_baseline_and_failure_evidence(self):
        result, observations = self.run_fixture(stale=True)
        self.assertEqual(result['terminal_reason'], 'passed')  # Synthetic order grading only; not a source-supported answer claim.
        self.assertEqual(observations[0]['status'], 'fallback')
        self.assertEqual(observations[0]['reason'], 'source_digest_mismatch')
        self.assertEqual(observations[0]['order'], ['c0','c1','c2'])
        self.assertEqual(result['phases']['source_revalidation']['status'], 'missing')

    def test_required_position_lock_is_measured_not_disabled(self):
        result, observations = self.run_fixture(provider=True)
        self.assertEqual(observations[0]['order'][2], 'c2')
        self.assertEqual(observations[0]['required_ids'], ['c2'])
        self.assertEqual(set(observations[0]['order']), set(observations[0]['baseline_order']))

    def test_lock_removal_is_only_a_counterfactual_fixture(self):
        _, locked = self.run_fixture(provider=True)
        self.packet['candidates'][2]['required'] = False
        # Required policy is local, not sent to Jev. Verify the request binding
        # rather than silently changing the fixture response to favor an outcome.
        self.envelope['request_sha256'] = self.module.prepare(self.packet, self.root)['request_sha256']
        _, unlocked = self.run_fixture(provider=True)
        self.assertEqual(locked[0]['order'], ['c1','c0','c2'])
        self.assertEqual(unlocked[0]['order'], ['c1','c2','c0'])
        self.assertEqual(set(locked[0]['order']), set(unlocked[0]['order']))

    def test_isolated_modules_do_not_change_production_functions(self):
        original_prepare = self.module.prepare
        result, _ = self.run_fixture()
        self.assertIs(self.module.prepare, original_prepare)
        self.assertEqual(result['terminal_reason'], 'passed')

    def test_live_execution_cannot_use_fixture_bridge(self):
        trial = Trial(identity(), Budget(0, 5_000_000_000), execution='observed')
        with self.assertRaisesRegex(ValueError, 'offline_bridge_requires_fixture_or_replay'):
            evaluate_offline(trial, ROOT, self.packet, self.root, envelope=self.envelope)


if __name__ == '__main__':
    unittest.main()
