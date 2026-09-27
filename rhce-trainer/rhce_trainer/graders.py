"""Question-specific checkpoints. No reference YAML equality comparisons."""
import json,re,shlex,hashlib,ast
from .transport import NODES
from .engine import BASE


def managed(g):
    n=g.q['id']
    f=MANAGED.get(n)
    if f is None:raise RuntimeError('本题评分器尚未接入：'+str(n))
    f(g)

def issue(g):
    for h,txt,w in [('servera','Development',20),('serverb','Test',15),('serverc','Production',15),('serverd','Production',15)]:
        actual=g.file(h,'/etc/issue').get('text')
        g.state_check(h+'.issue',h+' 登录提示内容',w,actual in (txt,txt+'\n'),{'actual':actual,'expected':txt},'cat /etc/issue')
    seen={e['host'] for e in g.events}
    g.state_check('all-hosts','在所有清单主机运行',5,set(NODES)<=seen,sorted(seen),'Ansible execution events')

def apache(g):
    role=all(g.has_event(role='apache',host=h) for h in g.q['nodes'])
    g.state_check('role','实际在 webservers 使用 apache 角色',10,role,[e for e in g.events if e['role']],'Ansible role execution events')
    for h in g.q['nodes']:
        c=g.obs[h]['commands']
        g.state_check(h+'.httpd',h+' httpd 已安装、启用并运行',10,'httpd-' in c['packages']['out'] and c['httpd_active']['out']=='active' and c['httpd_enabled']['out']=='enabled', {k:c[k]['out'] for k in ('packages','httpd_active','httpd_enabled')},'rpm -q httpd; systemctl is-enabled/is-active httpd')
        g.state_check(h+'.firewall',h+' 防火墙启用并运行',5,c['firewall_active']['out']=='active' and c['firewall_enabled']['out']=='enabled',{k:c[k]['out'] for k in ('firewall_active','firewall_enabled')},'systemctl is-enabled/is-active firewalld')
        opened=(c['firewall_http']['out']=='yes' or '80/tcp' in c['firewall_ports']['out']) and (c['firewall_http_permanent']['out']=='yes' or '80/tcp' in c['firewall_ports_permanent']['out'])
        g.state_check(h+'.http-rule',h+' HTTP 持久及运行规则允许访问',5,opened,{k:c[k]['out'] for k in ('firewall_http','firewall_http_permanent','firewall_ports','firewall_ports_permanent')},'firewall-cmd runtime and permanent service/port checks')
        ip='172.25.250.'+('12' if h=='serverc' else '13');expect=f'Welcome to {h}.lab.example.com on {ip}'
        r=g.t.ws('curl -fsS --max-time 10 http://'+h+'/')
        template=g.has_event(action='template',role='apache',host=h,dest='/var/www/html/index.html',src='index.html.j2')
        g.state_check(h+'.template',h+' apache 使用 index.html.j2 生成页面',5,template,{'template_used':template},'apache template event, source and destination')
        g.state_check(h+'.page',h+' HTTP 页面内容正确',5,r.rc==0 and r.out.strip()==expect,{'actual':r.out.strip(),'expected':expect},'curl from workstation')

def lvm(g):
    for h in NODES:
        try:
            lvs=json.loads(g.out(h,'lv'))['report'][0]['lv']
        except (ValueError,KeyError):lvs=[]
        data=[x for x in lvs if x.get('vg_name')=='research' and x.get('lv_name')=='data']
        if h=='bastion':
            ok=not data and g.message(h,'Volume group does not exist')
            g.state_check(h+'.missing','bastion 卷组缺失分支',10,ok,{'lvs':lvs,'message':g.message(h,'Volume group does not exist')},'lvs + per-host debug event')
        else:
            size=600 if h in ('servera','serverb') else 400
            valid=bool(data) and abs(float(data[0]['lv_size'])-size*1024**2)<1024**2
            fs=g.t.node(h,'blkid -c /dev/null -s TYPE -o value /dev/research/data' if g.fast else 'blkid -s TYPE -o value /dev/research/data')
            mount=g.t.node(h,'findmnt -rn -S /dev/research/data')
            persistent=g.t.node(h,'findmnt --fstab --evaluate -rn -S /dev/research/data')
            msg=size==600 or g.message(h,'Could not create logical volume of that size')
            g.state_check(h+'.volume',h+f' data={size} MiB、ext4、未挂载及错误分支',15,valid and fs.out.strip()=='ext4' and mount.rc==1 and persistent.rc==1 and msg,{'lv':data,'filesystem':fs.out.strip(),'mount':mount.out,'fstab':persistent.out,'fallback_message':msg},'lvs bytes; blkid; findmnt runtime/fstab; host-specific events')

