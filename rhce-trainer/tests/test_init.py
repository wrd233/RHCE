import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from rhce_trainer import state
from rhce_trainer.engine import Engine
from rhce_trainer.transport import NODES,Result
from rhce_trainer.remote import bootstrap

class InitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        patcher=patch.object(state,'STATE',Path(self.temp.name));patcher.start();self.addCleanup(patcher.stop)
        self.e=Engine();self.e.t=Mock();self.e.identity=Mock(return_value={'host':'expected'})
        self.e.vm=Mock();self.e.backup=Mock();self.e.guard=Mock();self.e.snapshot_disks=Mock()
        self.e.t.run.return_value=Result(0,'','');self.e.t.node.return_value=Result(0,'','')
        self.e.t.ws.return_value=Result(0,'ssh-rsa public','')

    def test_existing_baseline_requires_explicit_prepare(self):
        state.save('baseline.json',dict(label='old'))
        with self.assertRaisesRegex(RuntimeError,'--prepare'):self.e.init()
        self.e.t.ws.assert_not_called();self.e.vm.assert_not_called()

    def test_prepare_preserves_baseline_binding_answers_and_current(self):
        original={'baseline.json':dict(label='old'),'binding.json':dict(host='bound'),'current.json':dict(question=8)}
        for path,data in original.items():state.save(path,data)
        for _ in range(2):
            with contextlib.redirect_stdout(io.StringIO()):self.e.init(prepare_only=True)
        for path,data in original.items():self.assertEqual(state.load(path),data)
        self.e.vm.assert_not_called();self.e.backup.assert_not_called()
        self.assertEqual(self.e.snapshot_disks.call_count,10)
        for call in self.e.t.mock_calls:
            self.assertNotIn('/home/devops/ansible',' '.join(str(a) for a in call.args))

    def test_prepare_failure_does_not_create_baseline(self):
        self.e.t.ws.return_value=Result(1,'','key missing')
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'公共准备未完成'):
            self.e.init()
        self.assertIsNone(state.load('baseline.json'))
        self.assertEqual([c.args[0] for c in self.e.vm.call_args_list],['reset']*5)
        report=json.loads(next((Path(self.temp.name)/'reports').glob('*-init.json')).read_text())
        self.assertFalse(report['complete'])
        self.assertTrue(any(row['status']=='SKIP' for row in report['items']))

    def test_successful_prepare_precedes_baseline_save(self):
        order=[]
        self.e.bootstrap_nodes=Mock(side_effect=lambda:order.append('prepare'))
        self.e.vm.side_effect=lambda action,*args:order.append(action)
        with contextlib.redirect_stdout(io.StringIO()):self.e.init()
        self.assertEqual(order,['reset']*5+['prepare']+['save']*5)
        self.assertTrue(state.load('baseline.json')['label'].startswith('rhce-baseline-'))

    def test_existing_save_rejected_before_binding_or_reset(self):
        self.e.t.run.return_value=Result(0,'existing-save','')
        with self.assertRaises(RuntimeError):self.e.init()
        self.e.vm.assert_not_called();self.assertIsNone(state.load('binding.json'))

    def test_all_preparation_steps_report_and_verify_five_logins(self):
        with contextlib.redirect_stdout(io.StringIO()):self.e.bootstrap_nodes()
        report=json.loads(next((Path(self.temp.name)/'reports').glob('*-init.json')).read_text())
        self.assertTrue(report['complete']);self.assertEqual(len(report['items']),18)
        commands=[call.args[0] for call in self.e.t.ws.call_args_list]
        for h in NODES:self.assertTrue(any('devops@'+h in cmd and 'sudo -n true' in cmd for cmd in commands))

    def test_backups_keep_same_named_files_and_write_is_idempotent(self):
        base=Path(self.temp.name);target=base/'sample.repo';archive=base/'archive'
        account=Mock(pw_uid=1,pw_gid=1)
        with patch.object(bootstrap,'BACKUP',archive),patch.object(bootstrap.pwd,'getpwnam',return_value=account),patch.object(bootstrap.os,'chown'):
            target.write_text('original')
            bootstrap.write(target,'second');bootstrap.write(target,'third');bootstrap.write(target,'third')
        copies=list(archive.rglob('sample.repo'))
        self.assertEqual(sorted(p.read_text() for p in copies),['original','second'])
        self.assertEqual(target.read_text(),'third')
        self.assertEqual(target.stat().st_mode&0o777,0o600)

    def test_symlink_refused_before_overwrite(self):
        base=Path(self.temp.name);target=base/'original';target.write_text('safe')
        link=base/'link';link.symlink_to(target)
        with patch.object(bootstrap.pwd,'getpwnam',return_value=Mock(pw_uid=1,pw_gid=1)),self.assertRaises(RuntimeError):bootstrap.write(link,'changed')
        self.assertEqual(target.read_text(),'safe')

    def test_podman_probes_v2_then_legacy_and_checks_effective(self):
        registry='utility.lab.example.com'
        valid=json.dumps(dict(registries={'search':[registry],registry:{'Insecure':True}}))
        for legacy in (False,True):
            with self.subTest(legacy=legacy):
                directory=Path(self.temp.name)/str(legacy)/'containers'
                effects=[RuntimeError('v2 unsupported'),valid,valid] if legacy else [valid,valid]
                with patch.object(bootstrap,'dev',side_effect=effects) as dev,patch.object(bootstrap,'write') as write,patch.object(bootstrap.pwd,'getpwnam',return_value=Mock(pw_uid=1,pw_gid=1)),patch.object(bootstrap.os,'chown'),contextlib.redirect_stdout(io.StringIO()):
                    bootstrap.configure_podman(directory)
                self.assertEqual(dev.call_count,3 if legacy else 2)
                self.assertIn('[registries.search]' if legacy else 'unqualified-search-registries',write.call_args.args[1])
                self.assertEqual(list(directory.iterdir()),[])

    def test_podman_unverified_candidates_never_replace_config(self):
        directory=Path(self.temp.name)/'config'/'containers'
        with patch.object(bootstrap,'dev',return_value='{"registries":{"search":[]}}'),patch.object(bootstrap,'write') as write,patch.object(bootstrap.pwd,'getpwnam',return_value=Mock(pw_uid=1,pw_gid=1)),patch.object(bootstrap.os,'chown'),self.assertRaisesRegex(RuntimeError,'不接受'):
            bootstrap.configure_podman(directory)
        write.assert_not_called()

    def test_legacy_podman_info_requires_both_registry_flags(self):
        registry='utility.lab.example.com'
        self.assertTrue(bootstrap.registry_ready({'search':[registry],'insecure':[registry]},registry))
        self.assertFalse(bootstrap.registry_ready({'search':[registry]},registry))

    def test_prepare_without_baseline_rejects_changed_binding(self):
        state.save('binding.json',dict(host='other'))
        with self.assertRaisesRegex(RuntimeError,'不一致'):self.e.init(prepare_only=True)
        self.e.t.ws.assert_not_called();self.e.vm.assert_not_called()

    def test_prepare_invalid_baseline_disk_prevents_all_writes(self):
        state.save('baseline.json',dict(label='old'))
        self.e.snapshot_disks.side_effect=RuntimeError('missing vdb')
        with self.assertRaisesRegex(RuntimeError,'missing vdb'):self.e.init(prepare_only=True)
        self.e.t.ws.assert_not_called();self.e.t.node.assert_not_called();self.e.vm.assert_not_called()
        self.assertEqual(state.load('baseline.json'),dict(label='old'))

    def test_baseline_save_failure_never_publishes_baseline(self):
        self.e.bootstrap_nodes=Mock()
        self.e.vm.side_effect=lambda action,*args: (_ for _ in ()).throw(RuntimeError('save failed')) if action=='save' else None
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'save failed'):self.e.init()
        self.assertIsNone(state.load('baseline.json'))
