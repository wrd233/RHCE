import os,json,fcntl,time,uuid
from pathlib import Path
from contextlib import contextmanager

STATE=Path(os.environ.get('RHCE_STATE_DIR',str(Path.home()/'.local/state/rhce-trainer')))

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