MANAGED={8:apache,10:lvm,13:issue}

def controller(g):
    f=CONTROLLER.get(g.q['id'])
    if f is None:raise RuntimeError('控制节点评分尚未接入')
    f(g)
CONTROLLER={}

def repos(g):
    for h in NODES:
        found=g.obs[h]['repos'];ok=True
        for name,word,folder in [('rh294_BASE','base','BaseOS'),('rh294_STREAM','stream','AppStream')]:
            matches=[r for r in found if r.get('id')==name]
            good=any(r.get('name')=='rh294 '+word+' software' and r.get('baseurl','').rstrip('/')=='http://content.example.com/rhel9.0/x86_64/dvd/'+folder and r.get('enabled','1').lower() in ('1','yes','true') and r.get('gpgcheck','0').lower() in ('1','yes','true') and r.get('gpgkey')=='http://content.example.com/rhel9.0/x86_64/dvd/RPM-GPG-KEY-redhat-release' for r in matches)
            ok=ok and len(matches)==1 and good
        g.state_check(h+'.repos',h+' 两个存储库的全部要求',14,ok,found,'parse every /etc/yum.repos.d/*.repo')
MANAGED[2]=repos

def packages(g):
    for h in ('servera','serverb','serverc','serverd'):
        r=g.t.node(h,'rpm -q php mariadb')
        g.state_check(h+'.packages',h+' php/mariadb 已安装',10,r.rc==0,r.out,'rpm -q php mariadb')
    if g.fast:
        g.add('development-tools','dev 安装 Development Tools 组',15,None,{},'dnf group list')
        g.add('latest','dev 所有包为仓库可用最新版本',15,None,{},'dnf check-update')
        return
    r=g.t.node('servera','LC_ALL=C dnf -q group list --installed',timeout=180)
    g.state_check('development-tools','dev 安装 Development Tools 组',15,r.rc==0 and 'Development Tools' in r.out,r.out,'dnf group list --installed')
    r=g.t.node('servera','dnf -q check-update',timeout=300)
    g.state_check('latest','dev 所有包为仓库可用最新版本',15,r.rc==0,{'rc':r.rc,'updates':r.out[-3000:]},'dnf check-update (0=no update,100=updates,other=error)')
MANAGED[3]=packages

def timesync(g):
    installed=g.t.ws('rpm -q rhel-system-roles')
    g.state_check('role-package','控制节点已安装 RHEL 系统角色软件包',5,installed.rc==0,installed.out,'rpm -q rhel-system-roles on workstation')
    role=all(g.has_event(role='timesync',host=h) for h in NODES)
    g.state_check('role','所有节点实际使用 timesync 系统角色',15,role,sorted({e['role'] for e in g.events if e['role']}),'Ansible role events')
    for h in NODES:
        conf=(g.file(h,'/etc/chrony.conf').get('text') or '')
        selected=any(re.match(r'^\s*(server|pool|peer)\s+classroom\.example\.com(?:\s|$)',l) for l in conf.splitlines())
        g.state_check(h+'.ntp',h+' 活动 NTP 提供程序使用 classroom.example.com',10,selected and g.out(h,'chrony')=='active',{'config':conf,'service':g.out(h,'chrony'),'sources':g.out(h,'ntp')},'chrony configuration + active service')
MANAGED[4]=timesync

def selinux(g):
    installed=g.t.ws('rpm -q rhel-system-roles')
    g.state_check('role-package','控制节点已安装 RHEL 系统角色软件包',5,installed.rc==0,installed.out,'rpm -q rhel-system-roles on workstation')
    g.state_check('role','所有节点实际使用 SELinux 系统角色',15,all(g.has_event(role='selinux',host=h) for h in NODES),sorted({e['role'] for e in g.events if e['role']}),'Ansible role events')
    for h in NODES:
        conf=(g.file(h,'/etc/selinux/config').get('text') or '')
        ok=g.out(h,'selinux')=='Enforcing' and bool(re.search(r'''^\s*SELINUX\s*=\s*["']?enforcing["']?\s*(?:#.*)?$''',conf,re.M))
        g.state_check(h+'.enforcing',h+' 运行中及持久状态 enforcing',10,ok,{'runtime':g.out(h,'selinux'),'config':conf},'getenforce + /etc/selinux/config')
