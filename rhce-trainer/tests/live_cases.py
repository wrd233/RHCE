"""Opt-in acceptance fixtures. Never used by `rhce reset` or `rhce show`.
Run only with explicit development authorization; overwrites question artifacts after backups.
"""
import json,sys,shlex
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rhce_trainer.engine import Engine,BASE
from rhce_trainer import state
from rhce_trainer.model import question
from rhce_trainer.grading import Grading

def play(hosts,tasks,**kw):return dict(hosts=hosts,tasks=tasks,**kw)
def task(module,args,**kw):return {module:args,**kw}
def write(e,rel,value):e.t.put(BASE+'/'+rel,json.dumps(value,indent=2) if not isinstance(value,str) else value)

def fixture(e,n):
 q=question(n)
 if n==1:e.ensure_control();return
 if n==6:
  write(e,'roles/requirements.yml',[dict(name='balancer',src='http://classroom.example.com/content/haproxy.tar.gz'),dict(name='phpinfo',src='http://classroom.example.com/content/phpinfo.tar.gz')]);e.t.dev('ansible-galaxy role install -r roles/requirements.yml -p roles --force').require();return
 if n==7:e.collections();return
 if n==16:
  from rhce_trainer.secrets import secrets
  s=secrets(e.config);write(e,'secret.txt',s['vault']+'\n');write(e,'locker.yml',dict(pw_developer=s['developer'],pw_manager=s['manager']));e.t.dev('ansible-vault encrypt --vault-password-file secret.txt locker.yml').require();return
 if n==18:
  from rhce_trainer.secrets import secrets
  s=secrets(e.config)
  code='''import json,sys,urllib.request,pathlib
from ansible.parsing.vault import VaultLib,VaultSecret
p=json.load(sys.stdin); raw=urllib.request.urlopen('http://172.25.254.254/content/salaries.yml').read(); old=VaultLib([('default',VaultSecret(p['old'].encode()))]); plain=old.decrypt(raw); new=VaultLib([('default',VaultSecret(p['new'].encode()))]);pathlib.Path('salaries.yml').write_bytes(new.encrypt(plain))'''
  e.t.dev('python3 -c '+shlex.quote(code),json.dumps(s).encode()).require();return
 if n==2:
  tasks=[]
  for name,word,folder in [('rh294_BASE','base','BaseOS'),('rh294_STREAM','stream','AppStream')]:
   tasks.append(task('ansible.builtin.yum_repository',dict(name=name,description='rh294 '+word+' software',baseurl='http://content.example.com/rhel9.0/x86_64/dvd/'+folder,enabled=True,gpgcheck=True,gpgkey='http://content.example.com/rhel9.0/x86_64/dvd/RPM-GPG-KEY-redhat-release')))
  data=[play('all',tasks)]
 if n==3:
  data=[play('dev:test:prod',[task('ansible.builtin.dnf',dict(name=['php','mariadb'],state='present'))]),play('dev',[task('ansible.builtin.dnf',dict(name='@Development Tools',state='present')),task('ansible.builtin.dnf',dict(name='*',state='latest'))])]
 if n==4:data=[dict(hosts='all',roles=['rhel-system-roles.timesync'],vars=dict(timesync_ntp_servers=[dict(hostname='classroom.example.com',iburst=True)]))]
 if n==5:data=[dict(hosts='all',roles=['rhel-system-roles.selinux'],vars=dict(selinux_state='enforcing',selinux_policy='targeted'))]
 if n==8:
  write(e,'roles/apache/tasks/main.yml',[task('ansible.builtin.dnf',dict(name=['httpd','firewalld'],state='present')),task('ansible.builtin.service',dict(name='{{ item }}',enabled=True,state='started'),loop=['httpd','firewalld']),task('ansible.posix.firewalld',dict(service='http',permanent=True,immediate=True,state='enabled')),task('ansible.builtin.template',dict(src='index.html.j2',dest='/var/www/html/index.html'))])
  write(e,'roles/apache/templates/index.html.j2','Welcome to {{ ansible_fqdn }} on {{ ansible_default_ipv4.address }}\n')
  data=[dict(hosts='webservers',roles=['apache'])]
 if n==9:data=[dict(hosts='balancers',roles=['balancer']),dict(hosts='webservers',roles=['phpinfo'])]
 if n==10:
  data=[play('all',[dict(block=[task('community.general.lvol',dict(vg='research',lv='data',size='600m'))],rescue=[task('ansible.builtin.debug',dict(msg='Could not create logical volume of that size')),task('community.general.lvol',dict(vg='research',lv='data',size='400m'))],always=[task('community.general.filesystem',dict(fstype='ext4',dev='/dev/research/data'))],when="'research' in ansible_lvm.vgs"),task('ansible.builtin.debug',dict(msg='Volume group does not exist'),when="'research' not in ansible_lvm.vgs")])]
 if n==11:
  data=[play('dev',[task('ansible.builtin.debug',dict(msg='disk /dev/vdd does not exist'),when="'vdd' not in ansible_devices"),dict(block=[task('community.general.parted',dict(device='/dev/vdb',number=1,state='present',part_start='1MiB',part_end='1501MiB'))],rescue=[task('ansible.builtin.debug',dict(msg='Could not create partition of that size')),task('community.general.parted',dict(device='/dev/vdb',number=1,state='present',part_start='1MiB',part_end='801MiB'))]),task('community.general.filesystem',dict(fstype='ext4',dev='/dev/vdb1')),task('ansible.posix.mount',dict(path='/mnt/fs01',src='/dev/vdb1',fstype='ext4',state='mounted'))])]
 if n==12:
  write(e,'hosts.j2','127.0.0.1 localhost localhost.localdomain localhost4 localhost4.localdomain4\n::1 localhost localhost.localdomain localhost6 localhost6.localdomain6\n{% for h in groups.all %}\n{{ hostvars[h].ansible_default_ipv4.address }} {{ hostvars[h].ansible_fqdn }} {{ hostvars[h].ansible_hostname }}\n{% endfor %}\n')
  data=[play('all',[]),play('dev',[task('ansible.builtin.template',dict(src='hosts.j2',dest='/etc/myhosts'))])]
 if n==13:
  data=[play('all',[task('ansible.builtin.copy',dict(content=txt+'\n',dest='/etc/issue'),when="'"+grp+"' in group_names") for grp,txt in [('dev','Development'),('test','Test'),('prod','Production')]])]
 if n==14:
  data=[play('dev',[task('ansible.builtin.dnf',dict(name='httpd',state='present')),task('ansible.builtin.service',dict(name='httpd',state='started',enabled=True)),task('ansible.posix.firewalld',dict(service='http',immediate=True,permanent=True,state='enabled')),task('ansible.builtin.file',dict(path='/webdev',state='directory',group='devops',mode='2775',setype='httpd_sys_content_t')),task('ansible.builtin.copy',dict(dest='/webdev/index.html',content='Development\n',setype='httpd_sys_content_t')),task('ansible.builtin.file',dict(src='/webdev',dest='/var/www/html/webdev',state='link'))])]
 if n==15:
  tasks=[task('ansible.builtin.get_url',dict(url='http://172.25.254.254/content/hwreport.empty',dest='/root/hwreport.txt'))]
  for k,v in [('inventoryhostname','{{ inventory_hostname }}'),('memory_in_MB','{{ ansible_memtotal_mb }}'),('BIOS_version','{{ ansible_bios_version }}'),('disk_vda_size',"{{ ansible_devices.vda.size | default('NONE') }}"),('disk_vdb_size',"{{ ansible_devices.vdb.size | default('NONE') }}")]:tasks.append(task('ansible.builtin.replace',dict(path='/root/hwreport.txt',regexp=k,replace=v)))
  data=[play('all',tasks)]
 if n==17:
  e.t.dev('curl -fsS http://172.25.254.254/content/user_list.yml -o user_list.yml').require()
  data=[]
  for targets,job,group,key in [('dev:test','developer','devops','pw_developer'),('prod','manager','opsmgr','pw_manager')]:
   data.append(play(targets,[task('ansible.builtin.group',dict(name=group,state='present')),task('ansible.builtin.user',dict(name='{{ item.name }}',groups=group,append=True,password='{{ '+key+" | password_hash('sha512') }}"),loop='{{ users }}',when="item.job == '"+job+"'")],vars_files=['locker.yml','user_list.yml']))
 if n==19:data=[play('dev',[task('ansible.builtin.cron',dict(name='say hello',user='natasha',minute='*/2',job='echo hello'))])]
 write(e,q['playbook'],data)

def run(numbers):
 e=Engine()
 for n in numbers:
  print('LIVE START',n,flush=True)
  try:
   e.reset(question(n));fixture(e,n)
   r=Grading(e,question(n),'live' if n==12 else 'pdf').grade()
   state.save('reports/live-q'+str(n)+'.json',r)
   print('LIVE RESULT',n,r['score'],flush=True)
   for c in r['checkpoints']:
    if not c['passed']:print(c,flush=True)
  except Exception as exc:
   print('LIVE ERROR',n,str(exc),flush=True)
   state.save('reports/live-q'+str(n)+'-error.json',dict(question=n,error=str(exc)))
   raise
if __name__=='__main__':
 with state.locked():run([int(x) for x in sys.argv[1:]])
