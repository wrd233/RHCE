"""Common preparation, sent over stdin; never touches the answer directory."""
import json
import os
import pathlib
import pwd
import shutil
import subprocess
import sys
import tempfile
import uuid

BACKUP=pathlib.Path('/root/.rhce-common-backups')

def run(args, **kwargs):
    return subprocess.run(args,check=True,capture_output=True,text=True,**kwargs).stdout

def backup(path):
    path=pathlib.Path(path)
    if path.is_symlink():raise RuntimeError('拒绝覆盖符号链接：'+str(path))
    if path.exists():
        dest=BACKUP/uuid.uuid4().hex/path.relative_to('/')
        dest.parent.mkdir(parents=True,mode=0o700)
        shutil.copy2(path,dest)

def write(path,text,mode=0o600,user='root'):
    path=pathlib.Path(path)
    account=pwd.getpwnam(user)
    if path.is_symlink():raise RuntimeError('拒绝覆盖符号链接：'+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists() or path.read_text()!=text:
        backup(path)
        fd,tmp=tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd,'w') as f:f.write(text)
            os.chmod(tmp,mode);os.chown(tmp,account.pw_uid,account.pw_gid)
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    os.chmod(path,mode);os.chown(path,account.pw_uid,account.pw_gid)

def dev(args,**kw):
    return run(['sudo','-iu','devops']+args,**kw)

def registry_ready(registries,registry):
    entry=registries.get(registry,{})
    insecure=entry.get('Insecure',entry.get('insecure',False)) or registry in registries.get('insecure',[])
    return registry in registries.get('search',[]) and insecure

def configure_podman(directory='/home/devops/.config/containers'):
    registry='utility.lab.example.com'
    directory=pathlib.Path(directory)
    account=pwd.getpwnam('devops')
    for parent in (directory.parent,directory):
        if not parent.exists():
            parent.mkdir();os.chown(parent,account.pw_uid,account.pw_gid)
    path=directory/'registries.conf'
    candidates=[
        'unqualified-search-registries = ["'+registry+'"]\n[[registry]]\nlocation = "'+registry+'"\ninsecure = true\n',
        '[registries.search]\nregistries = ["'+registry+'"]\n[registries.insecure]\nregistries = ["'+registry+'"]\n[registries.block]\nregistries = []\n',
    ]
    failures=[]
    for index,content in enumerate(candidates):
        fd,tmp=tempfile.mkstemp(dir=directory)
        try:
            with os.fdopen(fd,'w') as f:f.write(content)
            os.chown(tmp,account.pw_uid,account.pw_gid)
            raw=dev(['env','CONTAINERS_REGISTRIES_CONF='+tmp,'podman','info','--format','json'])
            registries=json.loads(raw).get('registries',{})
            if not registry_ready(registries,registry):
                raise RuntimeError('Podman 未确认搜索仓库和 insecure 配置生效')
            write(path,content,user='devops')
            effective=json.loads(dev(['podman','info','--format','json'])).get('registries',{})
            if not registry_ready(effective,registry):
                raise RuntimeError('默认配置路径未生效')
            print('Podman 配置已验证：'+('v2' if index==0 else 'v1'))
            return
        except (subprocess.CalledProcessError,RuntimeError,ValueError) as exc:
            failures.append(str(exc))
        finally:os.unlink(tmp)
    raise RuntimeError('当前 Podman 不接受候选配置：'+'; '.join(failures))

def main():
    action=sys.argv[1]
    if action=='key':
        account=pwd.getpwnam('devops')
        directory=pathlib.Path('/home/devops/.ssh')
        directory.mkdir(exist_ok=True,mode=0o700)
        os.chown(directory,account.pw_uid,account.pw_gid);os.chmod(directory,0o700)
        source=pathlib.Path('/root/.ssh/lab_rsa')
        # Validate before replacing the user's default key. Preserve the previous key.
        public=run(['ssh-keygen','-y','-P','','-f',str(source)]).strip()
        write(directory/'id_rsa',source.read_text(),user='devops')
        print(public)
    elif action=='account':
        try:account=pwd.getpwnam('devops')
        except KeyError:
            run(['useradd','-m','devops']);account=pwd.getpwnam('devops')
        if sys.argv[2]=='bastion':
            run(['chpasswd'],input='devops:redhat\n')
        directory=pathlib.Path(account.pw_dir)/'.ssh'
        directory.mkdir(exist_ok=True,mode=0o700)
        os.chown(directory,account.pw_uid,account.pw_gid);os.chmod(directory,0o700)
        public=sys.argv[3]
        path=directory/'authorized_keys'
        old=path.read_text() if path.exists() else ''
        if public not in old.splitlines():old=old.rstrip('\n')+'\n'+public+'\n'
        write(path,old,user='devops')
        sudo='devops ALL=(ALL) NOPASSWD: ALL\n'
        fd,tmp=tempfile.mkstemp()
        try:
            with os.fdopen(fd,'w') as f:f.write(sudo)
            run(['visudo','-cf',tmp])
            write('/etc/sudoers.d/rhce-trainer-devops',sudo,0o440)
            run(['visudo','-c'])
        finally:os.unlink(tmp)
    elif action=='repos':
        files=list(pathlib.Path('/etc/yum.repos.d').glob('*.repo'))
        # Each invocation gets a fresh archive: never overwrite an earlier repository.
        for path in files:
            if path.is_symlink() or not path.is_file():raise RuntimeError('非普通 repo 文件：'+str(path))
            backup(path)
        for path in files:path.unlink()
        print('已备份并清理 '+str(len(files))+' 个 repo；备份位于 '+str(BACKUP))
    elif action=='navigator':
        path='/home/devops/.ansible-navigator.yml'
        write(path,'ansible-navigator:\n  execution-environment:\n    image: utility.lab.example.com/ee-supported-rhel8:latest\n    pull:\n      policy: missing\n',user='devops')
        import yaml
        effective=yaml.safe_load(dev(['ansible-navigator','settings','--effective','--mode','stdout']))
        ee=effective.get('ansible-navigator',{}).get('execution-environment',{})
        if ee.get('image')!='utility.lab.example.com/ee-supported-rhel8:latest' or ee.get('pull',{}).get('policy')!='missing':
            raise RuntimeError('ansible-navigator 有效镜像或拉取策略不符；检查环境变量/配置覆盖')
    elif action=='podman':
        configure_podman()
    else:raise ValueError(action)

if __name__=='__main__':
    try:main()
    except subprocess.CalledProcessError as exc:
        # Do not include stdin (private key/password) in diagnostics.
        print('准备命令失败：'+str(exc.stderr or exc.stdout),file=sys.stderr);sys.exit(1)