MANAGED[5]=selinux

def partition(g):
    h='servera';block=json.loads(g.out(h,'block'))
    disks={d['name']:d for d in block['blockdevices']}
    if 'vdd' in disks and not g.fast:raise RuntimeError('基线出现 vdd，题面双盘共用挂载点歧义，停止评分')
    parts=disks.get('vdb',{}).get('children',[])
    part=next((p for p in parts if p['name']=='vdb1'),{})
    expected=1500 if disks.get('vdb',{}).get('size',0)>=1501*1024**2 else 800
    g.state_check('partition','vdb1 容量符合成功/回退场景',25,abs(part.get('size',0)-expected*1024**2)<=2*1024**2,part,'lsblk bytes; tolerance 2 MiB alignment')
    g.state_check('filesystem','分区为 ext4',10,part.get('fstype')=='ext4',part,'lsblk FSTYPE')
    mount=g.t.node(h,'findmnt -rn -o SOURCE,FSTYPE /mnt/fs01')
    persistent=g.t.node(h,'findmnt --fstab --evaluate -rn -o SOURCE,FSTYPE /mnt/fs01')
    g.state_check('mount','/mnt/fs01 挂载正确并持久化',15,mount.rc==0 and '/dev/vdb1 ext4' in mount.out and '/dev/vdb1 ext4' in persistent.out,{'runtime':mount.out,'fstab':persistent.out},'findmnt runtime + evaluated fstab')
    g.state_check('missing-vdd','输出 vdd 不存在提示',10,g.message(h,'disk /dev/vdd does not exist'),{'message_observed':g.message(h,'disk /dev/vdd does not exist')},'host-specific debug event')
    g.state_check('fallback','容量不足分支提示',10,expected==1500 or g.message(h,'Could not create partition of that size'),{'fallback_required':expected==800,'message_observed':g.message(h,'Could not create partition of that size')},'host-specific debug event')
MANAGED[11]=partition

def hosts(g):
    text=(g.file('servera','/etc/myhosts').get('text') or '');parsed={}
    for line in text.splitlines():
        tokens=line.split('#',1)[0].split()
        if len(tokens)>=2:parsed[tokens[0]]=set(tokens[1:])
    g.state_check('template','使用 hosts.j2 模板生成 /etc/myhosts',15,g.has_event('template',host='servera',dest='/etc/myhosts',src='hosts.j2'),{'events':[e for e in g.events if e['action'].endswith('template')]},'template execution event including source')
    localhost={'127.0.0.1':{'localhost','localhost.localdomain','localhost4','localhost4.localdomain4'},'::1':{'localhost','localhost.localdomain','localhost6','localhost6.localdomain6'}}
    g.state_check('loopback','IPv4/IPv6 localhost 行',5,all(names<=parsed.get(ip,set()) for ip,names in localhost.items()),text,'parse /etc/myhosts')
    for h,i in zip(NODES,[10,11,12,13,254]):
        ip=('172.25.254.' if g.profile=='pdf' and h!='bastion' else '172.25.250.')+str(i)
        expect={h,h+'.lab.example.com'}
        g.state_check(h+'.host',h+' 地址与两个名称',10,expect<=parsed.get(ip,set()),{'expected_ip':ip,'actual_names':sorted(parsed.get(ip,set())),'profile':g.profile},'parse /etc/myhosts, order independent')
MANAGED[12]=hosts

def webcontent(g):
    d=g.file('servera','/webdev');link=g.file('servera','/var/www/html/webdev');page=g.file('servera','/webdev/index.html')
    g.state_check('directory','/webdev 目录组 devops、权限 2775',20,d.get('kind')=='directory' and d.get('group')=='devops' and d.get('mode')=='0o2775',d,'lstat + group lookup')
    resolved=g.t.node('servera','readlink -f /var/www/html/webdev')
    g.state_check('symlink','Web 路径符号链接到 /webdev',15,link.get('link') is not None and resolved.out.strip()=='/webdev',link,'readlink -f /var/www/html/webdev (absolute or relative link)')
    g.state_check('content','index.html 为单行 Development',15,page.get('text') in ('Development','Development\n'),page,'read /webdev/index.html')
    r=g.t.ws('curl -fsS --max-time 10 http://servera/webdev/')
    g.state_check('http','从控制节点通过 HTTP 访问目录',20,r.rc==0 and r.out.strip()=='Development',{'rc':r.rc,'actual':r.out},'curl workstation -> servera/webdev/')
