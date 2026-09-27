"""Read-only observations, executed via stdin on a managed VM as root."""
import sys,subprocess,json,os,stat,configparser,socket,pathlib,pwd,grp

def cmd(s):
 p=subprocess.run(s,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
 return {'rc':p.returncode,'out':p.stdout.strip(),'err':p.stderr.strip()}
def file(p):
 try:
  s=os.lstat(p)
  return dict(exists=True,kind='directory' if stat.S_ISDIR(s.st_mode) else 'symlink' if stat.S_ISLNK(s.st_mode) else 'file' if stat.S_ISREG(s.st_mode) else 'other',mode=oct(stat.S_IMODE(s.st_mode)),uid=s.st_uid,gid=s.st_gid,group=grp.getgrgid(s.st_gid).gr_name,link=os.readlink(p) if stat.S_ISLNK(s.st_mode) else None,text=pathlib.Path(p).read_text(errors='replace') if stat.S_ISREG(s.st_mode) and s.st_size<100000 else None)
 except FileNotFoundError:return {'exists':False}
fast='--fast' in sys.argv
profile=json.loads(sys.argv[sys.argv.index('--fast')+1]) if fast else None
r={'hostname':None if fast else socket.getfqdn(),'files':{},'commands':{}}
files=['/etc/issue','/etc/myhosts','/root/hwreport.txt','/var/www/html/index.html','/webdev','/webdev/index.html','/var/www/html/webdev','/etc/chrony.conf','/etc/selinux/config','/etc/fstab']
for p in profile.get('files',[]) if fast else files:
 r['files'][p]=file(p)
commands={
'packages':'rpm -q php mariadb httpd rhel-system-roles',
'httpd_active':'systemctl is-active httpd','httpd_enabled':'systemctl is-enabled httpd',
'firewall_active':'systemctl is-active firewalld','firewall_enabled':'systemctl is-enabled firewalld',
'firewall_http':'firewall-cmd --query-service=http','firewall_http_permanent':'firewall-cmd --permanent --query-service=http',
'firewall_ports':'firewall-cmd --list-ports','firewall_ports_permanent':'firewall-cmd --permanent --list-ports',
'selinux':'getenforce','chrony':'systemctl is-active chronyd','ntp':'chronyc -n sources',
'lv':'lvs --reportformat json --units b --nosuffix -o vg_name,lv_name,lv_size',
'block':'lsblk -b -J -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT',
'mounts':'findmnt -J -o SOURCE,TARGET,FSTYPE',
'cron':'crontab -l -u natasha',
'facts':'/usr/bin/python3 -c "import json; from ansible.module_utils.facts import ansible_facts; print(json.dumps(ansible_facts()))"',
'bios':'cat /sys/class/dmi/id/bios_version','memory':'awk \'/MemTotal/ {print int($2/1024)}\' /proc/meminfo',
}
# Ansible module_utils may not be installed on managed hosts; local facts fallbacks above.
if fast:commands={k:commands[k] for k in profile.get('commands',[])}
for k,v in commands.items():r['commands'][k]=cmd(v)
repos=[]
if not fast or profile.get('repos'):
 for path in pathlib.Path('/etc/yum.repos.d').glob('*.repo'):
  try:
   c=configparser.ConfigParser(interpolation=None);c.read(path)
   repos.extend(dict(id=s,file=str(path),**dict(c[s])) for s in c.sections())
  except Exception as e:repos.append({'error':str(e)})
r['repos']=repos
print(json.dumps(r))
