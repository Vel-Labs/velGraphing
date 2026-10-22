#!/usr/bin/env python3
"""Provider-free, user-directed frontend for the existing graph_tools JSONL seam."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import selectors
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CANONICAL = next((p for p in HERE.parents if (p / 'packages/core').is_dir()), HERE)
TOOL = CANONICAL / 'plugins/graph-engineering/skills/graph-find/scripts/graph_tools.py'


class NavigationError(RuntimeError):
    pass


def output_dir(value, *, evidence_root=None, source_root=None):
    allowed = HERE
    if evidence_root is not None:
        supplied = Path(evidence_root)
        if not supplied.is_absolute():
            raise NavigationError('evidence root must be absolute')
        allowed = supplied.resolve(strict=True)
        if allowed != supplied or not allowed.is_dir():
            raise NavigationError('evidence root must be an existing directory without aliases')
        if allowed.stat().st_uid != os.getuid():
            raise NavigationError('evidence root must be owned by the current user')
        protected = [HERE, CANONICAL]
        if source_root is not None:
            protected.append(Path(source_root).resolve())
        if any(allowed == root or root in allowed.parents for root in protected):
            raise NavigationError('evidence root must be outside source and operator directories')
    result = Path(value).resolve()
    if evidence_root is not None and any(result == root or root in result.parents for root in protected):
        raise NavigationError('output must be outside source and operator directories')
    if result == allowed or allowed not in result.parents:
        raise NavigationError('output must be a new directory below the evidence root')
    result.mkdir(parents=True, exist_ok=True)
    if any(result.iterdir()):
        raise NavigationError('output directory must be empty; previous evidence is preserved')
    return result


def source_hashes(tool):
    files = [tool, tool.with_name('graph_find.py')]
    root = next((p for p in tool.parents if (p / 'packages/core').is_dir()), None)
    if root:
        files.extend(sorted((root / 'packages/core').glob('*.py')))
        files.extend(p for p in [root / 'pyproject.toml', root / 'package.json'] if p.is_file())
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}


class PipeSession:
    """Drain both pipes without unbounded communicate/readline buffers."""
    def __init__(self, argv, timeout=45, response_limit=524288, total_limit=2097152,
                 stderr_limit=65536, run_limit=90):
        self.argv, self.timeout = argv, timeout
        self.response_limit, self.total_limit = response_limit, total_limit
        self.stderr_limit, self.run_limit = stderr_limit, run_limit
        self.stdout_total = 0
        self.stderr = bytearray()
        self.pending = bytearray()
        self.active_seconds = 0.0
        self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, bufsize=0,
                                        start_new_session=True,
                                        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.selector = selectors.DefaultSelector()
        for stream, name in [(self.process.stdout, 'stdout'), (self.process.stderr, 'stderr')]:
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, name)

    def _receive(self, wait):
        for key, _ in self.selector.select(wait):
            data = os.read(key.fileobj.fileno(), 65536)
            if not data:
                self.selector.unregister(key.fileobj)
                continue
            if key.data == 'stderr':
                room = self.stderr_limit - len(self.stderr)
                self.stderr.extend(data[:room])
                if len(data) > room:
                    raise NavigationError('stderr byte limit exceeded')
            else:
                self.stdout_total += len(data)
                room = self.response_limit + 1 - len(self.pending)
                self.pending.extend(data[:max(0, room)])
                if self.stdout_total > self.total_limit:
                    raise NavigationError('total stdout byte limit exceeded')
                if len(data) > room or (len(self.pending) > self.response_limit and b'\n' not in self.pending):
                    raise NavigationError('response byte limit exceeded')

    def request(self, action):
        raw = json.dumps(action, separators=(',', ':')).encode() + b'\n'
        if len(raw) > 16384:
            raise NavigationError('action exceeds native input byte limit')
        started = time.monotonic()
        try:
            self.process.stdin.write(raw)
            self.process.stdin.flush()
            while b'\n' not in self.pending:
                elapsed = time.monotonic() - started
                if elapsed > self.timeout or self.active_seconds + elapsed > self.run_limit:
                    raise NavigationError('navigation time limit exceeded')
                self._receive(min(0.1, self.timeout - elapsed))
                if not self.selector.get_map() and b'\n' not in self.pending:
                    raise NavigationError(f'tool exited {self.process.poll()}: {self.stderr.decode("utf-8", "replace")}')
            line, _, rest = self.pending.partition(b'\n')
            self.pending = bytearray(rest)
            if len(line) + 1 > self.response_limit:
                raise NavigationError('response byte limit exceeded')
            result = json.loads(line)
            if not isinstance(result, dict) or result.get('schema_version') != 'graph-tools-v1':
                raise NavigationError('unexpected tool response schema')
            return result
        except (BrokenPipeError, UnicodeError, json.JSONDecodeError) as error:
            raise NavigationError(str(error)) from error
        finally:
            self.active_seconds += time.monotonic() - started

    def close(self):
        if hasattr(self, 'cleanup'):
            return self.cleanup
        failure = None
        term_sent = blocked = False
        ownership = None
        signal_attempts = []
        group_id = self.process.pid
        leader_exited_before_cleanup = self.process.poll() is not None
        try:
            # An already-reaped leader provides no live ownership target. Its
            # group/descendants are unknown; do not probe or signal that group.
            if not leader_exited_before_cleanup:
                try:
                    ownership = {'pid': group_id, 'pgid': os.getpgid(group_id),
                                 'sid': os.getsid(group_id), 'launcher_uid': os.getuid(),
                                 'launcher_euid': os.geteuid()}
                    if ownership['pgid'] != group_id or ownership['sid'] != group_id:
                        failure = 'private session ownership check failed; no signal sent'
                    elif self.process.poll() is None:
                        attempt = {'signal': int(signal.SIGTERM)}
                        signal_attempts.append(attempt)
                        # Single live-owned TERM precedes stdin EOF. No later
                        # group probe, KILL, or individual-signal fallback.
                        os.killpg(group_id, signal.SIGTERM)
                        term_sent = True
                        attempt['status'] = 'accepted'
                except ProcessLookupError:
                    if signal_attempts:
                        signal_attempts[-1]['status'] = 'target_absent_at_signal'
                    # A live-check/signal race is possible. Wait only for the
                    # direct child; never retry this target.
                except PermissionError as error:
                    blocked = True
                    failure = f'owned process group cleanup blocked: {error}'
                    if signal_attempts:
                        signal_attempts[-1].update(status='blocked', error=str(error))
                except OSError as error:
                    failure = f'owned process group cleanup failed: {error}'
                    if signal_attempts:
                        signal_attempts[-1].update(status='failed', error=str(error))
            self.process.stdin.close()
            deadline = time.monotonic() + 5
            while self.selector.get_map() and time.monotonic() < deadline:
                try:
                    self._receive(0.05)
                except NavigationError as error:
                    failure = failure or str(error)
                    break
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                failure = failure or 'owned child not reaped before cleanup deadline'
        finally:
            self.selector.close()
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                stream.close()
        expected_term_exit = term_sent and self.process.returncode == -signal.SIGTERM
        self.cleanup = {'pid': self.process.pid, 'process_group_id': group_id,
                        'private_session': True, 'live_ownership_observed': ownership,
                        'leader_exited_before_cleanup': leader_exited_before_cleanup,
                        'group_term_sent': term_sent, 'group_kill_sent': False,
                        'returncode': self.process.returncode, 'expected_term_exit': expected_term_exit,
                        'abnormal_exit': self.process.returncode not in (0, None) and not expected_term_exit,
                        'group_signal_attempts': signal_attempts, 'signal_blocked': blocked,
                        'group_status': 'unknown', 'descendant_reaping': 'not_observed_by_launcher',
                        'reaped': self.process.poll() is not None, 'cleanup_error': failure}
        return self.cleanup


class Guide:
    def __init__(self):
        self.identity = {}
        self.nodes = {}
        self.choices = []
        self.build_query = None
        self.inspection = None
        self.last_file = None
        self.recovered_files = []

    def accept(self, response, request=None):
        identity = {k: response[k] for k in ('head', 'branch', 'snapshot_sha256')}
        if self.identity and identity != self.identity:
            raise NavigationError('tool identity changed; start a new session')
        self.identity = identity
        result = response.get('result', {})
        for node in result.get('nodes', []):
            self.nodes[node['id']] = node
        self.choices = list(self.nodes)
        self.recovered_files = []
        if response['status'] == 'ok' and request and request['op'] in ('build', 'expand'):
            self.recovered_files = [n['id'] for n in result.get('nodes', []) if n['kind'] == 'file']
            # Native admission revalidates existing files but omits duplicate
            # nodes. Keep that exact scoped, previously returned file selectable.
            scoped_id = 'file:' + request.get('scope', '')
            if (request['op'] == 'build' and result.get('eligible_files') == 1 and
                    scoped_id in self.nodes and self.nodes[scoped_id]['kind'] == 'file' and
                    scoped_id not in self.recovered_files):
                self.recovered_files.append(scoped_id)
        if request and request['op'] == 'read':
            self.last_file = None
            document = result.get('document')
            if response['status'] == 'ok' and document and document.get('kind') == 'file':
                self.last_file = document
        if request and request['op'] == 'build':
            self.inspection = None
            self.build_query = request.get('intent') if response['status'] == 'ok' else None
        elif request and request['op'] == 'inspect':
            self.inspection = None
            if response['status'] == 'ok':
                offset = request.get('offset', 0)
                limit = request.get('limit', 2)
                eligible = result['eligible_files']
                count = len(result.get('candidates', []))
                self.inspection = {'query': request.get('query', self.build_query),
                    'offset': offset, 'limit': limit, 'eligible_files': eligible,
                    'count': count, 'next_available': count > 0 and offset + limit < eligible}

    def selected(self, value):
        if value.isdecimal():
            index = int(value) - 1
            if index < 0 or index >= len(self.choices):
                raise NavigationError('choice is outside returned node list')
            return self.choices[index]
        if value not in self.nodes:
            raise NavigationError('select a returned built node; inspect or recover first')
        return value

    def action(self, step, limit=2):
        command, _, value = step.partition(':')
        if command == 'inspect':
            self.inspection = None
            action = {'op': 'inspect', 'limit': limit, 'offset': 0}
            if value:
                action['query'] = value
        elif command == 'inspect-next' and not value:
            page = self.inspection
            if page is None:
                raise NavigationError('inspect-next requires a successful inspection; use inspect first')
            if not page['next_available']:
                raise NavigationError('no next candidate page; use inspect or inspect:new question to restart')
            action = {'op': 'inspect', 'limit': page['limit'],
                      'offset': min(page['offset'] + page['limit'], page['eligible_files'])}
            if page['query'] is not None:
                action['query'] = page['query']
        elif command == 'recover' and value:
            action = {'op': 'expand', 'query': value, 'limit': limit}
        elif command == 'recover-imports' and not value:
            document = self.last_file
            if not document or not document['path'].endswith('.py'):
                raise NavigationError('recover-imports requires a successful complete Python file read')
            raw = document['text'].encode('utf-8')
            if (document.get('byte_start') != 0 or document.get('byte_end') != len(raw) or
                    hashlib.sha256(raw).hexdigest() != document.get('source_sha256') or
                    document.get('excerpt_sha256') != document.get('source_sha256')):
                raise NavigationError('complete source witness does not match')
            path = PurePosixPath(document['path'])
            if path.is_absolute() or '..' in path.parts:
                raise NavigationError('unsafe source path')
            try:
                tree = ast.parse(document['text'])
            except SyntaxError as error:
                raise NavigationError('Python import witness unavailable') from error
            modules = sorted({alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                              for alias in node.names if '.' not in alias.name and
                              alias.name not in sys.stdlib_module_names})
            if len(modules) != 1:
                raise NavigationError('recover-imports requires exactly one non-stdlib sibling candidate')
            # This is a syntactic sibling candidate, not proof of runtime binding.
            # Native scoped construction still owns admission and freshness.
            action = {'op': 'build', 'intent': self.build_query, 'limit': 1,
                      'scope': str(path.parent / (modules[0] + '.py'))}
        elif command == 'read-recovered' and value.isdecimal():
            index = int(value) - 1
            if index < 0 or index >= len(self.recovered_files):
                raise NavigationError('select a file returned by the latest successful recovery')
            action = {'op': 'read', 'id': self.selected(self.recovered_files[index])}
        elif command in ('read', 'imports') and value:
            action = {'op': 'read' if command == 'read' else 'expand', 'id': self.selected(value)}
            if command == 'imports':
                action['limit'] = limit
        elif command == 'read-file' and value:
            key = 'file:' + value
            if '/' not in value and key not in self.nodes:
                matches = [n['id'] for n in self.nodes.values() if n['kind'] == 'file' and
                           PurePosixPath(n['path']).name == value]
                if len(matches) != 1:
                    raise NavigationError('file basename must match exactly one returned built file')
                key = matches[0]
            action = {'op': 'read', 'id': self.selected(key)}
        elif command == 'read-unit' and '::' in value:
            path, label = value.split('::', 1)
            matches = [n['id'] for n in self.nodes.values() if n.get('path') == path
                       and n.get('label') == label and n['kind'] in ('unit', 'unresolved_unit')]
            if len(matches) != 1:
                raise NavigationError('unit selector must match exactly one returned path and label')
            action = {'op': 'read', 'id': matches[0]}
        else:
            raise NavigationError('use inspect[:question], inspect-next, recover:question, recover-imports, read-recovered:number, imports:choice, read:choice, read-file:path-or-basename, read-unit:path::label, or quit')
        return {**action, **self.identity}

    def show(self, response):
        print(f"\n{response['status']}: {response['reason']}")
        print('Identity:', json.dumps(self.identity, sort_keys=True))
        print('Shared content budget (bytes):', json.dumps(response['budget'], sort_keys=True))
        print('Observed cost/scan:', json.dumps({'cost': response['cost'], 'scan': response['scan']}, sort_keys=True))
        print('Source remains authoritative; completeness unassessed; sufficient=false; authority_bearing=false.')
        print('Provider calls: 0; receiving/generated tokens and physical I/O bytes: unknown.')
        result = response.get('result', {})
        if 'candidates' in result and self.inspection is not None:
            page = self.inspection
            if page['count']:
                first = page['offset'] + 1
                last = min(page['offset'] + page['count'], page['eligible_files'])
                print(f"Candidate page: {first}-{last} of {page['eligible_files']}")
            else:
                print(f"Candidate page: empty at offset {page['offset']} of {page['eligible_files']}")
            print('Next page: inspect-next' if page['next_available'] else 'Next page: unavailable')
        for field in ('mechanism', 'relations_supported', 'eligible_files', 'omitted_files',
                      'unbuilt_files', 'omitted_targets', 'duplicate'):
            if field in result:
                print(f'{field}: {result[field]}')
        for edge in result.get('edges', []):
            print('Witnessed local Python import:', json.dumps(edge, sort_keys=True))
        for index, key in enumerate(self.choices, 1):
            node = self.nodes[key]
            bounds = f" [{node.get('byte_start')}:{node.get('byte_end')}]" if 'byte_start' in node else ''
            print(f"  {index}. {node['kind']} {node.get('label', key)}{bounds}\n     {key}")
        for candidate in response.get('result', {}).get('candidates', []):
            print(f"  Candidate {'built' if candidate['built'] else 'unbuilt (recover before read)'}: {candidate['id']}")
        document = response.get('result', {}).get('document')
        if document:
            print(f"--- Complete {document['kind']} {document['path']} SHA256={document['excerpt_sha256']} ---")
            print(document['text'])
        if response.get('result', {}).get('fallback_obligations'):
            print('Explicit file fallback:', json.dumps(response['result']['fallback_obligations']))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--question', required=True)
    parser.add_argument('--python', required=True)
    parser.add_argument('--tool', required=True)
    parser.add_argument('--byte-budget', type=int, default=32768)
    parser.add_argument('--limit', type=int, default=2)
    parser.add_argument('--exclude-path-prefix', action='append', default=[])
    parser.add_argument('--step', action='append', default=[], help='ordered user choices; omit for interactive mode')
    parser.add_argument('--output', required=True, help='new empty directory below the evidence root')
    parser.add_argument('--evidence-root', required=True, help='existing owned absolute directory outside source')
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 64 or not 1 <= args.byte_budget <= 134217728:
        parser.error('limit must be 1..64 and byte budget 1..134217728')
    if len(args.step) > 31 or not args.question.strip() or len(args.question) > 4096:
        parser.error('use a nonempty question <=4096 characters and at most 31 follow-up steps')
    started = time.monotonic()
    session = None
    receipt = {'question': args.question, 'actions': [], 'provider_calls': 0,
               'launcher_sha256_before': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'generated_tokens': None, 'physical_io_bytes': None,
               'quality_or_completeness_assessed': False, 'limits': {'response_bytes': 524288,
               'stdout_bytes': 2097152, 'stderr_bytes': 65536, 'action_seconds': 45,
               'active_run_seconds': 90, 'actions': 32}}
    code = 0
    try:
        destination = output_dir(args.output, evidence_root=args.evidence_root, source_root=args.root)
        tool = Path(args.tool)
        receipt['source_sha256_before'] = source_hashes(tool)
        native_argv = [args.python, '-B', str(tool), '--root', args.root,
                       '--byte-budget', str(args.byte_budget)]
        for prefix in args.exclude_path_prefix:
            native_argv.extend(['--exclude-path-prefix', prefix])
        receipt['argv'] = native_argv
        session = PipeSession(native_argv)
        guide = Guide()
        with (destination / 'responses.jsonl').open('x') as responses:
            action = {'op': 'build', 'intent': args.question, 'limit': args.limit}
            remaining = iter(args.step)
            while True:
                response = session.request(action)
                receipt['actions'].append({'request': action, 'status': response['status'], 'reason': response['reason']})
                responses.write(json.dumps(response, sort_keys=True) + '\n')
                responses.flush()
                guide.accept(response, action)
                guide.show(response)
                receipt['last_budget'] = response['budget']
                receipt['last_cost'] = response['cost']
                receipt['scan'] = response['scan']
                receipt['identity'] = guide.identity
                if response['status'] != 'ok':
                    code = 2
                if len(receipt['actions']) >= 32:
                    break
                if args.step:
                    step = next(remaining, None)
                    if step is None:
                        break
                    action = guide.action(step, args.limit)
                else:
                    while True:
                        try:
                            step = input('\nChoice (inspect, inspect-next, recover:question, imports:number, read:number, quit): ').strip()
                        except EOFError:
                            step = 'quit'
                        if step == 'quit':
                            action = None
                            break
                        try:
                            action = guide.action(step, args.limit)
                            break
                        except NavigationError as error:
                            print(str(error), file=sys.stderr)
                    if action is None:
                        break
    except KeyboardInterrupt:
        code = 130
        receipt['error'] = 'interrupted by operator'
        print('guided: interrupted by operator', file=sys.stderr)
    except (NavigationError, OSError, KeyError) as error:
        code = 2
        receipt['error'] = str(error)
        print(f'guided: {error}', file=sys.stderr)
    finally:
        if session:
            receipt['cleanup'] = session.close()
            receipt['stdout_wire_bytes'] = session.stdout_total
            receipt['stderr_bytes'] = len(session.stderr)
            receipt['active_navigation_seconds'] = round(session.active_seconds, 6)
            if (receipt['cleanup']['abnormal_exit'] or receipt['cleanup']['cleanup_error'] or
                    not receipt['cleanup']['reaped']) and code != 130:
                code = 2
            (destination / 'stderr.txt').write_bytes(session.stderr)
        receipt['elapsed_seconds_including_acquisition_reads_cleanup'] = round(time.monotonic() - started, 6)
        receipt['exit_code'] = code
        receipt['launcher_sha256_after'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if 'destination' in locals():
            receipt['source_sha256_after'] = source_hashes(Path(args.tool))
            (destination / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
