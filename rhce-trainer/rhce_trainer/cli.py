import argparse,json,sys,subprocess,contextlib
from .model import QUESTIONS,question,plan
from .engine import Engine
from .transport import VMS,NODES
from .grading import Grading
from . import state

def main():
 p=argparse.ArgumentParser(prog='rhce',description='RHCE 9 逐题练习与基线重放评分')
 sub=p.add_subparsers(dest='command',required=True)
 sub.add_parser('list');sub.add_parser('status');sub.add_parser('doctor');sub.add_parser('connect')
 sub.add_parser('init',help='首次从原始镜像建立五个受管节点的命名基线')
 s=sub.add_parser('adopt-baseline',help='迁移电脑后接管明确的已有基线；只读核对 VM 与全部磁盘');s.add_argument('label')
 for name in ('show','reset','grade','plan'):
  s=sub.add_parser(name);s.add_argument('number',type=int,choices=range(1,20))
  if name=='grade':
   s.add_argument('--verbose',action='store_true');s.add_argument('--hint',action='store_true');s.add_argument('--json',action='store_true');s.add_argument('--profile',choices=['pdf','live'],default='pdf')
  if name=='reset':s.add_argument('--dry-run',action='store_true')
 s=sub.add_parser('recover');s.add_argument('journal');s.add_argument('--with-answers',action='store_true',help='同时恢复归档答案；当前答案保留到 retired 目录')
 s=sub.add_parser('restore-lab',help='将五个受管节点恢复到命名基线，不重建 workstation');s.add_argument('--dry-run',action='store_true')
 a=p.parse_args()
 try:
  if a.command=='list':
   for q in QUESTIONS:print(f"{q['id']:2}  {q['title']}")
   return
  if a.command=='show':
   q=question(a.number);print(f"第{q['id']}题 {q['title']}\n\n{q['question']}\n\n工作目录：{q['base']}\n提交：{', '.join(q['artifacts'])}\n前置题：{q['dependencies']}");return
  if a.command=='plan' or (a.command=='reset' and a.dry_run):
   print(json.dumps(plan(a.number),ensure_ascii=False,indent=2));return
  e=Engine()
  if a.command=='connect':
   e.t.connect();print('SSH 已连接，密码未保存。');return
  if a.command=='doctor':
   identity=e.identity();print('入口身份与 VM 清单：正常')
   failed=[]
   for h in VMS:
    r=e.t.ws('hostname') if h=='workstation' else e.t.node(h,'hostname')
    correct=r.rc==0 and r.out.strip()==h+'.lab.example.com'
    print(('PASS' if correct else 'FAIL')+' '+h+' '+r.out.strip())
    if not correct:failed.append(h)
   print(e.t.dev('ansible --version').require())
   baseline=state.load('baseline.json')
   if baseline:
    if state.load('binding.json')!=identity:raise RuntimeError('本地身份绑定与当前环境不一致')
    for h in NODES:e.snapshot_disks(h,baseline['label'])
    print('基线：'+baseline['label']+'（全部磁盘保存点存在）')
   else:print('尚无本地基线；初次使用 init，迁移电脑使用 adopt-baseline <明确名称>')
   if failed:raise RuntimeError('SSH 不可达：'+', '.join(failed))
   return
  if a.command=='status':
   print(json.dumps({'current':state.load('current.json'),'baseline':state.load('baseline.json'),'journals':[{'id':x.stem,'phase':json.loads(x.read_text()).get('phase')} for x in sorted((state.STATE/'journals').glob('*.json'))]},ensure_ascii=False,indent=2));return
  if a.command=='restore-lab' and a.dry_run:
   print('将备份现场并恢复：'+', '.join(NODES));return
  with state.locked(), (contextlib.nullcontext() if a.command=='adopt-baseline' else e.t.lease()):
   if a.command=='init':e.init();print('命名基线已创建。')
   elif a.command=='adopt-baseline':e.adopt_baseline(a.label)
   elif a.command=='reset':e.reset(question(a.number))
   elif a.command=='recover':
    if '/' in a.journal or '..' in a.journal:raise ValueError('恢复点名称无效')
    j=state.load('journals/'+a.journal+'.json')
    if not j:raise ValueError('找不到恢复点')
    if j.get('runner'):
     cleanup=Grading(e,question(j['question']));cleanup.run_directory=j['runner'];cleanup.stop_runner()
    e.restore_scene(j)
    if a.with_answers:
     e.restore_answers(j.get('backup'));j['controller_restored']=True;state.save('journals/'+j['id']+'.json',j)
   elif a.command=='restore-lab':
    j=e.restore_lab();print('五个受管节点已恢复；控制节点答案保留。恢复点：'+j['id'])
   elif a.command=='grade':
    with contextlib.redirect_stdout(sys.stderr):
     r=Grading(e,question(a.number),a.profile).grade()
    path='reports/'+state.stamp()+f'-q{a.number}.json';state.save(path,r)
    if a.json:print(json.dumps(r,ensure_ascii=False,indent=2))
    else:
     print(f"\n第{r['question']}题 {r['title']}")
     for c in r['checkpoints']:
      print(f"[{c['status']}] {c['description']} ({c['weight']}分)")
      if a.verbose or not c['passed']:print('  '+json.dumps(c['evidence'],ensure_ascii=False))
     print(f"\n得分：{r['score']}/100\n报告：{state.STATE/path}")
     if a.hint:print('提示：根据失败项的实际结果检查 play 的目标组、依赖、模块参数及运行错误；不要求与参考 YAML 相同。')
    if r['score']<100:sys.exit(1)
 except (RuntimeError,ValueError,OSError,subprocess.SubprocessError) as exc:
  print('ERROR：'+str(exc),file=sys.stderr);sys.exit(2)
 except KeyboardInterrupt:
  print('操作中断。请查看 rhce status；必要时运行 rhce recover <恢复点>。',file=sys.stderr);sys.exit(130)
if __name__=='__main__':main()
