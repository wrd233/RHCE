"""Bounded playbook execution with a recoverable process-group record."""
import subprocess,os,sys,json,signal,pathlib
args=json.loads(sys.argv[1]);root=pathlib.Path(sys.argv[2]);pidfile=root/'process.json'
p=subprocess.Popen(args,start_new_session=True)
def starttime(pid):return pathlib.Path('/proc/'+str(pid)+'/stat').read_text().split()[21]
pidfile.write_text(json.dumps({'pid':p.pid,'starttime':starttime(p.pid)}))
def stop(*unused):
 try:os.killpg(p.pid,signal.SIGTERM)
 except ProcessLookupError:pass
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGHUP,stop)
try:
 try:rc=p.wait(timeout=900)
 except subprocess.TimeoutExpired:
  stop()
  try:p.wait(timeout=15)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  rc=124
finally:
 stop()
 pidfile.unlink(missing_ok=True)
sys.exit(rc)
