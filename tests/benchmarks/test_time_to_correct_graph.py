"""Real shipped graph-find path, a disposable local Git fixture, no provider."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/benchmarks'))
from time_to_correct import Answer, Budget, Grade, Trial, canonical, digest
from time_to_correct_graph import observe_graph_find


class GraphTimingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root/'cancel.py').write_text('def cancel_task(task):\n    return task.cancel()\n')
        (self.root/'README.md').write_text('# Cancellation\nThe cancel_task function requests task cancellation.\n')
        subprocess.run(['git','-c','core.hooksPath=/dev/null','init','-q',str(self.root)], check=True, capture_output=True)
        subprocess.run(['git','-C',str(self.root),'-c','core.hooksPath=/dev/null','add','cancel.py','README.md'], check=True, capture_output=True)
        self.args = ['--root',str(self.root),'--prompt','Find cancel_task cancellation implementation and its documentation']
        snapshot = digest(canonical({'sources': [
            {'path': p.name, 'byte_length': len(p.read_bytes()), 'sha256': digest(p.read_bytes())}
            for p in sorted([self.root/'README.md', self.root/'cancel.py'])]}))
        self.identity = dict(run_id='graph-fixture', trial_id='trial1', task_id='cancel', arm='C',
                             repository_id='synthetic', repository_commit='a'*40, source_snapshot_sha256=snapshot,
                             dirty_state_sha256='c'*64, answer_model='fixture-model', reasoning='none',
                             prompt_sha256='d'*64, rubric_sha256='e'*64, rubric_version='v1', answer_lane_id='answer-lane')
    def run_graph(self, use_graph=True):
        trial = Trial(self.identity, Budget(0, 10_000_000_000), execution='fixture')
        payloads = []
        def prep(t, n):
            if use_graph:
                payload = observe_graph_find(t, ROOT, self.args)
                payloads.append(payload)
            else:
                t.not_applicable('cold_graph_build','warm_graph_load')
            return None
        result = trial.run(prep, lambda *_: Answer('fixture'),
                           lambda *_: Grade(True,1,1,True,0,'independent-grader','e'*64))
        return result, payloads
    def test_graph_wrapper_preserves_exact_public_result(self):
        result, payloads = self.run_graph()
        self.assertEqual(result['terminal_reason'], 'passed')
        spec = importlib.util.spec_from_file_location('_baseline_driver', ROOT/'plugins/graph-engineering/skills/graph-find/scripts/graph_find.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(module.main(self.args), 0)
        self.assertEqual(payloads[0], json.loads(output.getvalue()))
    def test_actual_graph_build_and_retrieval_are_observed(self):
        result, _ = self.run_graph()
        self.assertEqual(result['phases']['cold_graph_build']['status'], 'observed')
        self.assertEqual(result['phases']['retrieval']['status'], 'observed')
        self.assertEqual(result['phases']['warm_graph_load']['status'], 'not_applicable')
        observation = result['attempts'][0]['graph_observation']
        self.assertEqual(observation['edge_count'], 0)
        self.assertEqual(observation['record_count'], 2)
    def test_file_and_memory_reads_are_distinguished(self):
        result, _ = self.run_graph()
        operations = result['attempts'][0]['source_operations']
        self.assertEqual(sum(o['access'] == 'file_read' for o in operations), 2)
        self.assertGreater(sum(o['access'] == 'memory_read' for o in operations), 0)
        self.assertEqual(result['attempts'][0]['context_deliveries'], [])
    def test_graph_removal_does_not_invent_build_work(self):
        result, _ = self.run_graph(False)
        self.assertEqual(result['phases']['cold_graph_build']['status'], 'not_applicable')
        self.assertEqual(result['attempts'][0]['source_operations'], [])


if __name__ == '__main__':
    unittest.main()
