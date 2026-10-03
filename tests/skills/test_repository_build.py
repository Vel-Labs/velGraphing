"""Behavioral CLI tests for one persistent map and conservative full updates."""
from pathlib import Path
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
CLI = ROOT / 'plugins/graph-engineering/skills/graph-engineering/scripts/graphctl.py'
spec = importlib.util.spec_from_file_location('build_graphctl', CLI)
ctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctl)
from packages.core.repository_build import validate_manifest, python_import_relations


class RepositoryBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name).resolve()
        self.root = self.work / 'repo'
        self.root.mkdir()
        self.files = {
            'app/__init__.py': b'',
            'app/main.py': b'from .reader import authenticate\n\ndef deliver(x, y):\n    return authenticate(x, y)\n',
            'app/reader.py': b'def authenticate(actual, expected):\n    if actual != expected:\n        raise ValueError("retired_marker_xyz")\n    return actual\n',
        }
        for name, raw in self.files.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
        self.inventory = self.work / 'inventory.json'
        self.inventory.write_text(json.dumps(list(self.files)))

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, arguments, expected=0):
        out, err = io.StringIO(), io.StringIO()
        # emit's default stream was bound at import time. Capture that actual stream.
        def emit(value, stream=None):
            target = err if stream is sys.stderr else out
            target.write(json.dumps(value) + '\n')
        with patch.object(ctl, 'emit', side_effect=emit):
            code = ctl.main(arguments)
        self.assertEqual(code, expected, err.getvalue())
        return json.loads(out.getvalue() if code == 0 else err.getvalue())

    def build(self, name, previous=None, extra=(), expected=0):
        output = self.work / name
        args = ['retrievel-build', '--root', str(self.root), '--include', '.',
                '--inventory', str(self.inventory), '--output', str(output), '--namespace', 'fixture']
        if previous:
            args += ['--previous', str(self.work / previous)]
        receipt = self.run_cli([*args, *extra], expected)
        if expected:
            return receipt
        manifest = json.loads(output.read_text())
        validate_manifest(manifest)
        return receipt, manifest

    def test_repeat_identical_map_and_hash_bound_symbol_relationship_views(self):
        _, first = self.build('first.json')
        receipt, second = self.build('second.json', 'first.json')
        self.assertEqual(first, second)
        self.assertEqual((self.work / 'first.json').read_bytes(), (self.work / 'second.json').read_bytes())
        self.assertEqual(receipt['changes']['unchanged'], 3)
        self.assertFalse(receipt['changes']['changed'])
        symbol = next(s for s in first['symbols'] if s['name'] == 'authenticate')
        raw = self.files['app/reader.py']
        excerpt = raw[symbol['byte_start']:symbol['byte_end']]
        self.assertIn(b'if actual != expected:', excerpt)
        self.assertEqual(symbol['excerpt_sha256'], hashlib.sha256(excerpt).hexdigest())
        edge = first['relationships'][0]
        self.assertEqual(edge['target_id'], 'repo:app/reader.py')
        witness = edge['witness']
        raw = self.files['app/main.py']
        self.assertEqual(witness['excerpt_sha256'], hashlib.sha256(raw[witness['byte_start']:witness['byte_end']]).hexdigest())
        result = self.run_cli(['retrievel-search', '--map', str(self.work / 'first.json'), '--query', 'authenticate'])
        self.assertIn('app/reader.py', [h['path'] for h in result['hits']])
        self.assertEqual(result['hits'][0]['path'], 'app/reader.py')
        self.assertTrue(result['hits'][0]['exact_declaration_match'])
        self.assertEqual(result['freshness'], 'not_checked')

    def test_changed_deleted_renamed_inputs_remove_postings_symbols_and_dependents(self):
        _, first = self.build('before.json')
        # Source mutation is confined to this disposable fixture. Keep the importer
        # unchanged: a full rebuild must still invalidate its former import target.
        (self.root / 'app/reader.py').unlink()
        (self.root / 'app/replacement.py').write_bytes(b'def new_guard(x):\n    return x\n')
        (self.root / 'app/__init__.py').write_bytes(b'# changed package exports\n')
        self.inventory.write_text(json.dumps([*self.files, 'app/replacement.py']))
        receipt, current = self.build('after.json', 'before.json')
        self.assertEqual(receipt['changes']['removed'], ['app/reader.py'])
        self.assertEqual(receipt['changes']['added'], ['app/replacement.py'])
        self.assertEqual(receipt['changes']['changed'], ['app/__init__.py'])
        self.assertNotIn('retired-marker-xyz', current['keywords'])
        self.assertFalse(any(s['source_path'] == 'app/reader.py' for s in current['symbols']))
        self.assertFalse(current['relationships'])
        self.assertNotEqual(first['snapshot'], current['snapshot'])
        self.assertEqual(receipt['scan']['unsupported'], [{'path': 'app/reader.py', 'reason': 'deleted_or_missing'}])

    def test_exclusion_is_before_bytes_and_limits_are_honest(self):
        paths = [*self.files, '.env.production', 'private/note.txt',
                 'plugins/graph-engineering/runtime/copy.py', 'huge.txt', 'binary.dat']
        for name in paths[len(self.files):]:
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'\xff' if name == 'binary.dat' else b'x' * 300)
        self.inventory.write_text(json.dumps(paths))
        original = ctl.safe_file_bytes
        def guarded(path, metadata, maximum):
            self.assertFalse(path.name.startswith('.env'))
            self.assertNotIn('private', path.relative_to(self.root).parts)
            self.assertNotIn('runtime', path.relative_to(self.root).parts)
            return original(path, metadata, maximum)
        with patch.object(ctl, 'safe_file_bytes', side_effect=guarded):
            receipt, manifest = self.build('filtered.json', extra=('--max-file-bytes', '200'))
        self.assertEqual(receipt['scan']['excluded_counts']['sensitive'], 2)
        self.assertEqual(receipt['scan']['excluded_counts']['generated_or_local'], 1)
        self.assertEqual({x['reason'] for x in receipt['scan']['unsupported']}, {'invalid_utf8', 'max_file_bytes'})
        self.assertFalse(receipt['scan']['declared_inventory_complete'])
        self.assertNotIn('private/note.txt', json.dumps(manifest))
        self.assertEqual(len(manifest['files']), 3)

    def test_no_repository_write_overwrite_traversal_symlink_or_hardlink(self):
        self.build('existing.json')
        saved = (self.work / 'existing.json').read_bytes()
        error = self.build('existing.json', expected=2)
        self.assertIn('already exists', error['error'])
        self.assertEqual(saved, (self.work / 'existing.json').read_bytes())
        for path in ('../escape.py', '/absolute.py'):
            self.inventory.write_text(json.dumps([path]))
            self.build('invalid.json', expected=2)
            self.assertFalse((self.work / 'invalid.json').exists())
        self.inventory.write_text(json.dumps(['alias.py']))
        (self.root / 'alias.py').symlink_to(self.root / 'app/reader.py')
        self.build('alias-map.json', expected=2)
        args = ['retrievel-build', '--root', str(self.root), '--include', '.', '--inventory', str(self.inventory),
                '--output', str(self.root / 'forbidden-map.json')]
        self.run_cli(args, 2)
        self.assertFalse((self.root / 'forbidden-map.json').exists())
        import os
        os.link(self.root / 'app/reader.py', self.root / 'hardlink.py')
        self.inventory.write_text(json.dumps(['hardlink.py']))
        self.build('hardlink-map.json', expected=2)

    def test_unparseable_python_and_physical_byte_import_witness(self):
        bad = self.root / 'bad.py'
        bad.write_bytes(b'def broken(:\n')
        self.inventory.write_text(json.dumps([*self.files, 'bad.py']))
        _, manifest = self.build('syntax.json')
        self.assertEqual(next(f for f in manifest['files'] if f['source_path'] == 'bad.py')['symbol_status'], 'parse_unavailable')
        self.assertFalse(any(s['source_path'] == 'bad.py' for s in manifest['symbols']))
        # BOM, CRLF and a Unicode separator inside a literal must not shift AST
        # line numbers away from physical source bytes.
        raw = b'\xef\xbb\xbftext = "caf\xc3\xa9\xe2\x80\xa8separator"\r\nfrom .reader import authenticate\r\n'
        edge = python_import_relations(raw, 'app/unicode.py', self.files)[0]
        witness = edge['witness']
        self.assertEqual(raw[witness['byte_start']:witness['byte_end']], b'from .reader import authenticate\r\n')
        bad_manifest = dict(manifest, namespace='tampered')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            validate_manifest(bad_manifest)

    def test_git_inventory_filters_ignored_tracked_files_before_source_reads(self):
        import subprocess
        builder, adapter, identity = ctl.repository_modules()
        paths = [*self.files, 'ignored.py']
        (self.root / 'ignored.py').write_bytes(b'never read this fixture marker\n')
        def git(root, *args):
            self.assertIn('--cached', args)
            self.assertIn('--others', args)
            self.assertIn('--exclude-standard', args)
            return b'\0'.join(p.encode() for p in paths) + b'\0'
        def check_ignore(args, **options):
            self.assertIn('--no-index', args)
            self.assertIn(b'ignored.py\0', options['input'])
            return subprocess.CompletedProcess(args, 0, b'ignored.py\0', b'')
        original = ctl.safe_file_bytes
        def read(path, metadata, maximum):
            self.assertNotEqual(path.name, 'ignored.py')
            return original(path, metadata, maximum)
        output = self.work / 'git-mode.json'
        with patch.object(ctl, 'repository_modules', return_value=(builder, adapter, identity)), \
             patch.object(adapter, '_repository_root'), patch.object(adapter, '_git', side_effect=git), \
             patch.object(ctl.subprocess, 'run', side_effect=check_ignore), \
             patch.object(ctl, 'safe_file_bytes', side_effect=read):
            receipt = self.run_cli(['retrievel-build', '--root', str(self.root), '--include', '.', '--output', str(output)])
        self.assertEqual(receipt['scan']['excluded_counts']['ignored'], 1)
        self.assertEqual(receipt['counts']['files'], 3)

    def test_document_components_for_search_inventory_and_previous(self):
        self.build('direct.json')
        nested = self.work / 'documents/nested'
        nested.mkdir(parents=True)
        (nested / 'map.json').write_bytes((self.work / 'direct.json').read_bytes())
        (nested / 'inventory.json').write_bytes(self.inventory.read_bytes())
        alias = self.work / 'alias-parent'
        alias.symlink_to(nested, target_is_directory=True)
        leaf_map = self.work / 'alias-map.json'
        leaf_map.symlink_to(nested / 'map.json')
        leaf_inventory = self.work / 'alias-inventory.json'
        leaf_inventory.symlink_to(nested / 'inventory.json')
        for document in (self.work / 'direct.json', nested / 'map.json'):
            result = self.run_cli(['retrievel-search', '--map', str(document), '--query', 'authenticate'])
            self.assertEqual(result['hits'][0]['path'], 'app/reader.py')
        for label, document in [('parent', alias / 'map.json'), ('leaf', leaf_map)]:
            with self.subTest(consumer='search', alias=label):
                self.run_cli(['retrievel-search', '--map', str(document), '--query', 'authenticate'], 2)
            with self.subTest(consumer='previous', alias=label):
                output = self.work / (label + '-previous-output.json')
                self.run_cli(['retrievel-build', '--root', str(self.root), '--include', '.',
                              '--inventory', str(self.inventory), '--namespace', 'fixture',
                              '--previous', str(document), '--output', str(output)], 2)
                self.assertFalse(output.exists())
        for label, document in [('parent', alias / 'inventory.json'), ('leaf', leaf_inventory)]:
            with self.subTest(consumer='inventory', alias=label):
                output = self.work / (label + '-inventory-output.json')
                self.run_cli(['retrievel-build', '--root', str(self.root), '--include', '.',
                              '--inventory', str(document), '--output', str(output)], 2)
                self.assertFalse(output.exists())
        # A plain nested parent remains usable for both build input consumers.
        output = self.work / 'valid-nested-inputs.json'
        self.run_cli(['retrievel-build', '--root', str(self.root), '--include', '.',
                      '--inventory', str(nested / 'inventory.json'), '--namespace', 'fixture',
                      '--previous', str(nested / 'map.json'), '--output', str(output)])
        self.assertEqual(output.read_bytes(), (self.work / 'direct.json').read_bytes())
        # No lexical normalization may hide traversal through an alias.
        self.run_cli(['retrievel-search', '--map', str(alias) + '/../direct.json', '--query', 'authenticate'], 2)

    def test_output_alias_contract_and_valid_nested_output(self):
        self.build('direct.json')
        nested = self.work / 'outputs/nested'
        nested.mkdir(parents=True)
        alias = self.work / 'alias-output-parent'
        alias.symlink_to(nested, target_is_directory=True)
        leaf = self.work / 'alias-output.json'
        leaf.symlink_to(self.work / 'direct.json')
        saved = (self.work / 'direct.json').read_bytes()
        base = ['retrievel-build', '--root', str(self.root), '--include', '.',
                '--inventory', str(self.inventory), '--namespace', 'fixture']
        for target in (alias / 'new-map.json', leaf):
            with self.subTest(output=target):
                self.run_cli([*base, '--output', str(target)], 2)
        self.assertFalse((nested / 'new-map.json').exists())
        self.assertEqual(saved, (self.work / 'direct.json').read_bytes())
        self.run_cli([*base, '--output', str(nested / 'valid-map.json')])
        self.assertEqual((nested / 'valid-map.json').read_bytes(), saved)


if __name__ == '__main__':
    unittest.main(verbosity=2)
