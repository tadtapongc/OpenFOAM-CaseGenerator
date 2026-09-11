"""Regression coverage for the September 2026 exploration findings."""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, PropertyMock

from rapidfoam.config import load_config, validate
from rapidfoam.geometry import compute_mesh_params
from rapidfoam.web import server
from rapidfoam.web.ssh_client import ClusterSSHClient


class ReportFixesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(server, 'PROJECT_ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        (self.root / 'stl').mkdir()
        sample = Path(__file__).resolve().parents[1] / 'stl/geometry.stl'
        (self.root / 'stl/body.stl').write_bytes(sample.read_bytes())
        self.cfg = {'case_name': 'test', 'stl_files': ['body.stl']}

    def test_validate_and_save_never_generate_or_overwrite_case(self):
        case = self.root / 'cases/test/system/controlDict'
        case.parent.mkdir(parents=True)
        case.write_text('existing solver state')
        with patch('rapidfoam.cli._do_generate') as generate:
            result = asyncio.run(server.api_case_validate(server.GenerateCaseRequest(config=self.cfg)))
            self.assertTrue(result['success'])
            self.assertFalse((self.root / 'configs').exists())
            # Legacy validation flags also stay read-only.
            asyncio.run(server.api_case_generate_and_submit(server.GenerateCaseRequest(config=self.cfg, generate_locally=False)))
            self.assertFalse((self.root / 'configs').exists())
            asyncio.run(server.api_case_generate_and_submit(server.GenerateCaseRequest(config=self.cfg, generate_locally=False, save_config=True)))
            generate.assert_not_called()
        self.assertEqual(case.read_text(), 'existing solver state')
        self.assertEqual(json.loads((self.root / 'configs/test.json').read_text()), self.cfg)

    def test_generation_system_exit_is_http_error(self):
        with patch('rapidfoam.cli._do_generate', side_effect=SystemExit('invalid STL')):
            with self.assertRaises(server.HTTPException) as caught:
                asyncio.run(server.api_case_generate_and_submit(server.GenerateCaseRequest(config=self.cfg)))
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn('invalid STL', caught.exception.detail)

    def test_submission_failure_is_http_error(self):
        with patch.object(ClusterSSHClient, 'is_connected', new_callable=PropertyMock, return_value=True), \
             patch.object(server.ssh_client, 'upload_file'), patch.object(server.ssh_client, 'upload_text'), \
             patch.object(server.ssh_client, 'submit_job', return_value={'success': False, 'error': 'quota exceeded'}):
            with self.assertRaises(server.HTTPException) as caught:
                asyncio.run(server.api_case_generate_and_submit(server.GenerateCaseRequest(
                    config=self.cfg, generate_locally=False, upload_to_cluster=True, submit_slurm=True)))
        self.assertEqual(caught.exception.detail, 'quota exceeded')

    def test_cfmesh_sizes_reach_writer_and_validate(self):
        from rapidfoam.cli import _do_generate
        self.cfg['overrides'] = {'mesh_params': {'boundary_cell_size': 0.0123, 'ground_cell_size': 0.0456}}
        cfg_path = self.root / 'input.json'
        cfg_path.write_text(json.dumps(self.cfg))
        cfg = load_config(cfg_path)
        mesh = compute_mesh_params(cfg, ((0, 0, 0), (1, 2, 3)))
        self.assertEqual(mesh['boundary_cell_size'], 0.0123)
        self.assertEqual(mesh['ground_cell_size'], 0.0456)
        with contextlib.redirect_stdout(io.StringIO()):
            _do_generate(cfg_path, self.root)
        text = (self.root / 'cases/test/system/meshDict').read_text()
        self.assertIn('0.0123', text)
        self.assertIn('0.0456', text)
        cfg['mesh_params']['boundary_cell_size'] = -1
        self.assertTrue(any('boundary_cell_size' in e for e in validate(cfg, self.root)[0]))
        cfg['turbulence']['model'] = 'kEpsilon'
        self.assertTrue(any('kOmegaSST' in e for e in validate(cfg, self.root)[0]))

    def test_running_status_uses_log_timestamp(self):
        case = self.root / 'cases/test'
        case.mkdir(parents=True)
        log = case / 'log.simpleFoam'
        log.write_text('Time = 25\n')
        os.utime(case, (1, 1))
        result = asyncio.run(server.api_list_cases())
        self.assertEqual(next(c for c in result if c['name'] == 'test')['status'], 'Solving')

    def test_remote_force_reader_and_archive_execute_shared_parser(self):
        case = self.root / 'cases/test'
        case.mkdir(parents=True)
        (case / 'case_config.json').write_text(json.dumps({
            'outputs': {'drag_axis': '+x', 'downforce_axis': '+z'},
            'patches': {'symmetry': 'center'}, 'domain_faces': {'-y': 'center'},
        }))
        for segment, contents in [('2', '2 (3 0 4) (0 0 0) (0 0 0)\n20 (90 0 80) (0 0 0) (0 0 0)\n'),
                                  ('10', '10 (5 0 6) (0 0 0) (0 0 0)\n11 (nan 0 9) (0 0 0) (0 0 0)\n')]:
            path = case / 'processor0/postProcessing/forces' / segment / 'force.dat'
            path.parent.mkdir(parents=True)
            path.write_text(contents)
        client = ClusterSSHClient()
        client.remote_repo_path = str(self.root)
        def execute(command, timeout=None):
            args = shlex.split(command)
            stream = io.StringIO()
            with patch.object(sys, 'argv', ['-c'] + args[3:]), contextlib.redirect_stdout(stream):
                exec(args[2], {})
            return 0, stream.getvalue(), ''
        with patch.object(client, 'run_command', side_effect=execute), \
             patch.object(ClusterSSHClient, 'is_connected', new_callable=PropertyMock, return_value=True):
            data = client.read_case_forces('test')
            self.assertEqual(data['times'], [2, 10])
            self.assertEqual(data['drag'], [6, 10])
            self.assertEqual(data['downforce'], [8, 12])
            summary = client.list_remote_cases_detailed()[0]
            self.assertEqual(summary['latest_iter'], 10)
            self.assertEqual(summary['drag'], 8)
            self.assertEqual(summary['downforce'], 10)

    def test_remote_telemetry_uses_remote_configuration(self):
        with patch.object(ClusterSSHClient, 'is_connected', new_callable=PropertyMock, return_value=True), \
             patch.object(server.ssh_client, 'read_case_forces', return_value={
                 'times': [1, 2], 'drag': [10, 10], 'downforce': [40, 40], 'is_symmetry': True}):
            result = asyncio.run(server.api_telemetry_forces('test'))
        self.assertTrue(result['is_symmetry'])
        self.assertEqual(result['series']['downforce'], [40, 40])

    def test_ssh_drains_both_streams_before_exit_status(self):
        out = [b'x' * 65536, b'end']
        err = [b'e' * 65536, b'error']
        channel = Mock()
        channel.recv_ready.side_effect = lambda: bool(out)
        channel.recv_stderr_ready.side_effect = lambda: bool(err)
        channel.recv.side_effect = lambda n: out.pop(0)
        channel.recv_stderr.side_effect = lambda n: err.pop(0)
        channel.exit_status_ready.side_effect = lambda: not out and not err
        def status():
            self.assertFalse(out or err)
            return 0
        channel.recv_exit_status.side_effect = status
        client = ClusterSSHClient()
        client._client = Mock()
        client._client.exec_command.return_value = (Mock(), Mock(channel=channel), Mock())
        code, stdout, stderr = client.run_command('test')
        self.assertEqual(code, 0)
        self.assertTrue(stdout.endswith('end'))
        self.assertTrue(stderr.endswith('error'))
        channel.close.assert_called_once()

    def test_ssh_uses_known_hosts_and_rejects_unknown_keys(self):
        from rapidfoam.web import ssh_client as module
        client = ClusterSSHClient()
        with patch.object(module.paramiko, 'SSHClient') as factory, \
             patch.object(module.paramiko, 'RejectPolicy') as policy, \
             patch.object(client, 'test_connection', return_value={'connected': True}):
            client.connect('cluster.example', 'test')
            factory.return_value.load_system_host_keys.assert_called_once_with()
            factory.return_value.set_missing_host_key_policy.assert_called_once_with(policy.return_value)

    def test_launcher_only_restarts_when_requested(self):
        for restart in (False, True):
            with self.subTest(restart=restart), patch.object(sys, 'argv', ['rapidfoam-web', '--no-browser'] + (['--restart'] if restart else [])), \
                 patch('socket.socket') as sock, patch('urllib.request.urlopen') as urlopen, \
                 patch.object(server.os, 'kill') as kill, patch('subprocess.run') as run, patch('subprocess.check_output') as output, \
                 patch('time.sleep'), patch('uvicorn.run') as uvicorn, contextlib.redirect_stdout(io.StringIO()):
                sock.return_value.__enter__.return_value.connect_ex.side_effect = [0, 1]
                urlopen.return_value.status = 200
                output.return_value = '  TCP    127.0.0.1:8000  0.0.0.0:0 LISTENING 12345\n' if sys.platform == 'win32' else '12345\n'
                server.main()
                uvicorn.assert_called_once()
                if not restart:
                    kill.assert_not_called()
                    run.assert_not_called()
                    output.assert_not_called()
                elif sys.platform == 'win32':
                    run.assert_called_once()
                    self.assertIn('12345', run.call_args.args[0])
                else:
                    kill.assert_called_once_with(12345, 9)

    def test_resolved_preview_faces_follow_alternate_axes(self):
        cfg = {'flow': {'direction': '+x'}, 'outputs': {'drag_axis': '+x', 'downforce_axis': '-z'},
               'patches': {'ground': 'road', 'symmetry': 'center'},
               'domain_faces': {'-x': 'inlet', '+x': 'outlet', '-y': 'farField', '+y': 'center', '-z': 'farField', '+z': 'road'}}
        result = asyncio.run(server.api_geometry_domain_box(server.DomainBoxRequest(config=cfg, bounds={'min': [-1, -2, -3], 'max': [1, 2, 3]})))
        self.assertEqual(result['domain_faces']['+z'], 'ground')
        self.assertEqual(result['domain_faces']['+y'], 'symmetry')
