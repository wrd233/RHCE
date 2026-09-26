import json,shlex,subprocess,time,re,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from .model import checkpoint,report,ROOT
from .engine import BASE
from .transport import NODES
from . import state

class Grading:
    def __init__(self,e,q,profile='pdf'):
        self.e=e;self.t=e.t;self.q=q;self.profile=profile;self.checks=[];self.events=[];self.obs={};self.run_ok=False;self.run_result=None;self.run_directory=None
    def add(self,id,desc,weight,ok,evidence,check):
        self.checks.append(checkpoint(id,desc,weight,ok,evidence,check))
    def command(self,cmd):return self.t.dev(cmd)
    def has_event(self,action=None,role=None,host=None,dest=None,src=None):
        return any(x['status']=='ok' and (action is None or x['action'].split('.')[-1]==action) and (role is None or x['role'].split('.')[-1]==role) and (host is None or x['host']==host) and (dest is None or x.get('dest')==dest) and (src is None or Path(x.get('src','')).name==src) for x in self.events)
    def message(self,host,msg):return any(x['host']==host and x['status']=='ok' and msg in x.get('messages',[]) for x in self.events)
    def artifacts(self):
        code='''import json,os,pwd,pathlib,sys
out=[]
for rel in json.loads(sys.argv[1]):
 p=pathlib.Path('/home/devops/ansible')/rel
 try:
  s=p.stat(); out.append(dict(path=rel,exists=True,owner=pwd.getpwuid(s.st_uid).pw_name,size=s.st_size))
 except FileNotFoundError:out.append(dict(path=rel,exists=False))
print(json.dumps(out))'''
        return json.loads(self.t.ws('python3 -c '+shlex.quote(code)+' '+shlex.quote(json.dumps(self.q['artifacts']))).require())
    def safety_inventory(self):
        inv=json.loads(self.command('ansible-inventory --list').require())
        hv=inv.get('_meta',{}).get('hostvars',{})
        allowed={h:'172.25.250.'+str(i) for h,i in zip(NODES,[10,11,12,13,254])}
        allhosts=set(hv)
        for group,v in inv.items():
            if group!='_meta':allhosts.update(v.get('hosts',[]))
        if not allhosts or not allhosts<=set(NODES):raise RuntimeError('清单含缺失/未授权主机：'+str(allhosts))
        for h,v in hv.items():
            if v.get('ansible_host',h) not in (h,h+'.lab.example.com',allowed[h]):raise RuntimeError('清单将主机映射到范围外地址：'+h)
            if str(v.get('ansible_port',22))!='22' or v.get('ansible_connection','ssh') not in ('ssh','smart'):raise RuntimeError('拒绝非实验 SSH 连接')
            if any(v.get(k) for k in ('ansible_ssh_common_args','ansible_ssh_extra_args','ansible_ssh_executable')):raise RuntimeError('评分不接受清单自定义 SSH 代理或可执行程序')
        return inv
    def execute(self,journal=None):
        self.safety_inventory()
        runid=state.stamp();directory='/tmp/rhce-grade-'+runid;self.run_directory=directory
        if journal is not None:
            journal['runner']=directory;state.save('journals/'+journal['id']+'.json',journal)
        self.t.ws('install -d -o devops -g devops -m 700 '+directory).require()
        self.t.put(directory+'/rhce_events.py',(ROOT/'remote/events.py').read_text())
        self.t.put(directory+'/runner.py',(ROOT/'remote/runner.py').read_text())
        eventfile=directory+'/events.jsonl'
        self.t.put(eventfile,'')
        vault=' --vault-password-file secret.txt' if self.q['id']==17 else ''
        env='ANSIBLE_CALLBACK_PLUGINS='+directory+' ANSIBLE_CALLBACKS_ENABLED=rhce_events RHCE_EVENT_FILE='+eventfile+' ANSIBLE_NOCOLOR=1'
        args=['ansible-playbook',self.q['playbook']]
        if self.q['id']==17:args+=['--vault-password-file','secret.txt']
        args+=['--limit',','.join(self.q.get('execution_nodes',self.q['nodes']))]
        cmd=env+' python3 '+directory+'/runner.py '+shlex.quote(json.dumps(args))+' '+directory
        self.run_result=self.command(cmd);self.run_ok=self.run_result.rc==0
        raw=self.t.ws('cat '+eventfile).require()
        self.events=[json.loads(l) for l in raw.splitlines() if l.strip()]
        # Store only safe event metadata, never unfiltered student stdout or vault values.
        return {'returncode':self.run_result.rc,'events':self.events,'stdout_saved':False}
    def stop_runner(self):
        if not self.run_directory:return
        code="import pathlib,json,os,signal,time,sys\np=pathlib.Path(sys.argv[1])/'process.json'\nif p.exists():\n d=json.loads(p.read_text());proc=pathlib.Path('/proc/'+str(d['pid'])+'/stat')\n if proc.exists() and proc.read_text().split()[21]==d['starttime']:\n  os.killpg(d['pid'],signal.SIGTERM);time.sleep(2)\n  if proc.exists() and proc.read_text().split()[21]==d['starttime']:os.killpg(d['pid'],signal.SIGKILL)\n p.unlink(missing_ok=True)\n"
        self.t.ws('python3 -c '+shlex.quote(code)+' '+shlex.quote(self.run_directory)).require()
    def observe(self):
        script=(ROOT/'remote/inspect.py').read_bytes()
        def one(h):return h,json.loads(self.t.node(h,'python3 -',script,timeout=240).require())
        with ThreadPoolExecutor(max_workers=5) as pool:self.obs=dict(pool.map(one,self.q['nodes']))
    def out(self,h,key):return self.obs[h]['commands'][key]['out']
    def file(self,h,p):return self.obs[h]['files'][p]
    def state_check(self,id,desc,weight,predicate,evidence,check):
        self.add(id,desc,weight,self.run_ok and predicate,evidence,check)
    def grade(self):
        artifacts=self.artifacts()
        self.add('artifacts','题目要求的文件/目录存在且属于 devops',10,all(x.get('exists') and x.get('owner')=='devops' for x in artifacts),artifacts,'stat required artifacts')
        if not self.q['playbook']:
            from .graders import controller
            controller(self)
            return report(self.q,self.checks,mode='controller-verification',profile=self.profile)
        if not all(x.get('exists') for x in artifacts):
            self.add('execution','从基线执行提交文件',20,False,'缺少提交文件，未重建虚拟机','ansible-playbook')
            self.add('unexecuted','最终状态与行为检查',70,False,'因文件缺失未执行，手工状态不计分','fresh replay required')
            return report(self.q,self.checks,mode='missing-artifacts',profile=self.profile)
        # Validate the inventory before any VM mutation.
        self.safety_inventory()
        j=self.e.save_scene(self.q.get('execution_nodes',self.q['nodes']),'grade',self.q['id'])
        try:
            j['phase']='grading';state.save('journals/'+j['id']+'.json',j)
            self.e.baseline(self.q.get('execution_nodes',self.q['nodes']));self.e.prepare(self.q,grading=True)
            execution=self.execute(j)
            self.add('execution','以 devops 从正确基线执行成功',20,self.run_ok,{'returncode':self.run_result.rc,'failed_tasks':[x for x in self.events if x['status'] in ('failed','unreachable')]},'ansible-playbook '+self.q['playbook'])
            self.observe()
            from .graders import managed
            managed(self)
            result=report(self.q,self.checks,mode='fresh-replay',profile=self.profile,journal=j['id'],execution=execution)
        finally:
            try:self.stop_runner()
            except BaseException:
                j['phase']='recovery_required';state.save('journals/'+j['id']+'.json',j)
                raise RuntimeError('无法确认学生进程已停止，暂不覆盖 VM；运行 rhce recover '+j['id'])
            self.e.restore_scene(j)
        result['scene_restored']=True
        return result
