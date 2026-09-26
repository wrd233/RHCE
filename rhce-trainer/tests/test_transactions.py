import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rhce_trainer.engine import Engine
from rhce_trainer.grading import Grading
from rhce_trainer.model import question
from rhce_trainer import state

class Transactions(unittest.TestCase):
    def test_failed_preflight_prevents_any_mutation(self):
        e=Engine();e.preflight=Mock(side_effect=RuntimeError('offline'))
        e.backup=Mock();e.save_scene=Mock();e.clear_artifacts=Mock()
        with self.assertRaises(RuntimeError):e.reset(question(8))
        e.backup.assert_not_called();e.save_scene.assert_not_called();e.clear_artifacts.assert_not_called()

    def test_controller_only_reset_failure_restores_answers(self):
        with tempfile.TemporaryDirectory() as d,patch.object(state,'STATE',Path(d)):
            e=Engine();e.preflight=Mock();e.backup=Mock(return_value='saved.tar.gz')
            e.clear_artifacts=Mock();e.prepare=Mock(side_effect=RuntimeError('dependency failed'))
            e.restore_scene=Mock();e.restore_answers=Mock()
            with self.assertRaisesRegex(RuntimeError,'dependency failed'):e.reset(question(16))
            e.restore_answers.assert_called_once_with('saved.tar.gz')
            saved=list((Path(d)/'journals').glob('*.json'))
            self.assertEqual(len(saved),1)
            j=json.loads(saved[0].read_text())
            self.assertEqual(j['phase'],'recovered');self.assertTrue(j['controller_restored'])

    def test_rollback_failure_is_recoverable(self):
        with tempfile.TemporaryDirectory() as d,patch.object(state,'STATE',Path(d)):
            e=Engine();e.preflight=Mock();e.backup=Mock(return_value='archive')
            e.save_scene=Mock(return_value={'id':'sample','nodes':['servera'],'saved':['servera']})
            e.baseline=Mock();e.clear_artifacts=Mock();e.prepare=Mock(side_effect=RuntimeError('prepare'))
            e.restore_scene=Mock(side_effect=RuntimeError('VM recovery'));e.restore_answers=Mock()
            with self.assertRaisesRegex(RuntimeError,'恢复未完成'):e.reset(question(11))
            e.restore_answers.assert_called_once_with('archive')
            self.assertEqual(state.load('journals/sample.json')['phase'],'recovery_required')

    def test_archive_traversal_is_rejected_before_remote_writes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.tar.gz'
            with tarfile.open(p,'w:gz') as tar:
                member=tarfile.TarInfo('../outside');member.size=3;tar.addfile(member,io.BytesIO(b'bad'))
            e=Engine();e.t=Mock()
            with self.assertRaisesRegex(RuntimeError,'越界路径'):e.restore_answers(str(p))
            e.t.ws.assert_not_called()

    def test_archive_is_staged_before_answer_directory_is_moved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'good.tar.gz'
            with tarfile.open(p,'w:gz') as tar:
                member=tarfile.TarInfo('ansible');member.type=tarfile.DIRTYPE;tar.addfile(member)
            e=Engine();e.t=Mock();e.restore_answers(str(p))
            calls=e.t.ws.call_args_list
            self.assertIn('tar -xzf',calls[0].args[0]);self.assertNotIn('mv ',calls[0].args[0])
            self.assertIn('test -d',calls[1].args[0]);self.assertIn('mv ',calls[2].args[0])

    def test_partial_credit_requires_fresh_replay(self):
        g=Grading(Mock(),question(8));g.events=[dict(host='serverc',status='ok')]
        g.state_check('a','state',10,True,'correct','read')
        self.assertFalse(g.checks[-1]['passed'])
        g.replay_verified=True
        g.state_check('b','state',10,True,'correct','read')
        self.assertTrue(g.checks[-1]['passed'])

    def test_empty_events_never_give_partial_credit(self):
        g=Grading(Mock(),question(8));g.replay_verified=True
        g.state_check('a','state',10,True,'baseline','read')
        self.assertFalse(g.checks[-1]['passed'])

    def test_mux_refusal_retries_only_before_execution(self):
        from rhce_trainer.transport import Transport
        t=Transport(dict(host='example',port=22,user='root'))
        refused=Mock(returncode=255,stdout=b'',stderr=b'mux_client_request_session: session request failed: Session open refused by peer')
        success=Mock(returncode=0,stdout=b'ok',stderr=b'')
        with patch('subprocess.run',side_effect=[refused,success]) as run,patch('time.sleep'):
            self.assertEqual(t.run('one command').out,'ok');self.assertEqual(run.call_count,2)
        uncertain=Mock(returncode=255,stdout=b'',stderr=b'Connection reset by peer')
        with patch('subprocess.run',return_value=uncertain) as run:
            self.assertEqual(t.run('one command').rc,255);self.assertEqual(run.call_count,1)

    def test_internal_ssh_uses_fixed_lab_address(self):
        from rhce_trainer.transport import Transport
        t=Transport(dict(host='example',port=22,user='root'));t.ws=Mock()
        t.node('servera','hostname')
        self.assertIn('root@172.25.250.10',t.ws.call_args.args[0])

    def test_vm_readiness_requires_completed_boot(self):
        from rhce_trainer.transport import Transport,Result
        t=Transport(dict(host='example',port=22,user='root'));t.node=Mock(return_value=Result(0,'',''))
        t.wait('bastion')
        command=t.node.call_args.args[1]
        self.assertIn('multi-user.target',command);self.assertIn('bastion.lab.example.com',command)

if __name__=='__main__':unittest.main()
