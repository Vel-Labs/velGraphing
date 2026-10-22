"""Reopen saved handoff evidence; no source admission or product launch."""
import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path


def escaped_display(text):
    """Keep LF; visibly escape terminal controls, format controls and backslashes."""
    return ''.join(
        character if character == '\n' else
        '\\\\' if character == '\\' else
        json.dumps(character, ensure_ascii=True)[1:-1]
        if unicodedata.category(character) in {'Cc', 'Cf', 'Cs', 'Zl', 'Zp'} else
        character
        for character in text
    )


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--show-source', action='store_true',
                    help='Display saved native text after custody checks; terminal controls are escaped')
args = parser.parse_args()
if args.show_source and not __debug__:
    parser.error('--show-source requires Python assertions enabled; omit -O/-OO')
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
verified_documents = []
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
    verified_documents.append(document)
assert total == receipt['received_source_bytes'] == receipt['last_accepted_budget']['delivered_content_bytes']
summary['remaining_bytes'] = receipt['last_accepted_budget']['remaining_bytes']
summary['meaning'] = 'Saved complete-file custody reconciles. Answer/evaluator/comparison stages did not run.'
if not args.show_source:
    print(json.dumps(summary, indent=2))
else:
    print('Saved source status: ' + json.dumps(summary['outcome'], ensure_ascii=True))
    print('Saved snapshot: ' + json.dumps(summary['snapshot'], ensure_ascii=True, sort_keys=True))
    print(f"Native retained bytes: {total}; remaining bytes: {summary['remaining_bytes']}.")
    print('Untrusted source display: LF is retained; backslashes and terminal/format controls are escaped.')
    for file, document in zip(summary['files'], verified_documents):
        print('Retained file: ' + json.dumps(file, ensure_ascii=True, sort_keys=True))
        print('BEGIN retained source display')
        sys.stdout.write(escaped_display(document['text']))
        print('\nEND retained source display')
    print(summary['meaning'])
