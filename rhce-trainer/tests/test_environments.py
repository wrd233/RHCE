import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rhce_trainer import state
from rhce_trainer.engine import Engine
from rhce_trainer.model import question
from rhce_trainer.prerequisites import Prerequisites,reset_nodes
from rhce_trainer.transport import Result

CLI=Path(__file__).resolve().parents[1]/'rhce'

class Environments(unittest.TestCase):
    def test_no_implicit_ce_and_per_command_override(self):
        with tempfile.TemporaryDirectory() as d:
            env=dict(os.environ,RHCE_STATE_DIR=d)
            missing=subprocess.run([sys.executable,str(CLI),'status'],env=env,capture_output=True,text=True)
            self.assertEqual(missing.returncode,2)
            self.assertIn('尚未选择 CE 环境',missing.stderr)
            selected=subprocess.run([sys.executable,str(CLI),'--ce','CE-02','status'],env=env,capture_output=True,text=True,check=True)
            status=json.loads(selected.stdout)
            self.assertEqual((status['environment'],status['port']),('CE-02',9006))
            self.assertFalse((Path(d)/'selected-ce.json').exists())

    def test_selection_and_legacy_ce03_copy(self):
        with tempfile.TemporaryDirectory() as d,patch.object(state,'ROOT',Path(d)),patch.object(state,'STATE',Path(d)),patch.object(state,'ACTIVE_CE',None):
            state.save('binding.json',{'host':'legacy'})
            state.save('backups/old.json',{'saved':True})
            state.choose_ce('CE-03')
            self.assertEqual(state.selected_ce(),'CE-03')
            self.assertEqual(state.load('binding.json'),{'host':'legacy'})
            self.assertTrue((Path(d)/'binding.json').exists())
            self.assertTrue((Path(d)/'environments/ce-03/backups/old.json').exists())
            self.assertEqual(Engine().config['port'],9007)
            state.activate_ce('CE-01')
            self.assertIsNone(state.load('binding.json'))
            self.assertEqual(Engine().config['port'],9005)

    def test_dependency_scope_and_order(self):
        self.assertEqual(reset_nodes(question(11)),['servera','serverb','serverc','serverd','bastion'])
        e=Mock();p=Prerequisites(e)
        seen=[]
        p.check=Mock(side_effect=lambda n: seen.count(n)>0)
        p.complete=Mock(side_effect=lambda n: seen.append(n))
        p.ensure(question(9))
        self.assertEqual(seen,[1,2,3,6,7,8])
        self.assertEqual([c.args[0] for c in p.complete.call_args_list],seen)

    def test_packages_prerequisite_uses_supported_group_query(self):
        e=Mock();p=Prerequisites(e);p._file=Mock(return_value=True)
        def node(host,command,**kwargs):
            if command.startswith('rpm -q '):return Result(0,'php\nmariadb','')
            if 'group list' in command:
                self.assertEqual(command,'LC_ALL=C dnf -q group list --installed')
                return Result(0,'Installed Groups:\n   Development Tools\n','')
            if 'check-update' in command:return Result(0,'','')
            self.fail(command)
        e.t.node.side_effect=node
        self.assertTrue(p.check(3))

    def test_reset_prerequisite_failure_restores_every_saved_vm_and_answers(self):
        from rhce_trainer.transport import NODES
        with tempfile.TemporaryDirectory() as d,patch.object(state,'STATE',Path(d)):
            e=Engine();e.preflight=Mock();e.backup=Mock(return_value='answers.tar.gz')
            journal=dict(id='sample',nodes=list(NODES),saved=list(NODES),restored=[])
            e.save_scene=Mock(return_value=journal);e.baseline=Mock()
            e.restore_scene=Mock();e.restore_answers=Mock();e.clear_artifacts=Mock()
            with patch('rhce_trainer.prerequisites.Prerequisites.ensure',side_effect=RuntimeError('prerequisite failed')):
                with self.assertRaisesRegex(RuntimeError,'prerequisite failed'):e.reset(question(11))
            self.assertEqual(e.save_scene.call_args.args[0],list(NODES))
            self.assertEqual(e.baseline.call_args.args[0],list(NODES))
            e.restore_scene.assert_called_once_with(journal)
            e.restore_answers.assert_called_once_with('answers.tar.gz')
            e.clear_artifacts.assert_not_called()

if __name__=='__main__':unittest.main()
