"""Reopen saved handoff evidence; no source admission or product launch."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
args = parser.parse_args()
folder = args.output.resolve()
receipt = json.loads((folder/'receipt.json').read_text())
summary = {'outcome': receipt['outcome'], 'exit_code': receipt['exit_code'],
           'received_source_bytes': receipt['received_source_bytes'],
           'native_budget_validation': receipt['native_budget_validation'],
           'native_source_validation': receipt['native_source_validation'],
           'error': receipt.get('error'), 'answer_model_stage': receipt['answer_model_stage'],
           'snapshot': receipt.get('identity'), 'files': []}
if receipt['exit_code'] != 0:
    print(json.dumps(summary, indent=2))
    raise SystemExit(receipt['exit_code'])

assert receipt['outcome'] == 'source_actions_complete'
assert receipt['native_budget_validation'] == receipt['native_source_validation'] == 'accepted'
assert receipt['source_identity_validation'] == 'before_after_equal'
assert receipt['last_budget'] == receipt['last_accepted_budget']
nodes = {}
total = 0
for line in (folder/'responses.jsonl').read_text().splitlines():
    response = json.loads(line)
    nodes.update({node['id']: node for node in response['result'].get('nodes', [])})
    document = response['result'].get('document')
    if not document:
        continue
    raw = document['text'].encode('utf-8')
    witness = nodes['file:' + document['path']]
    digest = hashlib.sha256(raw).hexdigest()
    assert response['status'] == 'ok' and document['kind'] == 'file'
    assert digest == witness['source_sha256'] == document['source_sha256'] == document['excerpt_sha256']
    assert document['byte_start'] == witness['byte_start'] == 0
    assert document['byte_end'] == witness['byte_end'] == len(raw) == response['result']['byte_count']
    total += len(raw)
    summary['files'].append({'path': document['path'], 'bytes': len(raw), 'sha256': digest})
assert total == receipt['received_source_bytes'] == receipt['last_accepted_budget']['delivered_content_bytes']
summary['remaining_bytes'] = receipt['last_accepted_budget']['remaining_bytes']
summary['meaning'] = 'Saved complete-file custody reconciles. Answer/evaluator/comparison stages did not run.'
print(json.dumps(summary, indent=2))
