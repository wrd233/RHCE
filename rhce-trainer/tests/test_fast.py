import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from rhce_trainer import state
from rhce_trainer.grading import Grading,FAST_UNVERIFIED
from rhce_trainer.model import question,checkpoint,report
from rhce_trainer.transport import Result
from rhce_trainer.graders import MANAGED

class FastTests(unittest.TestCase):
    def grader(self,n):
        e=Mock();e.t.ws.return_value=Result(0,'','');e.t.node.return_value=Result(0,'','')
        g=Grading(e,question(n),fast=True)
        g.artifacts=Mock(return_value=[dict(exists=True,owner='devops')])
        g.observe=Mock()
        keys=('packages httpd_active httpd_enabled firewall_active firewall_enabled firewall_http firewall_http_permanent firewall_ports firewall_ports_permanent selinux chrony ntp memory bios cron').split()
        files=('/etc/issue /etc/myhosts /root/hwreport.txt /var/www/html/index.html /webdev /webdev/index.html /var/www/html/webdev /etc/chrony.conf /etc/selinux/config /etc/fstab').split()
        for h in g.q['nodes']:
            commands={k:dict(rc=0,out='') for k in keys}
            commands.update(lv=dict(out='{"report":[{"lv":[]}]}'),block=dict(out='{"blockdevices":[]}'))
            g.obs[h]=dict(commands=commands,files={p:{} for p in files},repos=[])
        return g

    def test_every_managed_fast_grader_avoids_mutations(self):
        for n in MANAGED:
            with self.subTest(n=n):
                g=self.grader(n)
                if n==17:
                    g.t.ws.return_value=Result(0,'{"users":[]}','')
                    g.t.dev.return_value=Result(0,'{"users":[]}','')
                    g.t.node.return_value=Result(0,'[]','')
                with patch('rhce_trainer.secrets.secrets',return_value=dict(developer='x',manager='y')):
                    r=g.grade()
                self.assertEqual(sum(c['weight'] for c in r['checkpoints']),100)
                self.assertEqual(r['mode'],'fast')
                for name in ('preflight','prepare','baseline','backup','save_scene','restore_scene','vm'):
                    getattr(g.e,name).assert_not_called()
                for call in g.t.mock_calls:
                    args=' '.join(str(a) for a in call.args)
                    for forbidden in ('ansible-playbook','ansible-galaxy','dnf ','cat >','systemctl start','mkdir','rht-vmctl'):
                        self.assertNotIn(forbidden,args)
                expected=FAST_UNVERIFIED.get(n,set())|{'execution'}
                self.assertEqual({c['id'] for c in r['checkpoints'] if c['status']=='UNVERIFIED'},expected)

    def test_fast_manual_state_can_pass_but_events_cannot(self):
        g=self.grader(13)
        for h,text in [('servera','Development'),('serverb','Test'),('serverc','Production'),('serverd','Production')]:
            g.obs[h]['files']['/etc/issue']={'text':text}
        r=g.grade()
        self.assertEqual((r['score'],r['maximum']),(75,75))
        self.assertEqual(r['counts'],dict(PASS=5,FAIL=0,UNVERIFIED=2))
        g.obs['servera']['files']['/etc/issue']['text']='typo';g.checks=[]
        r=g.grade();self.assertEqual((r['score'],r['maximum']),(55,75))
        self.assertEqual(r['counts']['FAIL'],1)

    def test_no_verifiable_items_has_no_percentage(self):
        r=report(question(1),[checkpoint('x','x',100,None,{},'events')],mode='fast')
        self.assertEqual(r['maximum'],0);self.assertIsNone(r['percentage'])
        self.assertIsNone(r['checkpoints'][0]['passed'])

    def test_fast_controller_config_never_loads_plugins(self):
        g=self.grader(1);g.t.ws.return_value=Result(0,'packages installed','')
        r=g.grade();self.assertEqual(r['maximum'],20)
        g.t.dev.assert_not_called();g.e.preflight.assert_not_called()

    def test_fast_roles_never_installs(self):
        g=self.grader(6);r=g.grade()
        self.assertEqual(r['maximum'],10);g.t.dev.assert_not_called()

    def test_fast_collections_and_vault_reuse_read_checks(self):
        samples={7:[dict(name='ansible.posix',passed=True),dict(name='community.general',passed=False)],
                 16:dict(encrypted=True,decrypts=True,variables=True,secret_file=False),
                 18:dict(encrypted=True,new_key=True,old_rejected=True,content_unchanged=True)}
        for n,data in samples.items():
            g=self.grader(n);g.t.dev.return_value=Result(0,json.dumps(data),'')
            with patch('rhce_trainer.secrets.secrets',return_value={}):r=g.grade()
            self.assertEqual(r['maximum'],100);g.e.preflight.assert_not_called()

    def test_cli_fast_does_not_take_remote_write_lock(self):
        from rhce_trainer.cli import main
        with tempfile.TemporaryDirectory() as d,patch.object(state,'STATE',Path(d)),patch('rhce_trainer.cli.Engine') as engine,patch('rhce_trainer.cli.Grading') as grading,patch('sys.argv',['rhce','grade','13','--fast','--json']):
            state.setup()
            grading.return_value.grade.return_value=report(question(13),[checkpoint('x','event',100,None,{},'event')],mode='fast')
            output=io.StringIO()
            with contextlib.redirect_stdout(output):main()
            self.assertEqual(json.loads(output.getvalue())['mode'],'fast')
            engine.return_value.t.lease.assert_not_called()
            self.assertTrue(grading.call_args.kwargs['fast'])

    def test_cli_full_still_uses_lease_and_full_grader(self):
        from rhce_trainer.cli import main
        with tempfile.TemporaryDirectory() as d,patch.object(state,'STATE',Path(d)),patch('rhce_trainer.cli.Engine') as engine,patch('rhce_trainer.cli.Grading') as grading,patch('sys.argv',['rhce','grade','13','--json']):
            state.setup();engine.return_value.t.lease.return_value=contextlib.nullcontext()
            grading.return_value.grade.return_value=report(question(13),[checkpoint('x','state',100,True,{},'state')])
            with contextlib.redirect_stdout(io.StringIO()):main()
            engine.return_value.t.lease.assert_called_once()
            self.assertFalse(grading.call_args.kwargs['fast'])
