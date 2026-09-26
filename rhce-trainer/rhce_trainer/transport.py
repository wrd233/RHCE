"""No passwords, remote installation or f0 configuration writes."""
import subprocess, shlex, json, base64, time
from dataclasses import dataclass

NODES = ('servera','serverb','serverc','serverd','bastion')
VMS = ('workstation',) + NODES
INNER = ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null','-o','LogLevel=ERROR']

@dataclass
class Result:
    rc: int
    out: str
    err: str
    def require(self):
        if self.rc:
            raise RuntimeError(f'远程命令失败 (rc={self.rc}): {self.err[-1500:]} {self.out[-1500:]}')
        return self.out

class Transport:
    def __init__(self, config):
        self.config = config
        self.base = ['ssh','-o','BatchMode=yes','-S',config.get('socket','/tmp/rhce-trainer-ssh-%C'),'-o','ControlMaster=auto','-o','ControlPersist=2h','-o','ConnectTimeout=12','-o','StrictHostKeyChecking=accept-new','-p',str(config['port']),f"{config['user']}@{config['host']}"]
    def run(self, cmd, data=None, timeout=600):
        p = subprocess.run(self.base + [cmd], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return Result(p.returncode,p.stdout.decode(errors='replace'),p.stderr.decode(errors='replace'))
    def ws(self, cmd, data=None, timeout=600):
        return self.run(shlex.join(INNER+['root@workstation',cmd]),data,timeout)
    def node(self, host, cmd, data=None, timeout=600):
        if host not in NODES: raise ValueError('不属于练习受管节点')
        return self.ws(shlex.join(INNER+['root@'+host,cmd]), data, timeout)
    def dev(self, cmd, data=None, timeout=1200):
        return self.ws('sudo -u devops -H bash -c '+shlex.quote('cd /home/devops/ansible && '+cmd),data,timeout)
    def put(self, path, content, owner='devops', mode=0o600):
        # VM files only; path sent in stdin, never shell-interpolated.
        payload = {'path':path,'content':base64.b64encode(content.encode() if isinstance(content,str) else content).decode(),'owner':owner,'mode':mode}
        script = "import json,sys,pathlib,base64,os,pwd; d=json.load(sys.stdin); p=pathlib.Path(d['path']); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(base64.b64decode(d['content'])); u=pwd.getpwnam(d['owner']); os.chown(p,u.pw_uid,u.pw_gid); os.chmod(p,d['mode'])"
        self.ws('python3 -c '+shlex.quote(script),json.dumps(payload).encode()).require()
    def wait(self, host, seconds=240):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:
                r=self.ws('true',timeout=20) if host=='workstation' else self.node(host,'true',timeout=25)
                if r.rc==0:return
            except subprocess.TimeoutExpired:pass
            time.sleep(3)
        raise RuntimeError(host+' 未能在等待时间内恢复 SSH')
