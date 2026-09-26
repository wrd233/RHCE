"""Exam secrets are read from the user's PDF on demand; never persisted here."""
import re,subprocess,sys
from pathlib import Path

def secrets(config):
    pdf=Path(config['pdf'])
    if not pdf.is_file():raise RuntimeError('密码题需要本地原 PDF：'+str(pdf))
    candidates=[sys.executable,str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3')]
    text=None
    for exe in candidates:
        if not Path(exe).exists():continue
        p=subprocess.run([exe,'-c','import pdfplumber,sys; p=pdfplumber.open(sys.argv[1]); print("\\n".join(x.extract_text() or "" for x in p.pages[-3:]))',str(pdf)],capture_output=True,text=True)
        if p.returncode==0:text=p.stdout;break
    if text is None:raise RuntimeError('读取 PDF 需要 pdfplumber；请在运行 Python 环境安装该可选依赖')
    patterns={'developer':r'pw_developer，值为\s*(\S+)','manager':r'pw_manager，值为\s*(\S+)','vault':r'用于加密和解密该库的密码为\s*([A-Za-z0-9]+)','old':r'当前的库密码为\s*([A-Za-z0-9]+)','new':r'新的库密码为\s*([A-Za-z0-9]+)'}
    result={}
    for k,p in patterns.items():
        m=re.search(p,text)
        if not m:raise RuntimeError('PDF 中缺少密码题必要字段：'+k)
        result[k]=m.group(1)
    return result