MANAGED[14]=webcontent

def hwreport(g):
    g.state_check('download','从指定 URL 获取报告模板',10,all(any(e['host']==h and e['status']=='ok' and e.get('url')=='http://172.25.254.254/content/hwreport.empty' for e in g.events) for h in NODES),[e for e in g.events if e.get('url')],'download execution evidence')
    for h in NODES:
        text=(g.file(h,'/root/hwreport.txt').get('text') or '');values={}
        for line in text.splitlines():
            if '=' in line:
                k,v=line.split('=',1);values[k.strip()]=v.strip()
        blocks=json.loads(g.out(h,'block'))['blockdevices'];sizes={d['name']:d['size'] for d in blocks}
        def eqsize(value,size):
            if size is None:return value=='NONE'
            m=re.fullmatch(r'([\d.]+)\s*([KMGT]?i?B)',value or '',re.I)
            if not m:return False
            unit=m[2].upper().replace('I','');factor={'B':1,'KB':1024,'MB':1024**2,'GB':1024**3,'TB':1024**4}[unit]
            return abs(float(m[1])*factor-size)<=max(factor*.011,1024)
        ok=values.get('hostname')==h and values.get('memory')==g.out(h,'memory') and values.get('bios_version')==g.out(h,'bios') and eqsize(values.get('vda_size'),sizes.get('vda')) and eqsize(values.get('vdb_size'),sizes.get('vdb'))
        g.state_check(h+'.hardware',h+' 主机名/内存/BIOS/磁盘报告',12,ok,{'actual':values,'expected':{'hostname':h,'memory':g.out(h,'memory'),'bios':g.out(h,'bios'),'disk_bytes':sizes}},'hardware observations vs key=value report')
MANAGED[15]=hwreport

def cron_minutes(expression):
    """Expand the standard minute field, including lists, ranges and steps."""
    result=set()
    try:
        for token in expression.split(','):
            parts=token.split('/')
            if len(parts)>2:return set()
            span=parts[0];step=int(parts[1]) if len(parts)==2 else 1
            if step<1:return set()
            if span=='*':lo,hi=0,59
            elif '-' in span:lo,hi=map(int,span.split('-'))
            else:lo=hi=int(span)
            if not 0<=lo<=hi<=59:return set()
            result.update(range(lo,hi+1,step))
    except (ValueError,TypeError):return set()
    return result

def cron(g):
    raw=g.out('servera','cron');lines=[l.split() for l in raw.splitlines() if l.strip() and not l.lstrip().startswith('#')]
    jobs=[l for l in lines if len(l)>=7 and ' '.join(l[5:])=='echo hello']
    g.state_check('user','natasha 存在',10,g.t.node('servera','id natasha').rc==0,'检查用户 natasha','id natasha')
    g.state_check('command','natasha 的任务命令为 echo hello',25,len(jobs)>0,raw,'crontab -l -u natasha')
    g.state_check('schedule','每两分钟执行，其他时间字段无限制',35,any(cron_minutes(l[0])==set(range(0,60,2)) and l[1:5]==['*']*4 for l in jobs),raw,'semantic cron schedule check')
MANAGED[19]=cron

def galaxy_use(g):
    g.state_check('balancer-role','在 bastion 实际使用 balancer 角色',10,g.has_event(role='balancer',host='bastion'),[e for e in g.events if e['host']=='bastion' and e['role']],'role execution events')
    g.state_check('phpinfo-role','在两个 webservers 实际使用 phpinfo 角色',10,all(g.has_event(role='phpinfo',host=h) for h in ('serverc','serverd')),sorted({(e['host'],e['role']) for e in g.events if e['role']}),'role execution events')
    pages=[]
    for i in range(6):
        r=g.t.ws('curl -fsS --max-time 10 http://bastion/')
        pages.append(r.out.strip() if r.rc==0 else 'HTTP_ERROR')
    expect={f'Welcome to {h}.lab.example.com on 172.25.250.{ip}' for h,ip in [('serverc',12),('serverd',13)]}
    g.state_check('balance','反复访问可得到两个后端正确页面',20,expect<=set(pages) and set(pages)<=expect,pages,'six independent HTTP requests to bastion')
    for h in ('serverc','serverd'):
        r=g.t.ws('curl -fsS --max-time 10 http://'+h+'/hello.php')
        text=re.sub('<[^>]+>',' ',r.out)
        correct=f'Hello PHP World from {h}.lab.example.com' in text
        g.state_check(h+'.php',h+' PHP 页面及配置信息',15,r.rc==0 and correct and 'PHP Version' in text,{'greeting_present':correct,'php_details':'PHP Version' in text,'body_excerpt':text[:240]},'HTTP greeting and PHP Version')
