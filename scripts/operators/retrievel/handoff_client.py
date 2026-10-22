#!/usr/bin/env python3
"""Bounded provider-free protocol test client; no answer-model stage."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import signal
import time

from guided import Guide, NavigationError, PipeSession, output_dir, source_hashes


def validate_handoff(payload):
    """Validate local conservation/bindings; native admission proves freshness."""
    def require(condition, message):
        if not condition:
            raise NavigationError('invalid handoff: ' + message)

    def integer(value, name):
        require(type(value) is int and value >= 0, name + ' must be a nonnegative integer')
        return value

    def digest(value, name):
        require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None,
                name + ' must be a lowercase SHA-256')
        return value

    def path(value):
        require(type(value) is str and bool(value) and not value.startswith('/') and
                '\\' not in value and ':' not in value and '\x00' not in value and
                all(part not in ('', '.', '..') for part in value.split('/')) and
                PurePosixPath(value).as_posix() == value, 'source path must be canonical and relative')
        return value

    require(type(payload) is dict, 'envelope must be an object')
    snapshot = digest(payload['source_snapshot_sha256'], 'source snapshot')
    budget = payload['delivery_budget']
    require(type(budget) is dict, 'delivery_budget must be an object')
    values = {k: integer(budget[k], k) for k in ('limit_bytes', 'graph_context_bytes',
              'follow_up_source_bytes', 'delivered_content_bytes', 'remaining_bytes')}
    # This reviewed client has a 32,768-byte ceiling; the native tool's broader
    # CLI capability does not authorize raising this workflow's allowance.
    require(0 < values['limit_bytes'] <= 32768, 'limit exceeds the current client ceiling')
    delivered = integer(payload['delivered_total_bytes'], 'delivered_total_bytes')
    remaining = integer(payload['remaining_byte_budget'], 'remaining_byte_budget')
    require(delivered == values['delivered_content_bytes'] ==
            values['graph_context_bytes'] + values['follow_up_source_bytes'], 'delivered charges disagree')
    require(remaining == values['remaining_bytes'] and delivered + remaining == values['limit_bytes'],
            'limit, delivered and remaining do not conserve the shared allowance')
    require(remaining > 0, 'no remaining source allowance')
    context = payload['context']
    require(type(context) is str, 'context must be text')
    require(len(context.encode('utf-8')) == values['graph_context_bytes'] ==
            integer(payload['context_bytes'], 'context_bytes') ==
            integer(payload['delivered_context_bytes'], 'delivered_context_bytes'), 'context charge differs from text')
    documents = []
    follow_up = payload.get('follow_up')
    if follow_up is not None:
        require(type(follow_up) is dict and follow_up['source_snapshot_sha256'] == snapshot,
                'follow-up snapshot differs')
        source_payload = follow_up.get('payload')
        require(source_payload is None or type(source_payload) is dict, 'follow-up payload must be an object or null')
        documents = (source_payload or {}).get('documents', [])
        require(type(documents) is list, 'follow-up documents must be an array')
        require(integer(follow_up['source_bytes'], 'follow-up source_bytes') == values['follow_up_source_bytes'],
                'follow-up source charge differs')
    follow_bytes = 0
    for document in documents:
        require(type(document) is dict and type(document.get('content')) is str, 'follow-up document must contain text')
        path(document['source_path'])
        raw = document['content'].encode('utf-8')
        require(len(raw) == integer(document['byte_count'], 'follow-up byte_count') and
                hashlib.sha256(raw).hexdigest() == digest(document['source_sha256'], 'follow-up source hash'),
                'follow-up content, bytes or hash disagree')
        follow_bytes += len(raw)
    require(follow_bytes == values['follow_up_source_bytes'], 'follow-up charge lacks matching delivered content')
    recovery = payload['named_source_recovery']
    require(type(recovery) is dict and recovery.get('needs_recovery') is True, 'recovery must be explicitly needed')
    targets = recovery['targets']
    require(type(targets) is list and 0 < len(targets) <= 16 and
            integer(recovery.get('omitted_mentions', 0), 'omitted_mentions') == 0, 'targets must be complete and bounded')
    pending = []
    source_paths = set()
    for target in targets:
        require(type(target) is dict, 'target must be an object')
        require(type(target.get('candidate_count')) is int and target['candidate_count'] == 1 and
                type(target.get('candidate_paths')) is list and len(target['candidate_paths']) == 1,
                'every target must be uniquely admitted')
        source_path = path(target['candidate_paths'][0])
        require(source_path not in source_paths, 'duplicate named source path')
        source_paths.add(source_path)
        source_hash = digest(target['source_sha256'], 'target source hash')
        mention = target['mention']
        require(type(mention) is str and bool(mention) and
                (mention == source_path if '/' in mention else mention == PurePosixPath(source_path).name),
                'mention differs from the admitted source path')
        if target['status'] == 'complete_source_delivered':
            require('next_build' not in target and any(d['source_path'] == source_path and
                    d['source_sha256'] == source_hash for d in documents), 'completed target lacks its delivered source')
            continue
        require(target['status'] == 'complete_source_read_needed', 'target is unresolved')
        action = target['next_build']
        require(type(action) is dict and not set(action) - {'op', 'intent', 'scope', 'limit', 'snapshot_sha256'},
                'build fields differ from the supported handoff')
        require(action.get('op') == 'build' and type(action.get('limit')) is int and action['limit'] == 1 and
                action.get('scope') == source_path, 'build must select exactly the admitted source')
        require(type(action.get('intent')) is str and bool(action['intent'].strip()) and mention in action['intent'],
                'build intent must retain the named source')
        require(action.get('snapshot_sha256', snapshot) == snapshot, 'build snapshot differs from the envelope')
        bound_action = {**action, 'snapshot_sha256': snapshot}
        require(len(json.dumps(bound_action, separators=(',', ':')).encode('utf-8')) + 1 <= 16384,
                'build exceeds the existing native action limit')
        pending.append(target)
    require(bool(pending), 'client requires at least one uniquely admitted pending target')
    return pending, values['limit_bytes'], delivered, remaining



def validate_native_budget(budget, inherited, previous, received_bytes, status):
    """Validate the native ledger against this unchanged session allowance."""
    def require(condition, message):
        if not condition:
            raise NavigationError('invalid native budget: ' + message)

    fields = ('limit_bytes', 'delivered_content_bytes', 'remaining_bytes', 'steps', 'max_steps')
    require(type(budget) is dict and all(key in budget for key in fields), 'budget fields are required')
    values = {key: budget[key] for key in fields}
    require(all(type(value) is int and value >= 0 for value in values.values()),
            'budget values must be nonnegative integers')
    require(values['limit_bytes'] == inherited, 'limit differs from inherited allowance')
    require(values['delivered_content_bytes'] + values['remaining_bytes'] == inherited,
            'delivered and remaining do not conserve the allowance')
    require(values['max_steps'] == 32 and values['steps'] <= values['max_steps'], 'step limit differs or is exceeded')
    previous = previous or {'delivered_content_bytes': 0, 'remaining_bytes': inherited, 'steps': 0}
    require(values['delivered_content_bytes'] >= previous['delivered_content_bytes'] and
            values['remaining_bytes'] <= previous['remaining_bytes'] and
            values['steps'] >= previous['steps'], 'counters moved backwards')
    increment = values['delivered_content_bytes'] - previous['delivered_content_bytes']
    require(increment >= received_bytes and (status != 'ok' or increment == received_bytes),
            'delivery increment differs from received source text')
    return values


def validate_native_file(result, action, nodes, target):
    """Bind received complete-file bytes to already admitted witnesses."""
    def require(condition, message):
        if not condition:
            raise NavigationError('invalid native source: ' + message)

    witness = nodes.get(action.get('id'))
    document = result.get('document')
    require(type(witness) is dict and witness.get('kind') == 'file', 'read lacks an admitted file witness')
    require(type(witness.get('path')) is str and action['id'] == 'file:' + witness['path'],
            'read differs from admitted file path')
    require(type(document) is dict and document.get('kind') == 'file' and type(document.get('text')) is str,
            'read lacks complete file text')
    require(document.get('path') == witness['path'], 'path differs from admitted witness')
    raw = document['text'].encode('utf-8')
    source_hash = hashlib.sha256(raw).hexdigest()
    require(source_hash == witness.get('source_sha256') == document.get('source_sha256') ==
            document.get('excerpt_sha256'), 'text hash differs from admitted witness')
    for field, expected in (('byte_start', 0), ('byte_end', len(raw))):
        require(type(document.get(field)) is int and document[field] == expected and
                type(witness.get(field)) is int and witness[field] == expected,
                field + ' differs from complete file bounds')
    require(type(result.get('byte_count')) is int and result['byte_count'] == len(raw),
            'byte_count differs from received text')
    if document['path'] == target['next_build']['scope']:
        require(source_hash == target['source_sha256'], 'text hash differs from handoff target')
    return {'path': document['path'], 'source_sha256': source_hash, 'byte_count': len(raw)}


def terminal_result(receipt, receipt_path):
    """Present retained observations; never turn source delivery into an answer."""
    files = receipt.get('accepted_source_documents', [])
    if receipt.get('interrupted') or receipt.get('exit_code') == 130:
        status = 'INTERRUPTED'
    elif (receipt.get('exit_code') == 0 and receipt.get('outcome') == 'source_actions_complete'
          and receipt.get('requested_sources_complete') is True):
        status = 'COMPLETE'
    elif receipt.get('exit_code') != 0:
        status = ('PARTIAL' if files or receipt.get('received_source_bytes', 0)
                  or receipt.get('prior_delivered_bytes', 0) else 'FAILED')
    else:
        status = 'UNCONFIRMED'
    quoted = lambda value: json.dumps(str(value), ensure_ascii=True)
    lines = [f"Source navigation: {status} (exit {receipt.get('exit_code')})",
             f"Validated full-file references: {len(files)}"]
    for file in files:
        lines.append(f"  {quoted(file['path'])}: {file['byte_count']} bytes; "
                     f"SHA256 {file['source_sha256']}; {file['origin']}")
    budget = receipt.get('combined_delivery_budget')
    if budget is not None:
        lines.append(f"Last accepted shared content charge: {budget['delivered_content_bytes']}/"
                     f"{budget['limit_bytes']} bytes; {budget['remaining_bytes']} remaining.")
    else:
        lines.append('Accepted combined content budget: unavailable.')
    if 'inherited_remaining_budget' in receipt:
        lines.append(f"At startup: {receipt['prior_delivered_bytes']} prior content bytes; "
                     f"{receipt['inherited_remaining_budget']} native allowance bytes.")
    lines.extend([f"Native source bytes observed: {receipt.get('received_source_bytes', 0)}.",
                  f"Native budget validation: {receipt.get('native_budget_validation', 'not_attempted')}; "
                  f"native source validation: {receipt.get('native_source_validation', 'not_attempted')}.",
                  f"Evidence receipt: {quoted(receipt_path)}",
                  'Answer/evaluation: not attempted. Semantic completeness: not assessed.'])
    if receipt.get('error'):
        lines.append('Reason: ' + quoted(receipt['error']))
    return '\n'.join(lines) + '\n'


def emit_terminal_result(receipt, receipt_path):
    # Presentation follows the saved receipt and does not rewrite its outcome.
    # Direct writes avoid buffered-shutdown errors if a receiving pipe closes.
    raw = terminal_result(receipt, receipt_path).encode('ascii')
    try:
        while raw:
            written = os.write(1, raw)
            if written <= 0:
                break
            raw = raw[written:]
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--handoff', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--python', required=True)
    parser.add_argument('--tool', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--evidence-root', required=True, help='existing owned absolute directory outside source')
    parser.add_argument('--follow-imports', action='store_true')
    args = parser.parse_args()
    try:
        destination = output_dir(args.output, evidence_root=args.evidence_root, source_root=args.root)
    except (NavigationError, OSError) as error:
        parser.error(str(error))
    started = time.monotonic()
    receipt = {'client_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'source_sha256_before': source_hashes(Path(args.tool)), 'actions': [],
               'provider_calls': 0, 'model_tokens': None, 'model_dollars': None,
               'answer_model_stage': 'not_attempted', 'semantic_completeness': 'not_assessed',
               'manual_glue': 'caller enables optional one-hop import recovery; source scope comes from adapter handoff',
               'interrupted': False, 'received_source_bytes': 0, 'accepted_source_documents': [],
               'evidence_root': str(Path(args.evidence_root).resolve()),
               'native_budget_validation': 'not_attempted', 'native_source_validation': 'not_attempted'}
    session = None
    code = 0
    cleaning_up = False
    previous_sigint = signal.getsignal(signal.SIGINT)

    def interrupt(signum, frame):
        receipt['interrupted'] = True
        receipt.setdefault('interrupted_phase', 'cleanup' if cleaning_up else 'navigation')
        receipt['interruption_signal'] = int(signum)
        # Keep child construction and cleanup uninterrupted. A pending request
        # can stop immediately; between requests the next checkpoint stops it.
        if not cleaning_up and 'in_flight_action' in receipt:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, interrupt)
    try:
        with Path(args.handoff).open('rb') as handoff:
            raw = handoff.read(2097152 + 1)
        if len(raw) > 2097152:
            raise NavigationError('handoff exceeds the existing client evidence limit')
        payload = json.loads(raw)
        receipt['handoff_sha256'] = hashlib.sha256(raw).hexdigest()
        targets, limit, delivered, remaining = validate_handoff(payload)
        if args.follow_imports and len(targets) != 1:
            raise NavigationError('follow-imports requires one uniquely admitted pending target')
        receipt['handoff_validation'] = 'local_conservation_and_bindings_accepted; native_freshness_required'
        receipt['inherited_limit_bytes'] = limit
        receipt['question'] = targets[0]['next_build']['intent']
        receipt['requested_target_paths'] = [t['candidate_paths'][0]
                                             for t in payload['named_source_recovery']['targets']]
        receipt['completed_target_paths'] = [t['candidate_paths'][0]
                                             for t in payload['named_source_recovery']['targets']
                                             if t['status'] == 'complete_source_delivered']
        receipt['remaining_target_paths'] = [t['candidate_paths'][0] for t in targets]
        receipt['requested_sources_complete'] = False
        receipt['scope_origin'] = 'named-source handoff; no target path supplied to client'
        receipt['prior_delivered_bytes'] = delivered
        receipt['inherited_remaining_budget'] = remaining
        completed = {t['candidate_paths'][0]: t['source_sha256']
                     for t in payload['named_source_recovery']['targets']
                     if t['status'] == 'complete_source_delivered'}
        for document in ((payload.get('follow_up') or {}).get('payload') or {}).get('documents', []):
            if completed.get(document['source_path']) == document['source_sha256']:
                receipt['accepted_source_documents'].append({
                    'path': document['source_path'], 'byte_count': document['byte_count'],
                    'source_sha256': document['source_sha256'], 'origin': 'prior_follow_up',
                    'snapshot_sha256': payload['source_snapshot_sha256']})
        argv = [args.python, '-B', args.tool, '--root', args.root, '--byte-budget', str(remaining)]
        receipt['argv'] = argv
        if receipt['interrupted']:
            raise KeyboardInterrupt
        session = PipeSession(argv)
        guide = Guide()
        with (destination / 'responses.jsonl').open('x') as responses:
            def request(action):
                if receipt['interrupted']:
                    raise KeyboardInterrupt
                receipt['in_flight_action'] = action
                result = session.request(action)
                receipt['in_flight_response'] = result
                receipt['actions'].append({'request': action, 'status': result['status'], 'reason': result['reason']})
                responses.write(json.dumps(result, sort_keys=True) + '\n')
                responses.flush()
                # Retain raw observations before validating them. A rejected
                # response may already contain source; never erase or refund it.
                document = result.get('result', {}).get('document')
                received = (len(document['text'].encode('utf-8'))
                            if isinstance(document, dict) and isinstance(document.get('text'), str) else 0)
                receipt['received_source_bytes'] += received
                receipt.update(last_budget=result.get('budget'), last_cost=result.get('cost'),
                               scan=result.get('scan'), last_observed_native_identity={
                                   key: result.get(key) for key in ('head', 'branch', 'snapshot_sha256')})
                try:
                    accepted = validate_native_budget(result.get('budget'), remaining,
                        receipt.get('last_accepted_budget'), received, result['status'])
                except NavigationError as error:
                    receipt['native_budget_validation'] = 'rejected'
                    receipt['native_budget_error'] = str(error)
                    raise
                receipt.update(native_budget_validation='accepted', last_accepted_budget=accepted)
                receipt['combined_delivery_budget'] = {
                    'limit_bytes': limit, 'prior_delivered_bytes': delivered,
                    'native_delivered_bytes': accepted['delivered_content_bytes'],
                    'delivered_content_bytes': delivered + accepted['delivered_content_bytes'],
                    'remaining_bytes': accepted['remaining_bytes']}
                if result['status'] == 'ok' and result['snapshot_sha256'] != payload['source_snapshot_sha256']:
                    raise NavigationError('successful native response differs from the handoff snapshot')
                if result['status'] == 'ok' and action['op'] == 'read':
                    try:
                        source = validate_native_file(result['result'], action, guide.nodes, target)
                    except NavigationError as error:
                        receipt.update(native_source_validation='rejected', native_source_error=str(error))
                        raise
                    receipt.update(native_source_validation='accepted', last_accepted_source=source)
                guide.accept(result, action)
                receipt.update(identity=guide.identity, last_budget=result['budget'],
                               last_cost=result['cost'], scan=result['scan'])
                if result['status'] == 'ok' and action['op'] == 'read':
                    receipt['accepted_source_documents'].append({**source, 'origin': 'native',
                        'snapshot_sha256': result['snapshot_sha256']})
                receipt.pop('in_flight_response')
                receipt.pop('in_flight_action')
                if result['status'] != 'ok':
                    raise NavigationError('native tool deferred: ' + result['reason'])
                return result

            for target in targets:
                request({**target['next_build'], 'snapshot_sha256': payload['source_snapshot_sha256']})
                result = request(guide.action('read-recovered:1'))
                document = result['result']['document']
                if document['path'] != target['next_build']['scope'] or document['source_sha256'] != target['source_sha256']:
                    raise NavigationError('delivered target differs from handoff snapshot')
                receipt['completed_target_paths'].append(document['path'])
                receipt['remaining_target_paths'].remove(document['path'])
            receipt['requested_sources_complete'] = not receipt['remaining_target_paths']
            if args.follow_imports:
                request(guide.action('recover-imports'))
                request(guide.action('read-recovered:1'))
    except KeyboardInterrupt:
        receipt['interrupted'] = True
        receipt.setdefault('interrupted_phase', 'navigation')
        code = 130
    except (NavigationError, OSError, ValueError, KeyError, TypeError) as error:
        code = 2
        receipt['error'] = str(error)
    finally:
        cleaning_up = True
        if session:
            receipt['cleanup'] = session.close()
            receipt['stdout_wire_bytes'] = session.stdout_total
            receipt['active_navigation_seconds'] = session.active_seconds
            (destination / 'stderr.txt').write_bytes(session.stderr)
            if receipt['cleanup']['cleanup_error'] or receipt['cleanup']['abnormal_exit'] or not receipt['cleanup']['reaped']:
                code = 2
        receipt['source_sha256_after'] = source_hashes(Path(args.tool))
        if receipt['source_sha256_before'] == receipt['source_sha256_after']:
            receipt['source_identity_validation'] = 'before_after_equal'
        else:
            receipt['source_identity_validation'] = 'before_after_changed'
            receipt['source_identity_error'] = 'invoked source maps changed between before/after observations'
            receipt.setdefault('error', receipt['source_identity_error'])
            code = 2
        if receipt['interrupted'] and session:
            pending = bytes(session.pending)
            (destination / 'pending_stdout.raw').write_bytes(pending)
            receipt['pending_stdout_bytes'] = len(pending)
            receipt['pending_stdout_sha256'] = hashlib.sha256(pending).hexdigest()
        receipt['elapsed_seconds'] = time.monotonic() - started
        # Work and owned cleanup have ended. Protect this short durable commit
        # from a late SIGINT, then restore the caller's handler.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            if receipt['interrupted']:
                code = 130
                receipt.setdefault('error', 'source navigation interrupted')
            receipt['exit_code'] = code
            receipt['outcome'] = ('interrupted' if receipt['interrupted'] else
                                  'failed' if code else 'source_actions_complete')
            (destination / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
            emit_terminal_result(receipt, destination / 'receipt.json')
        finally:
            signal.signal(signal.SIGINT, previous_sigint)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
