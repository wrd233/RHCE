import json,shlex,subprocess,time,re,hashlib,tarfile,io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from . import state
from .transport import Transport,NODES,VMS,INNER
from .model import question
from .archives import validate_answers

BASE='/home/devops/ansible'
INVENTORY='[dev]\nservera\n[test]\nserverb\n[prod]\nserverc\nserverd\n[balancers]\nbastion\n[webservers:children]\nprod\n'
CFG=f'''[defaults]
inventory = {BASE}/inventory
remote_user = devops
roles_path = {BASE}/roles:/usr/share/ansible/roles
collections_paths = {BASE}/mycollections:/usr/share/ansible/collections
host_key_checking = False
[privilege_escalation]
become = True
become_method = sudo
become_user = root
become_ask_pass = False
'''

class Engine:
    def __init__(self):
        state.setup()
        pdf=next(Path(__file__).resolve().parents[2].glob('RHCE9.0*.pdf'),None)
        self.config=dict(host='rhce.lab0.cn',port=0,user='root',pdf=str(pdf) if pdf else '')
        self.config.update(state.load('connection.json',{}))
        ce=state.active_ce()
        if ce:
            # A copied legacy connection file must never redirect another CE.
            self.config.update(host='rhce.lab0.cn',port=state.CE_PORTS[ce],user='root')
        self.t=Transport(self.config)
    def identity(self):
        host=self.t.run('hostname').require().strip()
        if host!='foundation0.ilt.example.com':raise RuntimeError('入口主机身份不符：'+host)
        rht=self.t.run('cat /etc/rht').require()
        if 'RHT_COURSE=rh294' not in rht:raise RuntimeError('不是 RH294 环境')
        ids={h:self.t.run('virsh domuuid '+h).require().strip() for h in VMS}
        if any(not re.fullmatch('[0-9a-f-]{36}',v) for v in ids.values()):raise RuntimeError('VM UUID 异常')
        script=self.t.run('sha256sum /usr/local/bin/rht-vmctl').require().split()[0]
        return dict(host=host,uuids=ids,vmctl_sha256=script)
    def guard(self,nodes,require_space=True):
        if not nodes or len(set(nodes))!=len(nodes) or not set(nodes)<=set(VMS):raise ValueError('拒绝未知或宽泛 VM 范围')
        binding=state.load('binding.json')
        if not binding:raise RuntimeError('先运行 rhce init 建立身份绑定和基线')
        current=self.identity()
        if current!=binding:raise RuntimeError('入口/VM UUID/官方管理脚本变化；停止，不执行破坏操作')
        if require_space:
            free=int(self.t.run("df -B1 --output=avail /var/lib/libvirt/images | tail -1").require().strip())
            if free<8*1024**3:raise RuntimeError('宿主机可用空间不足 8 GiB，停止创建保存点')
    def snapshot_disks(self,h,label):
        if h not in NODES or not re.fullmatch(r'[A-Za-z0-9-]{1,80}',label or ''):
            raise ValueError('保存点范围或名称无效')
        rows=self.t.run('virsh domblklist '+h+' --details').require().splitlines()
        paths=[]
        for row in rows:
            fields=row.split()
            if len(fields)==4 and fields[1]=='disk':
                path=fields[3]
                if not re.fullmatch('/var/lib/libvirt/images/rh294-'+h+r'-vd[a-z]\.ovl',path):
                    raise RuntimeError('VM 磁盘路径不符合实验范围：'+path)
                paths.append(path)
        if not paths:raise RuntimeError('未找到 VM 磁盘：'+h)
        for path in paths:
            self.t.run('test -s '+shlex.quote(path+'-'+label)).require()
        return paths
    def adopt_baseline(self,label,replace=False):
        previous=state.load('baseline.json')
        if previous and not replace:raise RuntimeError('已有本地基线；重新核对环境后可显式使用 --replace，旧记录将保留')
        if not re.fullmatch(r'rhce-baseline-[A-Za-z0-9-]+',label):raise ValueError('只接受明确的 rhce-baseline 保存点名称')
        binding=self.identity()
        disks={h:self.snapshot_disks(h,label) for h in NODES}
        if previous:
            state.save('previous-binding-'+state.stamp()+'.json',dict(baseline=previous,binding=state.load('binding.json'),current=state.load('current.json')))
        state.save('binding.json',binding)
        state.save('baseline.json',dict(label=label,nodes=list(NODES),identity=binding,disks=disks,adopted=True,created=time.time()))
        if previous:state.save('current.json',None)
        print('已接管既有命名基线；未修改虚拟机。后续恢复仍会核对全部磁盘。')
    def vm(self,action,h,label=None,start=True):
        if h not in NODES or action not in ('save','restore','reset','start'):raise ValueError('VM 操作不在白名单')
        if action in ('save','restore') and not re.fullmatch(r'[A-Za-z0-9-]{1,80}',label or ''):raise ValueError('保存点名称无效')
        if action=='restore':self.snapshot_disks(h,label)
        # Verify copying while stopped: the official script does not propagate rsync failures.
        cmd=shlex.join(['/usr/local/bin/rht-vmctl','-y']+(['-n'] if action in ('save','restore') or not start else [])+[action,h]+([label] if label else []))
        r=self.t.run(cmd,timeout=300)
        if r.rc or 'Error:' in r.out:raise RuntimeError(r.out+r.err)
        if action in ('save','restore'):
            if self.t.run('LC_ALL=C virsh domstate '+h).require().strip()!='shut off':
                raise RuntimeError('磁盘校验前 VM 未停止：'+h)
            for path in self.snapshot_disks(h,label):
                self.t.run('cmp -s '+shlex.quote(path)+' '+shlex.quote(path+'-'+label),timeout=300).require()
            if start:self.vm('start',h)
        elif start:self.t.wait(h)
    def backup(self):
        # A failed backup must prevent reset. Never write backup into source tree.
        exists=self.t.ws('test -d '+BASE)
        if exists.rc==1:return None
        exists.require()
        p=subprocess.run(self.t.base+[shlex.join(INNER+['root@workstation','tar -C /home/devops -czf - ansible'])],capture_output=True,timeout=300)
        if p.returncode:raise RuntimeError('答案备份失败：'+p.stderr.decode(errors='replace'))
        with tarfile.open(fileobj=io.BytesIO(p.stdout),mode='r:gz') as tar:
            validate_answers(tar)
        dest=state.STATE/'backups'/(state.stamp()+'.tar.gz');dest.write_bytes(p.stdout);dest.chmod(0o600)
        return str(dest)
    def restore_answers(self, backup):
        """Stage a verified archive before swapping; retain the displaced files."""
        tag=state.stamp()
        staging='/home/devops/.rhce-restore-'+tag
        retired='/home/devops/.rhce-trainer-retired/restore-'+tag
        if backup:
            data=Path(backup).read_bytes()
            with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
                validate_answers(archive)
            self.t.ws('install -d -m 700 '+staging+' && tar -xzf - -C '+staging,data).require()
            self.t.ws('test -d '+staging+'/ansible').require()
        else:
            self.t.ws('install -d -m 700 '+staging).require()
        command='set -e; mkdir -p '+retired+'; if test -e '+BASE+'; then mv '+BASE+' '+retired+'/ansible; fi; '
        if backup:
            command+='if ! mv '+staging+'/ansible '+BASE+'; then test ! -e '+retired+'/ansible || mv '+retired+'/ansible '+BASE+'; exit 1; fi; '
        command+='rmdir '+staging
        self.t.ws(command).require()
        return retired
    def save_scene(self,nodes,kind,qid=None,keep_running=False,backup=None):
        self.guard(nodes)
        tag='rhce-'+kind+'-'+state.stamp()
        journal=dict(id=tag,kind=kind,question=qid,nodes=nodes,saved=[],restored=[],phase='saving',backup=backup if backup is not None else self.backup())
        state.save('journals/'+tag+'.json',journal)
        with ThreadPoolExecutor(max_workers=5) as pool:
            jobs={pool.submit(self.vm,'save',h,tag,keep_running):h for h in nodes}
            errors=[]
            for job in as_completed(jobs):
                h=jobs[job]
                try:job.result();journal['saved'].append(h);print('已保存现场：'+h,flush=True)
                except Exception as exc:errors.append(h+': '+str(exc))
                state.save('journals/'+tag+'.json',journal)
        if errors:
            journal['phase']='save_failed';state.save('journals/'+tag+'.json',journal)
            # Saving stops VMs; bring every attempted VM back without changing its disks.
            for h in nodes:
                try:
                    if self.t.run('LC_ALL=C virsh domstate '+h).require().strip()!='running':self.vm('start',h)
                except Exception as exc:errors.append('启动 '+h+': '+str(exc))
            raise RuntimeError('现场保存不完整，未恢复基线：'+'; '.join(errors))
        journal['phase']='ready';state.save('journals/'+tag+'.json',journal)
        return journal
    def restore_scene(self,j):
        if j['nodes']:self.guard(j['nodes'],require_space=False)
        j['phase']='restoring';state.save('journals/'+j['id']+'.json',j)
        failures=[]
        with ThreadPoolExecutor(max_workers=5) as pool:
            jobs={pool.submit(self.vm,'restore',h,j['id']):h for h in j['saved']}
            for job in as_completed(jobs):
                h=jobs[job]
                try:
                    job.result();print('已恢复评分前现场：'+h,flush=True)
                    if h not in j['restored']:j['restored'].append(h)
                except Exception as exc:failures.append(h+': '+str(exc))
                state.save('journals/'+j['id']+'.json',j)
        j['phase']='recovered' if not failures else 'recovery_required';state.save('journals/'+j['id']+'.json',j)
        if failures:raise RuntimeError('恢复未完成，运行 rhce recover '+j['id']+'；'+'; '.join(failures))
    def baseline(self,nodes):
        self.guard(nodes,require_space=False)
        baseline=state.load('baseline.json')
        if not baseline:raise RuntimeError('没有可用基线')
        for h in nodes:
            if h not in baseline['nodes']:raise RuntimeError('缺少基线：'+h)
        with ThreadPoolExecutor(max_workers=5) as pool:
            jobs={pool.submit(self.vm,'restore',h,baseline['label']):h for h in nodes}
            for job in as_completed(jobs):
                job.result();print('已恢复基线：'+jobs[job],flush=True)
    def ensure_control(self):
        self.t.ws('install -d -o devops -g devops -m 755 '+BASE).require()
        self.t.put(BASE+'/inventory',INVENTORY)
        self.t.put(BASE+'/ansible.cfg',CFG)
        self.t.ws('install -d -o devops -g devops '+BASE+'/roles '+BASE+'/mycollections').require()
    def preflight(self,q):
        """Check external dependencies before stopping a VM or moving an answer."""
        from .model import dependency_order
        needed=set(dependency_order(q['id']))|{q['id']}
        urls=[]
        if 2 in needed:
            urls += ['http://content.example.com/rhel9.0/x86_64/dvd/'+part for part in ('BaseOS/repodata/repomd.xml','AppStream/repodata/repomd.xml','RPM-GPG-KEY-redhat-release')]
        if 6 in needed:urls += ['http://classroom.example.com/content/'+x+'.tar.gz' for x in ('haproxy','phpinfo')]
        if 7 in needed:urls += ['http://content.example.com/'+x+'.tar.gz' for x in ('ansible-posix-1.5.1','community-general-6.3.0')]
        for n,file in ((15,'hwreport.empty'),(17,'user_list.yml'),(18,'salaries.yml')):
            if n in needed:urls.append('http://172.25.254.254/content/'+file)
        if needed & {16,17,18}:
            from .secrets import secrets
            secrets(self.config)
        if not urls:return []
        script='''import urllib.request,json,sys
out=[]
for url in json.load(sys.stdin):
 try:
  with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=10) as r:out.append(dict(url=url,status=r.status))
 except Exception as exc:out.append(dict(url=url,status=0,error=str(exc)))
print(json.dumps(out))'''
        rows=json.loads(self.t.ws('python3 -c '+shlex.quote(script),json.dumps(urls).encode()).require())
        failed=[r for r in rows if r['status']!=200]
        if failed:raise RuntimeError('资源前置检查失败：'+json.dumps(failed,ensure_ascii=False))
        return rows
    def repos(self,nodes):
        repo=''
        for name,label,folder in [('rh294_BASE','base','BaseOS'),('rh294_STREAM','stream','AppStream')]:
            repo+=f'[{name}]\nname=rh294 {label} software\nbaseurl=http://content.example.com/rhel9.0/x86_64/dvd/{folder}\nenabled=1\ngpgcheck=1\ngpgkey=http://content.example.com/rhel9.0/x86_64/dvd/RPM-GPG-KEY-redhat-release\n\n'
        for h in nodes:self.t.node(h,'cat > /etc/yum.repos.d/rhce-prerequisite.repo',repo.encode()).require()
    def collections(self):
        for name in ('ansible-posix-1.5.1','community-general-6.3.0'):
            self.t.dev('ansible-galaxy collection install http://content.example.com/'+name+'.tar.gz -p mycollections').require()
    def prepare(self,q,grading=False,prerequisites_ready=False):
        n=q['id'];nodes=q['nodes']
        # During grading never replace student's inventory/configuration.
        if not grading and not prerequisites_ready and n!=1:self.ensure_control()
        if not prerequisites_ready and 2 in q['dependencies']:self.repos(nodes)
        if not grading and not prerequisites_ready and 7 in q['dependencies']:self.collections()
        if n in (4,5):
            if not grading:self.t.ws('dnf -y install rhel-system-roles',timeout=600).require()
        if n==5:
            for h in nodes:self.t.node(h,'setenforce 0; sed -i "s/^SELINUX=.*/SELINUX=permissive/" /etc/selinux/config').require()
        if n==9 and not prerequisites_ready:
            if not grading:
                self.t.put(BASE+'/roles/requirements.yml','- name: balancer\n  src: http://classroom.example.com/content/haproxy.tar.gz\n- name: phpinfo\n  src: http://classroom.example.com/content/phpinfo.tar.gz\n')
                self.t.dev('ansible-galaxy role install -r roles/requirements.yml -p roles --force').require()
            # Prerequisite Q8 is applied independently; target Q9 remains undone.
            for h in ('serverc','serverd'):
                self.t.node(h,'set -e; dnf -y install httpd firewalld php; systemctl enable --now httpd firewalld php-fpm; firewall-cmd --permanent --add-service=http; firewall-cmd --add-service=http; printf "Welcome to %s on %s\\n" "$(hostname -f)" "$(hostname -I | cut -d\" \" -f1)" > /var/www/html/index.html',timeout=600).require()
            self.t.node('bastion','systemctl disable --now httpd 2>/dev/null || true').require()
        if n==9 and prerequisites_ready:
            # Q3 supplies PHP and Q8 supplies the backend sites; PHP-FPM remains
            # an environment prerequisite for the supplied phpinfo role.
            for h in ('serverc','serverd'):
                self.t.node(h,'dnf -y install php-fpm && systemctl enable --now php-fpm',timeout=600).require()
            self.t.node('bastion','systemctl disable --now httpd 2>/dev/null || true').require()
        if n==10:
            def prepare_volume(h):
                end=800 if h in ('servera','serverb') else 600
                cmd=f'''set -e
[ -b /dev/vdb ]
[ "$(lsblk -n -o TYPE /dev/vdb | wc -l)" -eq 1 ]
! findmnt -rn -S /dev/vdb
! pvs --noheadings -o pv_name 2>/dev/null | grep -q /dev/vdb
dnf -y install parted lvm2
parted -s /dev/vdb mklabel msdos mkpart primary 1MiB {end}MiB set 1 lvm on
udevadm settle
vgcreate research /dev/vdb1
vgs --noheadings --units m -o vg_name,vg_free research
'''
                self.t.node(h,cmd,timeout=600).require()
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(prepare_volume,('servera','serverb','serverc','serverd')))
        if n==11:
            self.t.node('servera','set -e; test ! -b /dev/vdd; test "$(lsblk -n -o TYPE /dev/vdb | wc -l)" -eq 1; dnf -y install parted',timeout=600).require()
        if n==14:
            # Firewall running is an environmental prerequisite; HTTP remains closed.
            self.t.node('servera','systemctl start firewalld').require()
        if n==17 and not grading and not prerequisites_ready:
            from .secrets import secrets
            s=secrets(self.config)
            self.t.put(BASE+'/secret.txt',s['vault']+'\n')
            self.t.put(BASE+'/locker.yml',json.dumps({'pw_developer':s['developer'],'pw_manager':s['manager']}))
            self.t.dev('ansible-vault encrypt --vault-password-file secret.txt locker.yml').require()
        if n==19:self.t.node('servera','id natasha >/dev/null 2>&1 || useradd natasha').require()
    def clear_artifacts(self,q):
        # Move exactly enumerated paths inside the project, never rm recursively.
        tag=state.stamp()
        for rel in q['artifacts']:
            if rel.startswith('/') or '..' in Path(rel).parts:raise ValueError('危险题库路径')
            src=BASE+'/'+rel;dst='/home/devops/.rhce-trainer-retired/'+tag+'/'+rel
            self.t.ws('if test -e '+shlex.quote(src)+'; then mkdir -p '+shlex.quote(str(Path(dst).parent))+'; mv -- '+shlex.quote(src)+' '+shlex.quote(dst)+'; fi').require()
    def verify_ready(self,q):
        code='import json,sys,os; print(json.dumps([p for p in json.load(sys.stdin) if os.path.lexists("/home/devops/ansible/"+p)]))'
        remaining=json.loads(self.t.ws('python3 -c '+shlex.quote(code),json.dumps(q['artifacts']).encode()).require())
        if remaining:raise RuntimeError('重置后仍有本题产物：'+', '.join(remaining))
        for h in q['nodes']:
            self.t.ws('sudo -u devops -H '+shlex.join(INNER+['devops@'+h,'sudo -n true'])).require()
        if q['id']==10:
            for h in q['nodes']:
                rows=self.t.node(h,'vgs --noheadings --units b --nosuffix -o vg_name,vg_free').require().splitlines()
                groups={row.split()[0]:float(row.split()[1]) for row in rows if len(row.split())==2}
                free=groups.get('research',0)
                valid=(free>=600*1024**2 if h in ('servera','serverb') else 400*1024**2<=free<600*1024**2 if h in ('serverc','serverd') else 'research' not in groups)
                if not valid or self.t.node(h,'lvs research/data').rc==0:
                    raise RuntimeError(h+' 的 LVM 前置条件不正确')
    def reset(self,q):
        from .prerequisites import Prerequisites,reset_nodes
        scope=reset_nodes(q)
        print('正在检查第 '+str(q['id'])+' 题的资源并备份答案……',flush=True)
        self.preflight(q)
        backup=self.backup()
        print('本次保存和恢复的受管节点：'+(', '.join(scope) if scope else '无'),flush=True)
        j=self.save_scene(scope,'reset',q['id'],backup=backup) if scope else None
        if j is None:
            j=dict(id='rhce-reset-'+state.stamp(),kind='reset',question=q['id'],nodes=[],saved=[],restored=[],backup=backup,phase='ready')
        j['backup']=backup
        try:
            j['phase']='preparing';state.save('journals/'+j['id']+'.json',j)
            if scope:self.baseline(scope)
            Prerequisites(self).ensure(q)
            self.clear_artifacts(q);self.prepare(q,prerequisites_ready=True);self.verify_ready(q)
        except BaseException:
            failures=[]
            try:self.restore_scene(j)
            except BaseException as exc:failures.append('虚拟机恢复：'+str(exc))
            try:
                self.restore_answers(backup);j['controller_restored']=True
            except BaseException as exc:failures.append('答案恢复：'+str(exc))
            j['phase']='recovery_required' if failures else 'recovered'
            state.save('journals/'+j['id']+'.json',j)
            if failures:raise RuntimeError('重置失败且恢复未完成；恢复点 '+j['id']+'；'+'; '.join(failures))
            raise
        j['phase']='prepared';state.save('journals/'+j['id']+'.json',j)
        state.save('current.json',dict(question=q['id'],backup=backup,journal=j['id'],time=time.time()))
        print('第 '+str(q['id'])+' 题已准备；目标题产物未写入。备份：'+str(backup))
    def restore_lab(self):
        j=self.save_scene(list(NODES),'restore')
        try:self.baseline(list(NODES))
        except BaseException:
            self.restore_scene(j)
            raise
        j['phase']='prepared';state.save('journals/'+j['id']+'.json',j)
        return j
    def init(self,prepare_only=False):
        previous=state.load('baseline.json')
        if previous:
            if not prepare_only:raise RuntimeError('基线已存在；显式使用 rhce init --prepare 补齐公共准备，保留原基线')
            self.guard(list(NODES),require_space=False)
            for h in NODES:self.snapshot_disks(h,previous['label'])
        if prepare_only:
            if not previous:
                identity=self.identity()
                binding=state.load('binding.json')
                if binding and binding!=identity:raise RuntimeError('已有身份绑定与当前环境不一致；停止公共准备')
            self.bootstrap_nodes()
            print('公共准备全部通过；未创建或更新基线，未重置虚拟机。')
            return
        # Preserve first-init safeguards: no existing saves, no implicit baseline replacement.
        binding=self.identity()
        old_binding=state.load('binding.json')
        if old_binding and old_binding!=binding:raise RuntimeError('已有身份绑定与当前环境不一致；停止初始化')
        for h in NODES:
            r=self.t.run('find /var/lib/libvirt/images -maxdepth 1 -name '+shlex.quote('rh294-'+h+'-*.ovl-*')+' -print').require()
            if r.strip():raise RuntimeError(h+' 已有保存点；请人工核对并 adopt-baseline，不会自动覆盖')
        state.save('binding.json',binding)
        self.guard(list(NODES))
        self.backup()
        for h in NODES:
            print('从原始镜像初始化：'+h,flush=True);self.vm('reset',h)
        self.bootstrap_nodes()
        for h in NODES:
            if h!='bastion':self.t.node(h,'test "$(lsblk -n -o TYPE /dev/vdb | wc -l)" -eq 1').require()
        label='rhce-baseline-'+state.stamp()
        print('本次基线名称：'+label,flush=True)
        for h in NODES:
            print('保存已验证基线：'+h,flush=True);self.vm('save',h,label)
        state.save('baseline.json',dict(label=label,nodes=list(NODES),identity=binding,created=time.time()))
        print('公共准备全部通过，命名基线已创建：'+label)

    def resume_init(self,label):
        if not re.fullmatch(r'rhce-baseline-\d{14}-[0-9a-f]{6}',label):raise ValueError('基线名称无效')
        if state.load('baseline.json'):raise RuntimeError('基线已存在，不需要续建')
        reports=sorted((state.STATE/'reports').glob('*-init.json'))
        if not reports or not json.loads(reports[-1].read_text()).get('complete'):
            raise RuntimeError('找不到成功的公共准备报告，不能续建基线')
        self.guard(list(NODES))
        binding=state.load('binding.json')
        for h in NODES:
            saved=self.t.run('find /var/lib/libvirt/images -maxdepth 1 -name '+shlex.quote('rh294-'+h+'-*.ovl-'+label)+' -print').require().splitlines()
            if saved:
                paths=self.snapshot_disks(h,label)
                if set(saved)!=set(p+'-'+label for p in paths):raise RuntimeError(h+' 的基线磁盘不完整')
                if self.t.run('LC_ALL=C virsh domstate '+h).require().strip()!='shut off':
                    raise RuntimeError(h+' 已运行，无法校验中断前的磁盘副本；请先核对现场')
                for path in paths:self.t.run('cmp -s '+shlex.quote(path)+' '+shlex.quote(path+'-'+label),timeout=300).require()
                self.vm('start',h)
                print('已校验并启动已保存基线：'+h,flush=True)
            else:
                print('续存基线：'+h,flush=True)
                self.vm('save',h,label)
        disks={h:self.snapshot_disks(h,label) for h in NODES}
        state.save('baseline.json',dict(label=label,nodes=list(NODES),identity=binding,disks=disks,created=time.time()))
        print('命名基线续建完成：'+label)

    def bootstrap_nodes(self):
        script=(Path(__file__).parent/'remote/bootstrap.py').read_bytes()
        results=[]
        def step(label,operation):
            try:
                value=operation()
                results.append(dict(item=label,status='PASS'))
                print('[通过] '+label,flush=True)
                return value
            except (RuntimeError,OSError,subprocess.SubprocessError) as exc:
                results.append(dict(item=label,status='FAIL',error=str(exc)))
                print('[失败] '+label+'：'+str(exc),flush=True)
                return None
        def remote(action,host=None,*args):
            command=shlex.join(['python3','-',action]+list(args))
            return (self.t.node(host,command,script) if host else self.t.ws(command,script)).require()
        public=step('workstation：安装并验证 devops 私钥（600）',lambda:remote('key'))
        for h in NODES:
            if public:
                step(h+'：devops、公钥、免密 sudo'+('、密码 redhat' if h=='bastion' else ''),lambda h=h:remote('account',h,h,public.strip()))
            else:
                results.append(dict(item=h+'：公钥准备',status='SKIP',error='workstation 私钥准备失败'))
                print('[跳过] '+h+'：workstation 私钥准备失败',flush=True)
            step(h+'：备份并清理 repo 文件',lambda h=h:remote('repos',h))
            step(h+'：devops 免密 SSH 与 sudo 验证',lambda h=h:self.t.ws('sudo -iu devops '+shlex.join(INNER+['devops@'+h,'test "$(id -un)" = devops && sudo -n true'])).require())
        step('workstation：ansible-navigator 配置与有效设置验证',lambda:remote('navigator'))
        step('workstation：Podman 仓库格式与有效配置验证',lambda:remote('podman'))
        path='reports/'+state.stamp()+'-init.json'
        success=all(row['status']=='PASS' for row in results)
        state.save(path,dict(operation='common-preparation',complete=success,items=results))
        print('公共准备报告：'+str(state.STATE/path),flush=True)
        if not success:raise RuntimeError('公共准备未完成；失败/跳过项见报告。不会建立基线；修复后可显式 init --prepare 重试')