MANAGED[9]=galaxy_use

def users(g):
    from .secrets import secrets
    s=secrets(g.e.config)
    # Read trusted list on the controller and parse with installed PyYAML.
    r=g.t.ws("curl -fsS http://172.25.254.254/content/user_list.yml | python3 -B -c 'import yaml,json,sys; print(json.dumps(yaml.safe_load(sys.stdin)))'")
    source=json.loads(r.require())
    r=g.command("python3 -B -c 'import yaml,json; print(json.dumps(yaml.safe_load(open(\"user_list.yml\"))))'")
    submitted=json.loads(r.out) if r.rc==0 else None
    g.state_check('list','提交的用户列表与给定资源一致',10,submitted==source,{'matches':submitted==source,'source_user_count':len(source.get('users',[]))},'semantic YAML comparison to supplied list')
    code='''import json,sys,pwd,grp,crypt,spwd
p=json.load(sys.stdin); out=[]
for u in p['users']:
 expected=u.get('job')==p['job']; name=u['name']
 try:
  account=pwd.getpwnam(name); actual=spwd.getspnam(name).sp_pwdp
  groups=[grp.getgrgid(x).gr_name for x in __import__('os').getgrouplist(name,account.pw_gid)]
  ok=expected and actual.startswith('$6$') and crypt.crypt(p['password'],actual)==actual and p['group'] in groups
  out.append(dict(name=name,expected=expected,exists=True,sha512=actual.startswith('$6$'),password_matches=crypt.crypt(p['password'],actual)==actual,groups=groups,passed=ok if expected else False))
 except KeyError:out.append(dict(name=name,expected=expected,exists=False,passed=not expected))
print(json.dumps(out))'''
    for h in g.q['nodes']:
        dev=h in ('servera','serverb')
        payload=dict(users=source['users'],job='developer' if dev else 'manager',group='devops' if dev else 'opsmgr',password=s['developer' if dev else 'manager'])
        rows=json.loads(g.t.node(h,'python3 -B -c '+shlex.quote(code),json.dumps(payload).encode()).require())
        g.state_check(h+'.users',h+' 用户分配、SHA512 密码及附加组',15,all(x['passed'] for x in rows),rows,'getpwnam/getspnam + crypt verification (hash/password never logged)')
MANAGED[17]=users

def configured_paths(text,key):
    for line in text.splitlines():
        if line.startswith(key+'('):
            try:
                value=ast.literal_eval(line.split('=',1)[1].strip())
                return value if isinstance(value,list) else [value]
            except (ValueError,SyntaxError,IndexError):return []
    return []

def config(g):
    r=g.command('ansible-inventory --list')
    try:inv=json.loads(r.out)
    except ValueError:inv={}
    groups={'dev':['servera'],'test':['serverb'],'prod':['serverc','serverd'],'balancers':['bastion']}
    for name,members in groups.items():
        actual=inv.get(name,{}).get('hosts',[])
        g.add('group.'+name,name+' 组成员',10,set(actual)==set(members),actual,'ansible-inventory --list')
    children=inv.get('webservers',{}).get('children',[])
    g.add('parent','prod 是 webservers 子组',10,'prod' in children,children,'ansible-inventory children')
    r=g.command('ansible-config dump --only-changed')
    text=r.out
    for key,expected in [('DEFAULT_HOST_LIST',BASE+'/inventory'),('DEFAULT_ROLES_PATH',BASE+'/roles'),('COLLECTIONS_PATHS',BASE+'/mycollections')]:
        lines=[l for l in text.splitlines() if l.startswith(key+'(')]
        g.add(key,key+' 有效配置',10,expected in configured_paths(text,key),lines,'ansible-config dump --only-changed, exact path membership')
    r=g.t.ws('rpm -q ansible-core ansible-navigator')
    g.add('software','所需 Ansible 软件包已安装',10,r.rc==0,r.out,'rpm -q ansible-core ansible-navigator')
