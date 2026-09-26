import unittest,tempfile,json,subprocess,sys
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rhce_trainer.model import QUESTIONS,question,report,checkpoint
from rhce_trainer.engine import Engine
from rhce_trainer.graders import MANAGED,CONTROLLER,issue,apache,lvm
from rhce_trainer.transport import Transport,Result
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
 def test_controller_is_never_reset(self):
  e=Engine();e.t=Mock()
  for action in ('reset','save','restore','start'):
   with self.assertRaises(ValueError):e.vm(action,'workstation','safe')
  e.t.run.assert_not_called()
 def test_adopt_missing_disk_does_not_bind(self):
  with tempfile.TemporaryDirectory() as d,patch.object(state,'STATE',Path(d)):
   e=Engine();e.identity=Mock(return_value={'host':'expected'});e.snapshot_disks=Mock(side_effect=RuntimeError('missing vdb'))
   with self.assertRaises(RuntimeError):e.adopt_baseline('rhce-baseline-example')
   self.assertIsNone(state.load('baseline.json'));self.assertIsNone(state.load('binding.json'))
 def test_restore_missing_disk_never_calls_vmctl(self):
  e=Engine();e.t=Mock();e.snapshot_disks=Mock(side_effect=RuntimeError('missing disk'))
  with self.assertRaises(RuntimeError):e.vm('restore','servera','safe')
  e.t.run.assert_not_called()
 def test_save_copy_failure_is_not_success(self):
  e=Engine();e.t=Mock();e.snapshot_disks=Mock(return_value=['/var/lib/libvirt/images/rh294-servera-vda.ovl'])
  e.t.run.side_effect=[Result(0,'Saving',''),Result(0,'shut off\n',''),Result(1,'','copy differs')]
  with self.assertRaises(RuntimeError):e.vm('save','servera','safe')
  e.t.wait.assert_not_called()
 def test_snapshot_requires_all_attached_disks(self):
  e=Engine();e.t=Mock()
  e.t.run.side_effect=[Result(0,'file disk vda /var/lib/libvirt/images/rh294-servera-vda.ovl\nfile disk vdb /var/lib/libvirt/images/rh294-servera-vdb.ovl',''),Result(0,'',''),Result(1,'','missing')]
  with self.assertRaises(RuntimeError):e.snapshot_disks('servera','safe')
  self.assertIn('vdb.ovl-safe',e.t.run.call_args[0][0])
 def test_reset_failure_restores_scene(self):
  with tempfile.TemporaryDirectory() as d,patch.object(state,'STATE',Path(d)):
   e=Engine();e.backup=Mock(return_value='archive');j={'id':'safe'}
   e.save_scene=Mock(return_value=j);e.baseline=Mock();e.clear_artifacts=Mock();e.prepare=Mock(side_effect=RuntimeError('prepare failed'));e.restore_scene=Mock()
   with self.assertRaises(RuntimeError):e.reset(question(13))
   e.restore_scene.assert_called_once_with(j)
   self.assertIsNone(state.load('current.json'))
 def test_restore_lab_failure_rolls_back(self):
  e=Engine();j={'id':'safe'};e.save_scene=Mock(return_value=j);e.baseline=Mock(side_effect=RuntimeError('restore failed'));e.restore_scene=Mock()
  with self.assertRaises(RuntimeError):e.restore_lab()
  e.restore_scene.assert_called_once_with(j)
 def test_template_source_and_role_must_match(self):
  from rhce_trainer.grading import Grading
  g=Grading(Mock(),question(8));g.events=[dict(status='ok',action='ansible.builtin.template',role='not_apache',host='serverc',dest='/var/www/html/index.html',src='other.j2')]
  self.assertFalse(g.has_event('template',role='apache',src='index.html.j2'))
  g.events[0].update(role='apache',src='/absolute/path/index.html.j2')
  self.assertTrue(g.has_event('template',role='apache',src='index.html.j2'))
 def test_lost_remote_lock_prevents_commands(self):
  t=Transport(dict(host='example',port=22,user='root'));t._lease=Mock();t._lease.poll.return_value=255
  with patch('subprocess.run') as run:
   with self.assertRaises(RuntimeError):t.run('hostname')
   run.assert_not_called()
 def test_lock_lifetime_without_remote_access(self):
  t=Transport(dict(host='example',port=22,user='root'))
  t.base=[sys.executable,'-u','-c',"import sys; print('RHCE_LOCKED'); sys.stdin.read()"]
  with t.lease():
   proc=t._lease
   self.assertIsNone(proc.poll())
  self.assertIsNone(t._lease);self.assertEqual(proc.returncode,0)
 def test_lock_rejection_never_enters_operation(self):
  t=Transport(dict(host='example',port=22,user='root'))
  t.base=[sys.executable,'-c','raise SystemExit(1)']
  with self.assertRaises(RuntimeError):
   with t.lease():self.fail('operation must not start')
 def test_cron_equivalent_schedules(self):
  from rhce_trainer.graders import cron_minutes
  expected=set(range(0,60,2))
  for expression in ('*/2','0-59/2','0-58/2',','.join(map(str,expected))):
   self.assertEqual(cron_minutes(expression),expected)
  for expression in ('*/0','60','-1','0-60/2','*/3','nonsense'):
   self.assertNotEqual(cron_minutes(expression),expected)
 def test_plan_exposes_actual_grade_scope(self):
  from rhce_trainer.model import plan,dependency_order
  p=plan(12)
  self.assertEqual(p['reset_vm_scope'],['servera'])
  self.assertEqual(len(p['grade_vm_scope']),5)
  self.assertEqual(dependency_order(9),[1,2,3,6,7,8])
 def test_config_path_prefix_does_not_pass(self):
  from rhce_trainer.graders import configured_paths
  text="DEFAULT_HOST_LIST(example) = ['/home/devops/ansible/inventory-backup']"
  self.assertNotIn('/home/devops/ansible/inventory',configured_paths(text,'DEFAULT_HOST_LIST'))
  self.assertIn('/home/devops/ansible/inventory-backup',configured_paths(text,'DEFAULT_HOST_LIST'))
 def test_collection_reset_preserves_unrelated_collections(self):
  paths=question(7)['artifacts']
  self.assertNotIn('mycollections',paths)
  self.assertEqual(len(paths),2)
 def test_upload_assigns_only_new_parent_directories(self):
  import shlex,io
  t=Transport(dict(host='example',port=22,user='root'));t.ws=Mock()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);target=root/'apache'/'tasks'/'main.yml'
   t.put(str(target),'[]',owner='devops')
   args=t.ws.call_args[0];script=shlex.split(args[0])[2]
   with patch('sys.stdin',io.StringIO(args[1].decode())),patch('pwd.getpwnam',return_value=Mock(pw_uid=1234,pw_gid=1234)),patch('os.chown') as chown:
    exec(script,{})
   assigned={call.args[0] for call in chown.call_args_list}
   self.assertEqual(assigned,{root/'apache',root/'apache'/'tasks',target})
   self.assertEqual(target.read_text(),'[]')
 def test_issue_typo_fails_only_affected_checkpoint(self):
  from rhce_trainer.grading import Grading
  g=Grading(Mock(),question(13));g.run_ok=True
  g.obs={h:{'files':{'/etc/issue':{'text':t+'\n'}}} for h,t in [('servera','Devlopment'),('serverb','Test'),('serverc','Production'),('serverd','Production')]}
  g.events=[{'host':h} for h in ('servera','serverb','serverc','serverd','bastion')]
  issue(g)
  self.assertFalse(g.checks[0]['passed']);self.assertTrue(all(c['passed'] for c in g.checks[1:]))
  self.assertEqual(sum(c['weight'] for c in g.checks),70)

if __name__=='__main__':unittest.main()
