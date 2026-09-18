"""Read retained public pilot receipts, never ignored inputs or live providers.

This recomputes bookkeeping, not the independent grades or historical timings.
Privacy output identifies file/line locations without repeating private values.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess


def inspect(repo: Path) -> dict:
    source = repo/'benchmarks/velgraphing-corpus-pilot-v1/result.json'
    result = json.loads(source.read_text(encoding='utf-8'))
    def usage_total(rows, key):
        values = [0 if r['jev'] == 'off' else r['telemetry'].get('jev', {}).get(key) for r in rows]
        return sum(values) if all(type(v) is int and v >= 0 for v in values) else None
    by_arm = {}
    for arm in 'ABCD':
        rows = [r for r in result['results'] if r['arm'] == arm]
        by_arm[arm] = {
            'task_count': len(rows), 'score': sum(r['required_fact_score'] for r in rows),
            'maximum': sum(r['required_fact_max'] for r in rows),
            'passes': sum(r['status'] == 'pass' for r in rows),
            'jev_input_tokens': usage_total(rows, 'input_tokens'),
            'jev_output_tokens': usage_total(rows, 'output_tokens'),
            'answer_wall_unknown': sum(r['telemetry'].get('all_in', r['telemetry']).get('total_wall_ms', 'unknown') == 'unknown' for r in rows),
        }
    # Enumerate only tracked historical benchmark JSON. No .inputs, raw reports,
    # credentials or source corpus checkout is opened.
    tracked = subprocess.run(['git','-C',str(repo),'ls-files','-z','--','benchmarks'],
                             capture_output=True, check=True).stdout
    privacy = []
    for encoded in tracked.split(b'\0'):
        if not encoded:
            continue
        relative = Path(encoded.decode('utf-8'))
        if relative.name not in {'freeze.json', 'result.json', 'result-seal.json'} or '.inputs' in relative.parts:
            continue
        path = repo/relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(repo.resolve()):
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if re.search(r'/Users/[^/\s"\\]+/', line):
                privacy.append({'file': relative.as_posix(), 'line': number,
                                'finding': 'historical_absolute_home_path'})
    return {'status': 'retained_receipt_bookkeeping_only', 'arms': by_arm,
            'provider_summary': {k: result['provider_summary'][k] for k in
                 ('live_calls','input_tokens','output_tokens','elapsed_sum_ms')},
            'privacy_locations': privacy,
            'grade_reproduced': False, 'ordering_causality_established': False,
            'provider_calls_made': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(inspect(args.root), sort_keys=True, indent=2))
