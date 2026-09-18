"""Runnable clock/controller demonstration. Synthetic outcomes, NOT an eval.

Run from the repository root:
  python3 scripts/benchmarks/time_to_correct_fixture.py

No providers, repositories, credentials or private artifacts are accessed.
"""
import json

from time_to_correct import Answer, Budget, Grade, Trial, summarize


class Clock:
    def __init__(self):
        self.value = 0
    def __call__(self):
        return self.value
    def advance(self, ns):
        self.value += ns


def demonstrate(arm):
    clock = Clock()
    identity = dict(run_id='demonstration', trial_id='example-' + arm, task_id='fixture', arm=arm,
                    repository_id='synthetic', repository_commit='a'*40, source_snapshot_sha256='b'*64,
                    dirty_state_sha256='c'*64, answer_model='fixture-answer', reasoning='none',
                    prompt_sha256='d'*64, rubric_sha256='e'*64, rubric_version='synthetic-v1',
                    answer_lane_id='answer-lane')
    trial = Trial(identity, Budget(1, 1_000_000_000), clock=clock, execution='fixture')
    def prepare(t, n):
        if arm in {'C','D'}:
            with t.phase('cold_graph_build'):
                clock.advance(5_000_000)
            t.not_applicable('warm_graph_load')  # No invented warm path.
        else:
            t.not_applicable('cold_graph_build', 'warm_graph_load')
        with t.phase('candidate_discovery'):
            clock.advance(10_000_000)
        if arm in {'B','D'}:
            with t.phase('jev_preparation'):
                clock.advance(1_000_000)
            with t.phase('operator_approval'):
                clock.advance(15_000_000)
            with t.phase('provider'):
                clock.advance(3_000_000)
            with t.phase('source_revalidation'):
                clock.advance(1_000_000)
            t.usage(f'jev{n}', 'jev', model='fixture-jev', provenance='fixture',
                    input_tokens=40, output_tokens=3, cost_usd=0.001)
        else:
            t.not_applicable('jev_preparation', 'provider', 'source_revalidation')
        with t.phase('context_composition'):
            payload = b'unchanged synthetic context'
            t.context(payload)
        return payload
    def answer(t, payload, n):
        with t.phase('host_queue'):
            clock.advance(2_000_000)
        clock.advance(20_000_000)
        t.usage(f'answer{n}', 'answer', model='fixture-answer', provenance='fixture',
                input_tokens=100, output_tokens=10, cost_usd=0.01)
        # Every arm intentionally needs a repair. No manufactured Jev win.
        return Answer('incomplete' if n == 0 else 'complete')
    def grade(t, output, n):
        clock.advance(4_000_000)
        t.coverage(source_operations=True, model_calls=True, context_deliveries=True)
        passed = output.content == 'complete'
        return Grade(passed, int(passed), 1, True, 0, 'fixture-grader', 'e'*64)
    return trial.run(prepare, answer, grade)


if __name__ == '__main__':
    rows = [demonstrate(arm) for arm in 'ABCD']
    print(json.dumps({'status': 'synthetic_demonstration_not_performance_evidence',
                      'provider_calls_made': 0, 'trials': rows,
                      'per_arm': {r['identity']['arm']: summarize([r['identity']['trial_id']], [r]) for r in rows}},
                     sort_keys=True, indent=2))