CONTROLLER[1]=config

def install_roles(g):
    if g.fast:
        for id,desc in [('requirements','requirements.yml 使用指定 URL 并能在空目录安装'),('balancer.installed','balancer 安装位置与角色文件完整'),('phpinfo.installed','phpinfo 安装位置与角色文件完整')]:
            g.add(id,desc,30,None,{},'requires fresh Galaxy installation')
        return
    # Requirements must work in an empty target, not merely point at existing roles.
    import uuid
    tmp='/tmp/rhce-galaxy-'+uuid.uuid4().hex
    code='''import json,yaml
try:
 data=yaml.safe_load(open('roles/requirements.yml'))
 if isinstance(data,dict):data=data.get('roles',[])
 expected={'balancer':'http://classroom.example.com/content/haproxy.tar.gz','phpinfo':'http://classroom.example.com/content/phpinfo.tar.gz'}
 print(json.dumps({'sources_match':isinstance(data,list) and all(any(isinstance(row,dict) and row.get('name')==name and row.get('src')==url for row in data) for name,url in expected.items())}))
except Exception:print(json.dumps({'sources_match':False}))'''
    source_result=g.command('python3 -B -c '+shlex.quote(code))
    sources=json.loads(source_result.require())
    r=g.command('ansible-galaxy role install -r roles/requirements.yml -p '+tmp)
    g.add('requirements','requirements.yml 使用指定 URL 并能在空目录安装',30,r.rc==0 and sources['sources_match'],dict(returncode=r.rc,**sources),'requirements source validation + ansible-galaxy fresh install')
    for role in ('balancer','phpinfo'):
        script='''import pathlib,json,hashlib,sys
original=pathlib.Path(sys.argv[1]); installed=pathlib.Path(sys.argv[2]); files=[p for p in original.rglob('*') if p.is_file() and '.galaxy_install_info' not in str(p)]
missing=[str(p.relative_to(original)) for p in files if not (installed/p.relative_to(original)).is_file()]
changed=[str(p.relative_to(original)) for p in files if (installed/p.relative_to(original)).is_file() and p.read_bytes()!=(installed/p.relative_to(original)).read_bytes()]
print(json.dumps(dict(reference_files=len(files),missing=missing,changed=changed,tasks=(installed/'tasks/main.yml').is_file())))'''
        r2=g.command('python3 -B -c '+shlex.quote(script)+' '+shlex.quote(tmp+'/'+role)+' '+shlex.quote('roles/'+role))
        try:e=json.loads(r2.out)
        except ValueError:e={}
        g.add(role+'.installed',role+' 安装位置与角色文件完整',30,r.rc==0 and e.get('reference_files',0)>0 and not e.get('missing') and not e.get('changed') and e.get('tasks'),e,'compare installed role files with Galaxy fresh install; no playbook YAML comparison')
CONTROLLER[6]=install_roles

def install_collections(g):
    script='''import pathlib,json,hashlib
out=[]
for ns,name,version in [('ansible','posix','1.5.1'),('community','general','6.3.0')]:
 p=pathlib.Path('mycollections/ansible_collections')/ns/name
 try:
  manifest=json.loads((p/'MANIFEST.json').read_text()); info=manifest['collection_info']; files=json.loads((p/'FILES.json').read_text())['files']; errors=[]; checked=0
  for f in files:
   if f.get('ftype')!='file':continue
   rel=pathlib.PurePosixPath(f['name'])
   if rel.is_absolute() or '..' in rel.parts:errors.append('unsafe path');continue
   fp=p/str(rel);checked+=1
   if not fp.is_file() or (f.get('chksum_sha256') and hashlib.sha256(fp.read_bytes()).hexdigest()!=f['chksum_sha256']):errors.append(str(rel))
  out.append(dict(name=ns+'.'+name,version=info.get('version'),passed=info.get('namespace')==ns and info.get('name')==name and info.get('version')==version and checked>0 and not errors,checked=checked,errors=errors[:20]))
 except Exception as e:out.append(dict(name=ns+'.'+name,passed=False,error=str(e)))
print(json.dumps(out))'''
    r=g.command('python3 -B -c '+shlex.quote(script));rows=json.loads(r.require())
    for row in rows:g.add(row['name'],row['name']+' 指定版本、路径及文件完整性',45,row['passed'],row,'MANIFEST + FILES SHA256 checks as devops')
