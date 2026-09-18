"""Controller tests use a deterministic clock, never a model or network."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/benchmarks'))
from time_to_correct import (Answer, Budget, Grade, MeasurementError, Trial, digest,
                             load_completed_trials, save_completed_trial, summarize, union_ns)


class Clock:
    def __init__(self):
        self.value = 0
    def __call__(self):
        return self.value
    def advance(self, amount):
        self.value += amount


def identity(trial_id='trial1', arm='A'):
    return dict(run_id='run1', trial_id=trial_id, task_id='task1', arm=arm,
                repository_id='fixture-repository', repository_commit='a' * 40,
                source_snapshot_sha256='b' * 64, dirty_state_sha256='c' * 64,
                answer_model='fixture-model', reasoning='none', prompt_sha256='d' * 64,
                rubric_sha256='e' * 64, rubric_version='v1', answer_lane_id='answer-lane')


def grade(passed=True):
    return Grade(passed, 1.0 if passed else 0.0, 1.0, True, 0, 'independent-grader', 'e' * 64)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.trial = Trial(identity(), Budget(2, 1000), clock=self.clock, execution='fixture')
    def execute(self, passes=(True,), prepare=None, answer=None, grader=None):
        def prep(t, n):
            with t.phase('candidate_discovery'):
                self.clock.advance(10)
            return b'actual request'
        def generate(t, request, n):
            t.context(request)
            t.usage('answer' + str(n), 'answer', provenance='fixture', model='fixture-model',
                    input_tokens=100, output_tokens=10, cached_input_tokens=20,
                    reasoning_output_tokens=3, cost_usd=0.01)
            self.clock.advance(20)
            return Answer('supported answer')
        def scoring(t, output, n):
            self.clock.advance(5)
            return grade(passes[min(n, len(passes) - 1)])
        return self.trial.run(prepare or prep, answer or generate, grader or scoring)

    def test_deadline_origin_is_acceptance_not_constructor_setup(self):
        class SetupClock(Clock):
            def __init__(self):
                super().__init__()
                self.calls = 0
            def __call__(self):
                self.calls += 1
                if self.calls == 2:
                    self.value = 900
                return self.value
        self.clock = SetupClock()
        self.trial = Trial(identity(), Budget(0, 100), clock=self.clock, execution='fixture')
        result = self.execute()
        self.assertEqual(result['terminal_reason'], 'passed')
        self.assertEqual(result['first_answer_ns'], 30)
        self.assertEqual(result['user_visible_wall_ns'], 35)
        self.assertEqual(result['events'][0]['t_ns'], 0)

    def test_first_answer_and_confirmed_correct_are_distinct(self):
        result = self.execute()
        self.assertEqual(result['first_answer_ns'], 30)
        self.assertEqual(result['first_correct_answer_ns'], 30)
        self.assertEqual(result['confirmed_time_to_correct_ns'], 35)
        self.assertEqual(result['user_visible_wall_ns'], 35)
        self.assertTrue(result['first_pass_correct'])

    def test_repair_includes_previous_attempt_and_grade(self):
        result = self.execute((False, True))
        self.assertEqual(result['first_answer_ns'], 30)
        self.assertEqual(result['first_correct_answer_ns'], 65)
        self.assertEqual(result['confirmed_time_to_correct_ns'], 70)
        self.assertEqual(len(result['attempts']), 2)
        self.assertFalse(result['first_pass_correct'])
        self.assertEqual(result['phases']['repair']['inclusive_union_ns'], 35)
        self.assertEqual(result['observed_active_execution_ns'], 70)  # Not 105 with repair double-counted.

    def test_phase_observed_in_only_one_repair_attempt_is_partial(self):
        def prep(t, n):
            if n == 0:
                with t.phase('candidate_discovery'):
                    self.clock.advance(10)
            return b'actual request'
        result = self.execute((False, True), prepare=prep)
        phase = result['phases']['candidate_discovery']
        self.assertEqual(phase['status'], 'partial')
        self.assertFalse(phase['complete'])
        self.assertEqual(phase['attempts_total'], 2)
        self.assertEqual(phase['observed_attempts'], 1)
        self.assertEqual(phase['missing_attempts'], 1)
        self.assertEqual(phase['inclusive_union_ns'], 10)

    def test_budget_exhaustion_keeps_failed_attempts(self):
        result = self.execute((False,))
        self.assertEqual(len(result['attempts']), 3)
        self.assertEqual(result['terminal_reason'], 'repair_budget_exhausted')
        self.assertIsNone(result['confirmed_time_to_correct_ns'])
        self.assertEqual(result['user_visible_wall_ns'], 105)

    def test_no_repair_budget(self):
        self.trial = Trial(identity(), Budget(0, 1000), clock=self.clock, execution='fixture')
        result = self.execute((False,))
        self.assertEqual(len(result['attempts']), 1)
        self.assertEqual(result['terminal_reason'], 'repair_budget_exhausted')

    def test_slow_answer_is_censored_without_grading_or_retry(self):
        def slow(t, p, n):
            self.clock.advance(1001)
            return Answer('late')
        result = self.execute(answer=slow, grader=lambda *_: self.fail('must not grade'))
        self.assertEqual(result['terminal_reason'], 'deadline_exceeded')
        self.assertEqual(len(result['attempts']), 1)
        self.assertIsNone(result['confirmed_time_to_correct_ns'])
        self.assertGreater(result['user_visible_wall_ns'], 1000)  # Actual overrun, not truncated to budget.

    def test_callback_timeout_is_not_controller_deadline(self):
        def timed_out(*_):
            raise TimeoutError('private host detail')
        result = self.execute(answer=timed_out)
        self.assertEqual(result['terminal_reason'], 'callback_timeout')
        self.assertEqual(result['attempts'][0]['failure_stage'], 'answer')
        self.assertEqual(result['attempts'][0]['failure_reason'], 'callback_timeout')
        self.assertNotIn('private host detail', json.dumps(result))

    def test_slow_prepare_does_not_dispatch_answer(self):
        def slow(t, n):
            self.clock.advance(1001)
        result = self.execute(prepare=slow, answer=lambda *_: self.fail('must not answer'))
        self.assertEqual(result['terminal_reason'], 'deadline_exceeded')
        self.assertIsNone(result['first_answer_ns'])

    def test_slow_grade_kept_but_not_credited_as_within_budget(self):
        def slow(t, output, n):
            self.clock.advance(1001)
            return grade()
        result = self.execute(grader=slow)
        self.assertTrue(result['attempts'][0]['grade']['passed'])
        self.assertEqual(result['terminal_reason'], 'deadline_exceeded')
        self.assertIsNone(result['confirmed_time_to_correct_ns'])

    def test_callback_failure_kept_and_sanitized(self):
        def broken(*_):
            raise RuntimeError('secret-key /private/source excerpt')
        result = self.execute(answer=broken)
        self.assertEqual(result['terminal_reason'], 'callback_error')
        self.assertEqual(result['phases']['answer_generation']['status'], 'observed')
        self.assertNotIn('secret-key', json.dumps(result))
        self.assertNotIn('/private/source', json.dumps(result))

    def test_cancelled_trial_is_retained(self):
        def cancelled(*_):
            raise KeyboardInterrupt()
        self.assertEqual(self.execute(answer=cancelled)['terminal_reason'], 'cancelled')

    def test_queue_and_approval_not_double_counted(self):
        def prep(t, n):
            with t.phase('candidate_discovery'):
                self.clock.advance(10)
                with t.phase('host_queue'):
                    self.clock.advance(30)
            with t.phase('operator_approval'):
                self.clock.advance(40)
            self.clock.advance(7)  # Unattributed orchestration, not fabricated active work.
            return b'request'
        result = self.execute(prepare=prep)
        self.assertEqual(result['user_visible_wall_ns'], 112)
        self.assertEqual(result['observed_wait_union_ns'], 70)
        self.assertEqual(result['observed_active_execution_ns'], 35)
        self.assertEqual(result['unattributed_ns'], 7)
        self.assertEqual(result['phases']['candidate_discovery']['inclusive_union_ns'], 40)

    def test_missing_is_not_not_applicable_or_zero(self):
        def prep(t, n):
            t.not_applicable('provider', 'cold_graph_build')
            return b''
        result = self.execute(prepare=prep)
        self.assertEqual(result['phases']['provider']['status'], 'not_applicable')
        self.assertTrue(result['phases']['provider']['complete'])
        self.assertEqual(result['phases']['provider']['inclusive_union_ns'], 0)
        self.assertEqual(result['phases']['warm_graph_load']['status'], 'missing')
        self.assertFalse(result['phases']['warm_graph_load']['complete'])
        self.assertIsNone(result['phases']['warm_graph_load']['inclusive_union_ns'])

    def test_named_required_fact_recall_drives_frozen_gate(self):
        result = self.execute(grader=lambda *_: Grade(
            True, 9, 10, True, 0, 'independent-grader', 'e' * 64))
        self.assertEqual(result['terminal_reason'], 'passed')
        self.assertEqual(result['attempts'][0]['grade']['required_fact_score'], 9)
        self.assertEqual(result['attempts'][0]['grade']['required_fact_maximum'], 10)
        self.assertEqual(result['attempts'][0]['grade']['required_fact_recall'], 0.9)

    def test_not_applicable_phase_cannot_run(self):
        def prep(t, n):
            t.not_applicable('provider')
            with t.phase('provider'):
                pass
        self.assertEqual(self.execute(prepare=prep)['terminal_reason'], 'measurement_error')

    def test_unmeasured_answer_tokens_remain_unknown(self):
        result = self.execute()
        self.assertIsNone(result['total_input_tokens'])  # Coverage not claimed.
        self.assertIsNone(result['all_attempt_cost_usd'])

    def test_actual_usage_aggregates_without_subset_double_count(self):
        def grader(t, output, n):
            t.coverage(model_calls=True)
            return grade(n == 1)
        result = self.execute(grader=grader)
        self.assertEqual(result['total_input_tokens'], 200)  # Cached20 is included, not added.
        self.assertEqual(result['total_output_tokens'], 20)  # Reasoning3 is included, not added.
        self.assertAlmostEqual(result['all_attempt_cost_usd'], 0.02)

    def test_missing_single_call_prevents_complete_usage_total(self):
        def grader(t, output, n):
            t.usage('grader0', 'grader', model='unknown-model', provenance='unavailable')
            t.coverage(model_calls=True)
            return grade()
        result = self.execute(grader=grader)
        self.assertIsNone(result['total_input_tokens'])
        self.assertIsNone(result['all_attempt_cost_usd'])

    def test_duplicate_model_call_rejected(self):
        def prep(t, n):
            for _ in range(2):
                t.usage('same', 'jev', provenance='unavailable', model='fixture-model')
        self.assertEqual(self.execute(prepare=prep)['terminal_reason'], 'measurement_error')

    def test_cache_and_reasoning_subsets_validate(self):
        for args in ({'input_tokens': 1, 'cached_input_tokens': 2}, {'output_tokens': 1, 'reasoning_output_tokens': 2}):
            with self.subTest(args=args):
                self.setUp()
                def prep(t, n):
                    t.usage('call', 'answer', model='fixture-model', provenance='fixture', **args)
                self.assertEqual(self.execute(prepare=prep)['terminal_reason'], 'measurement_error')

    def test_utf8_bytes_hashes_not_characters_or_token_estimates(self):
        raw = 'é\n\n你好'.encode()
        def prep(t, n):
            t.context(raw, kind='tool_message')
            return raw
        result = self.execute(prepare=prep)
        rows = result['attempts'][0]['context_deliveries']
        self.assertEqual(rows[0]['bytes'], len(raw))
        self.assertEqual(rows[0]['sha256'], digest(raw))
        self.assertNotIn('你好', json.dumps(result))
        self.assertEqual(len(rows), 2)  # Separate tool and full request views, never blindly summed.

    def test_repeated_source_reads_retained(self):
        def prep(t, n):
            t.source('f'*64, 0, 10, operation_id='r1')
            t.source('f'*64, 0, 10, operation_id='r2')
            return b''
        result = self.execute(prepare=prep)
        self.assertEqual(len(result['attempts'][0]['source_operations']), 2)

    def test_snapshot_binding_cannot_change(self):
        def prep(t, n):
            t.bind(source_snapshot_sha256='f'*64)
        self.assertEqual(self.execute(prepare=prep)['terminal_reason'], 'measurement_error')

    def test_request_binding_cannot_change_mid_attempt(self):
        def prep(t, n):
            t.bind(request_sha256='f'*64)
            t.bind(request_sha256='a'*64)
        self.assertEqual(self.execute(prepare=prep)['terminal_reason'], 'measurement_error')

    def test_grader_identity_rubric_and_gate_enforced(self):
        bad = [replace(grade(), grader_id='answer-lane'), replace(grade(), rubric_sha256='a'*64),
               replace(grade(), required_fact_score=0.8), replace(grade(), unsupported_material_claims=1)]
        for item in bad:
            with self.subTest(item=item):
                self.setUp()
                self.assertEqual(self.execute(grader=lambda *_: item)['terminal_reason'], 'measurement_error')

    def test_grade_is_not_exposed_to_answer_callback(self):
        numbers = []
        def answer(t, prepared, attempt_number):
            numbers.append(attempt_number)
            self.assertIsInstance(attempt_number, int)
            self.assertIsInstance(prepared, bytes)
            return Answer('answer')
        result = self.execute((False, True), answer=answer)
        self.assertEqual(numbers, [0, 1])
        self.assertEqual(result['terminal_reason'], 'passed')
        # Trusted host code has the trace, but must NOT pass it to a model prompt.

    def test_fallback_removal_fixture_keeps_failure_in_result(self):
        outcomes = []
        for fallback_enabled in (True, False):
            self.setUp()
            def prep(t, n):
                if not fallback_enabled:
                    raise RuntimeError('synthetic discovery unavailable')
                with t.phase('fallback'):
                    self.clock.advance(7)
                return b'verified fixture source'
            outcomes.append(self.execute(prepare=prep))
        self.assertEqual(outcomes[0]['terminal_reason'], 'passed')
        self.assertEqual(outcomes[1]['terminal_reason'], 'callback_error')
        self.assertIsNone(outcomes[1]['confirmed_time_to_correct_ns'])
        self.assertEqual(outcomes[0]['phases']['fallback']['inclusive_union_ns'], 7)

    def test_trial_cannot_be_run_twice(self):
        self.execute()
        with self.assertRaises(MeasurementError):
            self.execute()

    def test_clock_regression_rejected(self):
        self.clock.value = -1
        with self.assertRaises(MeasurementError):
            self.trial.now()

    def test_cross_thread_clock_rejected(self):
        errors = []
        def worker():
            try:
                self.trial.now()
            except MeasurementError as e:
                errors.append(str(e))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(errors, ['clock_owner_mismatch'])

    def test_event_trace_order_and_ownership(self):
        result = self.execute((False, True))
        events = result['events']
        self.assertEqual([e['sequence'] for e in events], list(range(len(events))))
        self.assertEqual([e['t_ns'] for e in events], sorted(e['t_ns'] for e in events))
        self.assertEqual(events[0]['event'], 'task_accepted')
        self.assertEqual(events[-1]['event'], 'task_terminal')
        self.assertEqual(sum(e['event'] == 'first_passing_answer' for e in events), 1)
        self.assertEqual(result['clock']['owner'], 'benchmark_controller')

    def test_registered_missing_and_failed_trials_stay_in_denominator(self):
        result = self.execute((False,))
        summary = summarize(['trial1', 'not-returned'], [result])
        self.assertEqual(summary['registered_trials'], 2)
        self.assertEqual(summary['pass_rate_registered'], 0)
        self.assertEqual(summary['trials'][1]['terminal_reason'], 'missing')
        self.assertIsNone(summary['mean_observed_terminal_wall_ns'])
        self.assertIsNone(summary['mean_time_to_correct_ns'])

    def test_completed_receipt_recovers_only_preregistered_trials(self):
        result = self.execute()
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            receipt = save_completed_trial(directory, result)
            self.assertEqual(receipt.name, 'trial1.json')
            self.assertEqual(save_completed_trial(directory, result), receipt)
            recovered = load_completed_trials(directory, ['trial1', 'not-returned'])
            summary = summarize(['trial1', 'not-returned'], recovered)
        self.assertEqual(summary['reported_trials'], 1)
        self.assertEqual(summary['registered_trials'], 2)
        self.assertEqual(summary['trials'][1]['terminal_reason'], 'missing')

    def test_incomparable_arms_and_duplicate_trials_rejected(self):
        result = self.execute()
        with self.assertRaises(MeasurementError):
            summarize(['trial1'], [result, result])
        other = json.loads(json.dumps(result))
        other['identity'].update(trial_id='trial2', arm='D')
        with self.assertRaises(MeasurementError):
            summarize(['trial1', 'trial2'], [result, other])

    def test_union_handles_overlaps_empty_and_adjacent(self):
        self.assertEqual(union_ns([(0,10), (2,8), (9,15), (15,20)]), 20)
        self.assertEqual(union_ns([]), 0)
        with self.assertRaises(MeasurementError):
            union_ns([(10, 0)])

    def test_identity_cannot_contain_raw_paths(self):
        bad = identity()
        bad['repository_id'] = '/private/workspace/repository'
        with self.assertRaises(MeasurementError):
            Trial(bad)

    def test_invalid_budgets_rejected(self):
        for budget in ((True, 10), (-1, 10), (11, 10), (0, 0), (0, 1.5)):
            with self.subTest(budget=budget), self.assertRaises(MeasurementError):
                Budget(*budget)


if __name__ == '__main__':
    unittest.main()
