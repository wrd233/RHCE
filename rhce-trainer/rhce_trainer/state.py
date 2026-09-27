import os,json,fcntl,time,uuid,shutil
from pathlib import Path
from contextlib import contextmanager

ROOT=Path(os.environ.get('RHCE_STATE_DIR',str(Path.home()/'.local/state/rhce-trainer')))
STATE=ROOT
ACTIVE_CE=None
CE_PORTS={f'CE-{n:02d}':9004+n for n in range(1,6)}

def validate_ce(value):
    ce=str(value).upper()
    if ce not in CE_PORTS:raise ValueError('环境应为 CE-01 至 CE-05')
    return ce

def selected_ce():
    p=ROOT/'selected-ce.json'
    return validate_ce(json.loads(p.read_text())['ce']) if p.exists() else None

def active_ce():return ACTIVE_CE

def activate_ce(value):
    """Select isolated local state. Copy legacy CE-03 records once; keep originals."""
    global STATE,ACTIVE_CE
    ce=validate_ce(value)
    target=ROOT/'environments'/ce.lower()
    if ce=='CE-03' and not target.exists() and any((ROOT/x).exists() for x in ('binding.json','baseline.json','journals')):
        target.parent.mkdir(parents=True,exist_ok=True)
        with (ROOT/'operation.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('原 CE-03 操作正在运行，完成后再迁移本地状态')
            if not target.exists():
                staging=target.parent/('.migration-'+stamp())
                shutil.copytree(ROOT,staging,ignore=shutil.ignore_patterns('environments','selected-ce.json','operation.lock'))
                staging.replace(target)
    STATE=target;ACTIVE_CE=ce
    setup()
    return ce

def choose_ce(value):
    ce=activate_ce(value)
    ROOT.mkdir(parents=True,exist_ok=True);ROOT.chmod(0o700)
    p=ROOT/'selected-ce.json';tmp=p.with_suffix('.tmp')
    tmp.write_text(json.dumps({'ce':ce})+'\n');tmp.chmod(0o600);tmp.replace(p)
    return ce

def setup():
    STATE.mkdir(parents=True,exist_ok=True);STATE.chmod(0o700)
    for n in ('backups','reports','journals'):
        (STATE/n).mkdir(exist_ok=True);(STATE/n).chmod(0o700)

def load(name, default=None):
    p=STATE/name
    return json.loads(p.read_text()) if p.exists() else default

def save(name, data):
    setup();p=STATE/name;t=p.with_suffix('.tmp')
    t.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');t.chmod(0o600);t.replace(p)

def stamp():return time.strftime('%Y%m%d%H%M%S')+'-'+uuid.uuid4().hex[:6]

@contextmanager
def locked():
    setup()
    with (STATE/'operation.lock').open('a') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('另一个 rhce 操作正在执行；请等待它完成。')
        yield
