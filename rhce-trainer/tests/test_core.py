import unittest,tempfile,json,subprocess,sys
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rhce_trainer.model import QUESTIONS,question,report,checkpoint
from rhce_trainer.engine import Engine
from rhce_trainer.graders import MANAGED,CONTROLLER,issue,apache,lvm
from rhce_trainer.transport import Transport
from rhce_trainer import state

class Tests(unittest.TestCase):
 def test_all_questions_have_implementation(self):
  self.assertEqual(set(range(1,20)),set(MANAGED)|set(CONTROLLER))
  self.assertEqual(len(QUESTIONS),19)
  for q in QUESTIONS:
   self.assertTrue(all(d<q['id'] for d in q['dependencies']))
   self.assertNotIn(q['id'],q['dependencies'])
 def test_unsafe_vm_never_reaches_transport(self):
  e=Engine();e.t=Mock()
  for vm in ['all','everything','classroom','utility','servera; reboot','../servera']:
   with self.assertRaises(ValueError):e.vm('restore',vm,'safe')
  e.t.run.assert_not_called()
 def test_label_injection_rejected(self):
  e=Engine();e.t=Mock()
  for label in ['x; reboot','../../foo','',None]:
   with self.assertRaises(ValueError):e.vm('restore','servera',label)
  e.t.run.assert_not_called()
 def test_report_weight_invariant(self):
  with self.assertRaises(ValueError):report(question(1),[checkpoint('a','a',90,True,{},'check')])
  r=report(question(1),[checkpoint('a','a',25,True,{},'check'),checkpoint('b','b',75,False,{},'check')])
  self.assertEqual(r['score'],25)
 def test_transport_never_has_password(self):
  t=Transport(dict(host='rhce.lab0.cn',port=9007,user='root'))
  self.assertIn('BatchMode=yes',t.base)
  self.assertNotIn('sshpass',' '.join(t.base))
 def test_snapshot_recovery_attempts_every_vm(self):
  with tempfile.TemporaryDirectory() as d,patch.object(state,'STATE',Path(d)):
   e=Engine();e.guard=Mock();e.vm=Mock(side_effect=[RuntimeError('one failed'),None]);
   j=dict(id='safe',nodes=['servera','serverb'],saved=['servera','serverb'],restored=[])
   with self.assertRaises(RuntimeError):e.restore_scene(j)
   self.assertEqual(e.vm.call_count,2)
   self.assertEqual(state.load('journals/safe.json')['phase'],'recovery_required')
 def test_cli_list_offline(self):
  p=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'rhce'),'list'],capture_output=True,text=True)
  self.assertEqual(p.returncode,0);self.assertEqual(len(p.stdout.splitlines()),19)
 def test_state_score_requires_replay(self):
  from rhce_trainer.grading import Grading
  g=Grading(Mock(),question(13));g.run_ok=False
  g.state_check('x','manual state',100,True,{'state':'correct'},'check')
  self.assertFalse(g.checks[0]['passed'])
 def test_escaping_does_not_execute_shell(self):
  t=Transport(dict(host='example',port=22,user='root'))
  t.ws=Mock()
  t.dev('python3 -c \'print("a\\nb")\'')
  self.assertIn('sudo -u devops -H bash -c',t.ws.call_args[0][0])

if __name__=='__main__':unittest.main()