CONTROLLER[7]=install_collections

def vault_create(g):
    from .secrets import secrets
    s=secrets(g.e.config)
    code='''import sys,json,pathlib,yaml
from ansible.parsing.vault import VaultLib,VaultSecret
p=json.load(sys.stdin);out={};raw=pathlib.Path('locker.yml').read_bytes() if pathlib.Path('locker.yml').exists() else b''
out['encrypted']=raw.startswith(b'$ANSIBLE_VAULT;')
try:
 obj=yaml.safe_load(VaultLib([('default',VaultSecret(p['vault'].encode()))]).decrypt(raw));out['variables']=isinstance(obj,dict) and obj.get('pw_developer')==p['developer'] and obj.get('pw_manager')==p['manager'];out['decrypts']=True
except Exception:out['variables']=False;out['decrypts']=False
out['secret_file']=pathlib.Path('secret.txt').is_file() and pathlib.Path('secret.txt').read_text().strip()==p['vault']
print(json.dumps(out))'''
    r=g.t.dev('python3 -B -c '+shlex.quote(code),json.dumps(s).encode());d=json.loads(r.require())
    for key,desc,w in [('encrypted','locker.yml 使用 Vault 加密',20),('decrypts','题目指定密码可解密',20),('variables','两个变量及值正确',30),('secret_file','secret.txt 内容正确',20)]:g.add(key,desc,w,d[key],{key:d[key]},'VaultLib decrypt and semantic YAML checks; sensitive values redacted')
CONTROLLER[16]=vault_create

def vault_rekey(g):
    from .secrets import secrets
    s=secrets(g.e.config)
    code='''import sys,json,pathlib,urllib.request,hashlib
from ansible.parsing.vault import VaultLib,VaultSecret
p=json.load(sys.stdin);out={};path=pathlib.Path('salaries.yml');raw=path.read_bytes() if path.exists() else b''
out['encrypted']=raw.startswith(b'$ANSIBLE_VAULT;')
def dec(data,key):return VaultLib([('default',VaultSecret(key.encode()))]).decrypt(data)
try:current=dec(raw,p['new']);out['new_key']=True
except Exception:current=None;out['new_key']=False
try:dec(raw,p['old']);out['old_rejected']=False
except Exception:out['old_rejected']=out['new_key']
try:original=urllib.request.urlopen('http://172.25.254.254/content/salaries.yml',timeout=15).read();plain=dec(original,p['old']);out['content_unchanged']=current==plain
except Exception:out['source_error']=True;out['content_unchanged']=False
print(json.dumps(out))'''
    r=g.t.dev('python3 -B -c '+shlex.quote(code),json.dumps(s).encode());d=json.loads(r.require())
    if d.get('source_error'):raise RuntimeError('原始 salaries.yml 不可读取/不能用题面旧密码解密，不能可靠评分')
    for key,desc,w in [('encrypted','库保持 Vault 加密',20),('new_key','新密码可解密',25),('old_rejected','旧密码不再可解密',15),('content_unchanged','明文内容与原库一致',30)]:g.add(key,desc,w,d[key],{key:d[key]},'VaultLib old/new key verification and plaintext equality, no plaintext logging')
CONTROLLER[18]=vault_rekey


def fast_config(g):
    # Inventory/config plugins may execute submitted code. Do not invoke them in fast mode.
    for name in ('dev','test','prod','balancers'):
        g.add('group.'+name,name+' 有效组成员',10,None,{'reason':'有效清单需运行 Ansible 插件；快速模式不执行'},'ansible-inventory')
    g.add('parent','prod 是 webservers 子组',10,None,{'reason':'未执行清单插件'},'ansible-inventory')
    for key in ('DEFAULT_HOST_LIST','DEFAULT_ROLES_PATH','COLLECTIONS_PATHS'):
        g.add(key,key+' 有效配置',10,None,{'reason':'未加载提交的 Ansible 配置'},'ansible-config')
    r=g.t.ws('rpm -q ansible-core ansible-navigator')
    g.add('software','所需 Ansible 软件包已安装',10,r.rc==0,r.out,'rpm -q ansible-core ansible-navigator')
