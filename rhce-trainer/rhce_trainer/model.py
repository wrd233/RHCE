import json
from pathlib import Path

ROOT=Path(__file__).parent
QUESTIONS=json.loads((ROOT/'questions.json').read_text()) if (ROOT/'questions.json').exists() else []

def question(n):
    for q in QUESTIONS:
        if q['id']==int(n):return q
    raise ValueError('题号应在 1–19 之间')

def checkpoint(id,description,weight,passed,evidence,check):
    return dict(id=id,description=description,weight=weight,check=check,status='PASS' if passed else 'FAIL',passed=bool(passed),evidence=evidence)

def report(q, checks, **extra):
    total=sum(c['weight'] for c in checks)
    if total!=100:raise ValueError(f'检查点权重不是 100: {total}')
    return dict(question=q['id'],title=q['title'],score=sum(c['weight'] for c in checks if c['passed']),maximum=100,checkpoints=checks,**extra)
