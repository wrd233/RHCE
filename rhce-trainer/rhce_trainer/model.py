import json
from pathlib import Path

ROOT=Path(__file__).parent
QUESTIONS=json.loads((ROOT/'questions.json').read_text()) if (ROOT/'questions.json').exists() else []

def question(n):
    for q in QUESTIONS:
        if q['id']==int(n):return q
    raise ValueError('题号应在 1–19 之间')

def dependency_order(n):
    ordered=[];active=set();visited=set()
    def visit(current):
        if current in active:raise ValueError('题目依赖存在循环')
        if current in visited:return
        active.add(current)
        for dependency in question(current)['dependencies']:visit(dependency)
        active.remove(current);visited.add(current);ordered.append(current)
    visit(n)
    return ordered[:-1]

def plan(n):
    q=question(n)
    return dict(q,prerequisite_order=dependency_order(n),
                reset_vm_scope=q['nodes'],
                grade_vm_scope=q.get('execution_nodes',q['nodes']),
                reset_effect='范围内 VM 的全部状态恢复命名基线；原现场保留恢复点，控制节点答案先备份',
                grade_effect='保存现场 → 基线 → 准备依赖 → 运行学生提交 → 逐项评分 → 恢复现场')

def checkpoint(id,description,weight,passed,evidence,check):
    return dict(id=id,description=description,weight=weight,check=check,status='UNVERIFIED' if passed is None else 'PASS' if passed else 'FAIL',passed=None if passed is None else bool(passed),evidence=evidence)

def report(q, checks, **extra):
    total=sum(c['weight'] for c in checks)
    if total!=100:raise ValueError(f'检查点权重不是 100: {total}')
    if extra.get('mode')=='fast':
        maximum=sum(c['weight'] for c in checks if c['passed'] is not None)
        earned=sum(c['weight'] for c in checks if c['passed'])
        return dict(question=q['id'],title=q['title'],score=earned,maximum=maximum,
                    percentage=round(100*earned/maximum,2) if maximum else None,
                    label='快速检查',notice='仅按可验证项目计算，与完整评分不可直接比较；不证明提交可重放。',
                    counts={status:sum(c['status']==status for c in checks) for status in ('PASS','FAIL','UNVERIFIED')},
                    checkpoints=checks,**extra)
    return dict(question=q['id'],title=q['title'],score=sum(c['weight'] for c in checks if c['passed']),maximum=100,checkpoints=checks,**extra)
