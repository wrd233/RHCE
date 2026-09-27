"""Complete declared prerequisite questions before exposing a reset target."""
import json,shlex
from .engine import BASE,CFG,INVENTORY
from .model import question,dependency_order
from .transport import NODES

def reset_nodes(q):
    required=set(q['nodes'])
    for n in dependency_order(q['id']):required.update(question(n)['nodes'])
    return [h for h in NODES if h in required]

class Prerequisites:
    def __init__(self,engine):self.e=engine;self.t=engine.t;self.details={}

    def _file(self,path):return self.t.ws('test -e '+shlex.quote(BASE+'/'+path)).rc==0

    def _playbook(self,name,plays):
        self.t.put(BASE+'/'+name,json.dumps(plays,ensure_ascii=False,indent=2)+'\n')
        self.t.dev('ansible-playbook '+shlex.quote(name),timeout=1800).require()

    def check(self,n):
        from .grading import Grading
        from . import graders
        g=Grading(self.e,question(n),fast=True)
        if n==1:
            try:graders.config(g)
            except (RuntimeError,ValueError):return False
            return all(c['passed'] for c in g.checks)
        if n==2:
            if not self._file('yum_repo.yml'):return False
            script='''import configparser,json,pathlib
out=[]
for p in pathlib.Path('/etc/yum.repos.d').glob('*.repo'):
 try:
  c=configparser.ConfigParser(interpolation=None);c.read(p)
  out.extend(dict(id=s,**dict(c[s])) for s in c.sections())
 except Exception:pass
print(json.dumps(out))'''
            for h in question(2)['nodes']:
                try:rows=json.loads(self.t.node(h,'python3 -B -c '+shlex.quote(script)).require())
                except (RuntimeError,ValueError):return False
                g.obs[h]={'repos':rows}
            graders.repos(g)
            return all(c['passed'] for c in g.checks)
        if n==3:
            if not self._file('packages.yml'):return False
            packages={h:self.t.node(h,'rpm -q php mariadb') for h in question(3)['nodes']}
            group=self.t.node('servera','LC_ALL=C dnf -q group list --installed',timeout=180)
            updates=self.t.node('servera','dnf -q check-update',timeout=300)
            self.details[n]=dict(package_rc={h:r.rc for h,r in packages.items()},group_rc=group.rc,group_present='Development Tools' in group.out,group_output=group.out[-500:],updates_rc=updates.rc,updates_output=updates.out[-500:],updates_error=updates.err[-300:])
            return all(r.rc==0 for r in packages.values()) and group.rc==0 and 'Development Tools' in group.out and updates.rc==0
        if n==6:
            code='''import yaml,pathlib,json
p=pathlib.Path('roles/requirements.yml')
try:
 rows=yaml.safe_load(p.read_text());expected={'balancer':'http://classroom.example.com/content/haproxy.tar.gz','phpinfo':'http://classroom.example.com/content/phpinfo.tar.gz'}
 ok=isinstance(rows,list) and all(any(isinstance(x,dict) and x.get('name')==n and x.get('src')==url for x in rows) and (pathlib.Path('roles')/n/'tasks/main.yml').is_file() for n,url in expected.items())
except Exception:ok=False
print(json.dumps(ok))'''
            r=self.t.dev('python3 -B -c '+shlex.quote(code))
            return r.rc==0 and r.out.strip()=='true'
        if n==7:
            try:graders.install_collections(g)
            except (RuntimeError,ValueError):return False
            return all(c['passed'] for c in g.checks)
        if n==8:
            if any(not self._file(p) for p in question(8)['artifacts']):return False
            for h in ('serverc','serverd'):
                checks=['rpm -q httpd firewalld','systemctl is-active --quiet httpd','systemctl is-active --quiet firewalld','systemctl is-enabled --quiet httpd','systemctl is-enabled --quiet firewalld','firewall-cmd --quiet --query-service=http','firewall-cmd --permanent --quiet --query-service=http']
                if any(self.t.node(h,cmd).rc for cmd in checks):return False
                page=self.t.node(h,'cat /var/www/html/index.html')
                expected='Welcome to '+h+'.lab.example.com on 172.25.250.'+('12' if h=='serverc' else '13')
                if page.rc or page.out.strip()!=expected:return False
            return True
        if n==16:
            try:graders.vault_create(g)
            except (RuntimeError,ValueError):return False
            return all(c['passed'] for c in g.checks)
        raise RuntimeError('尚无第 '+str(n)+' 题的自动前置完成器')

    def complete(self,n):
        q=question(n)
        self.e.clear_artifacts(q)
        if n==1:
            self.t.ws('dnf -y install ansible-core ansible-navigator',timeout=900).require()
            self.e.ensure_control()
        elif n==2:
            tasks=[]
            for name,word,folder in [('rh294_BASE','base','BaseOS'),('rh294_STREAM','stream','AppStream')]:
                tasks.append({'ansible.builtin.yum_repository':dict(name=name,description='rh294 '+word+' software',baseurl='http://content.example.com/rhel9.0/x86_64/dvd/'+folder,enabled=True,gpgcheck=True,gpgkey='http://content.example.com/rhel9.0/x86_64/dvd/RPM-GPG-KEY-redhat-release')})
            self._playbook('yum_repo.yml',[dict(hosts='all',tasks=tasks)])
        elif n==3:
            self._playbook('packages.yml',[dict(hosts='dev:test:prod',tasks=[{'ansible.builtin.dnf':dict(name=['php','mariadb'],state='present')}]),dict(hosts='dev',tasks=[{'ansible.builtin.dnf':dict(name='@Development Tools',state='present')},{'ansible.builtin.dnf':dict(name='*',state='latest')}])])
        elif n==6:
            self.t.put(BASE+'/roles/requirements.yml','- name: balancer\n  src: http://classroom.example.com/content/haproxy.tar.gz\n- name: phpinfo\n  src: http://classroom.example.com/content/phpinfo.tar.gz\n')
            self.t.dev('ansible-galaxy role install -r roles/requirements.yml -p roles --force').require()
        elif n==7:self.e.collections()
        elif n==8:
            self.t.put(BASE+'/roles/apache/tasks/main.yml',json.dumps([
                {'ansible.builtin.dnf':dict(name=['httpd','firewalld'],state='present')},
                {'ansible.builtin.service':dict(name='{{ item }}',enabled=True,state='started'),'loop':['httpd','firewalld']},
                {'ansible.posix.firewalld':dict(service='http',permanent=True,immediate=True,state='enabled')},
                {'ansible.builtin.template':dict(src='index.html.j2',dest='/var/www/html/index.html')}
            ],indent=2)+'\n')
            self.t.put(BASE+'/roles/apache/templates/index.html.j2','Welcome to {{ ansible_fqdn }} on {{ ansible_default_ipv4.address }}\n')
            self._playbook('newrole.yml',[dict(hosts='webservers',roles=['apache'])])
        elif n==16:
            from .secrets import secrets
            s=secrets(self.e.config)
            self.t.put(BASE+'/secret.txt',s['vault']+'\n')
            self.t.put(BASE+'/locker.yml',json.dumps({'pw_developer':s['developer'],'pw_manager':s['manager']}))
            self.t.dev('ansible-vault encrypt --vault-password-file secret.txt locker.yml').require()
        else:raise RuntimeError('尚无第 '+str(n)+' 题的自动前置完成器')

    def ensure(self,q):
        for n in dependency_order(q['id']):
            if self.check(n):
                print('前置第 '+str(n)+' 题：已完成',flush=True)
                continue
            print('前置第 '+str(n)+' 题：缺失，正在补做并验证……',flush=True)
            self.complete(n)
            if not self.check(n):raise RuntimeError('前置第 '+str(n)+' 题补做后验证失败：'+json.dumps(self.details.get(n,{}),ensure_ascii=False))
            print('前置第 '+str(n)+' 题：已补做并验证',flush=True)
