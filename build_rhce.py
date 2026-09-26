"""Build the study HTML from the chapter Markdown files.

Run with PYTHONPATH=/tmp/rhce_pydeps and the bundled Python. The original HTML
remains a layout/template and source archive; the chapter files own the prose.
"""
from pathlib import Path
import re
import sys

from bs4 import BeautifulSoup
from markdown import markdown
from markdownify import markdownify


ROOT = Path(__file__).parent
SOURCE = ROOT / "RHCE_深度讲义_课程化完整版.html"
OUTPUT = ROOT / "RHCE_深度讲义_课程化修订版.html"
CHAPTERS = ROOT / "RHCE_课程正文"


def tidy(s: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"


def import_original() -> None:
    """One-time extraction. Never run after editing chapter files."""
    CHAPTERS.mkdir(exist_ok=True)
    if list(CHAPTERS.glob("*.md")):
        raise RuntimeError("Chapter Markdown already exists; import would overwrite edited prose")
    doc = BeautifulSoup(SOURCE.read_text(), "html.parser")
    for number in range(1, 14):
        sec = doc.find(id=f"ch{number:02d}")
        title = sec.find("h2").get_text(" ", strip=True)
        intro = sec.find("div", class_="chapter-head").find("p").get_text(" ", strip=True)
        lecture = sec.find("div", class_="lecture")
        for model in lecture.find_all("div", class_="model"):
            title_node = model.find("div", class_="model-title")
            model_title = title_node.get_text(" ", strip=True) if title_node else "心智模型"
            flow = model.find("div", class_="flow")
            body = " → ".join(x.get_text(" ", strip=True) for x in flow.find_all("span")) if flow else model.get_text(" ", strip=True)
            replacement = doc.new_tag("p")
            replacement.string = f"{model_title}：{body}"
            model.replace_with(replacement)
        prose = markdownify(str(lecture), heading_style="ATX", bullets="-")
        exam = sec.find("div", class_="exam-box")
        exercise = sec.find("div", class_="exercise")
        text = f"# {title}\n\n{intro}\n\n{prose.strip()}\n\n<!-- EXAM -->\n\n"
        if exam:
            text += markdownify(str(exam), heading_style="ATX").strip()
        text += "\n\n<!-- EXERCISE -->\n\n"
        if exercise:
            # Keep disclosure interaction in the HTML while the answer also stays
            # readable as ordinary text in this Markdown source.
            text += str(exercise).replace('class="exercise"', 'class="exercise"')
        (CHAPTERS / f"{number:02d}-{title.replace('/', '／')}.md").write_text(tidy(text))
    print(f"Imported {len(list(CHAPTERS.glob('*.md')))} chapters")


def build() -> None:
    doc = BeautifulSoup(SOURCE.read_text(), "html.parser")
    for number in range(1, 14):
        matches = list(CHAPTERS.glob(f"{number:02d}-*.md"))
        if len(matches) != 1:
            raise RuntimeError(f"Chapter {number:02d}: expected one Markdown file, got {matches}")
        content = matches[0].read_text()
        if "<!-- EXAM -->" not in content or "<!-- EXERCISE -->" not in content:
            raise RuntimeError(f"Missing section marker in {matches[0]}")
        lesson, following = content.split("<!-- EXAM -->", 1)
        exam, exercise = following.split("<!-- EXERCISE -->", 1)
        sec = doc.find(id=f"ch{number:02d}")
        head = sec.find("div", class_="chapter-head")
        h1_match = re.search(r"^# (.+)\n", lesson)
        if not h1_match:
            raise RuntimeError(f"Missing chapter title in {matches[0]}")
        head.find("h2").string = h1_match.group(1)
        intro, lesson = lesson[h1_match.end():].strip().split("\n\n", 1)
        head.find("p").string = intro.strip()
        for old in list(sec.children):
            if getattr(old, "get", None) and old.get("class") and any(c in old.get("class") for c in ("lecture", "exam-box", "exercise")):
                old.decompose()
        notes = sec.find("details", class_="raw-notes")
        for cls, src in (("lecture", lesson), ("exam-box", exam), ("exercise", exercise)):
            if not src.strip():
                continue
            wrapper = doc.new_tag("div", attrs={"class": cls})
            rendered = markdown(src.strip(), extensions=["fenced_code", "tables", "md_in_html"])
            fragment = BeautifulSoup(rendered, "html.parser")
            if cls == "exercise":
                outer = fragment.find("div", class_="exercise")
                if outer:
                    outer.unwrap()
            for child in list(fragment.contents):
                wrapper.append(child)
            if cls == "exercise":
                note_label = doc.new_tag("label", attrs={"class": "note-label", "for": f"note-{number:02d}"})
                note_label.string = "先写下我的判断（保存在本机）"
                note_field = doc.new_tag("textarea", id=f"note-{number:02d}", attrs={"data-note": f"{number:02d}", "rows": "3", "placeholder": "我会先检查……"})
                wrapper.append(note_label)
                wrapper.append(note_field)
            notes.insert_before(wrapper)
    hero = doc.find("header", class_="hero")
    hero.find("h1").string = "从问题出发，把 Ansible 学到能够独立完成任务"
    hero.find("p").string = "我会从一个具体问题开始，带你看清对象、写出自动化、核对最终状态。13 份课程材料里的知识与例子会直接进入正文；每章再把它们接到这套 19 题模拟练习上。你可以把此页作为主要学习入口，按章节阅读，也可以带着题目查找。"
    hero.find("div", class_="meta").find_all("span")[1].string = "课程知识与例子进入正文"
    doc.title.string = "RHCE Ansible 课程讲解｜从原理到模拟题复现"
    aside = doc.find("aside")
    aside.find("div", class_="logo").contents[0].replace_with("RHCE Ansible 课程")
    aside.find("nav").find("a", href="#start").find("span").next_sibling.replace_with("学习路线")
    aside.find("nav").find("a", href="#exam").find("span").next_sibling.replace_with("模拟题与官方目标")
    aside.find("nav").find("a", href="#manual").find("span").next_sibling.replace_with("查文档与验收")
    aside.find("button", id="sourceToggle").string = "隐藏 / 显示课堂记录附录"
    export_button = doc.new_tag("button", id="exportNotes", attrs={"type": "button"})
    export_button.string = "导出随堂思路"
    aside.find("button", id="resetProgress").insert_before(export_button)
    start = doc.find(id="start")
    start_source = (CHAPTERS / "00-学习路线.md").read_text()
    start_rendered = BeautifulSoup(markdown(start_source), "html.parser")
    start.find("h2").string = start_rendered.find("h1").get_text(strip=True)
    start_paragraphs = start_rendered.find_all("p", recursive=False)
    first_card = start.find("div", class_="card")
    first_card.find("p").replace_with(start_paragraphs[0])
    second_card = start.find_all("div", class_="card")[1]
    for index, paragraph in enumerate(start_paragraphs[1:]):
        (first_card if index < 2 else second_card).append(paragraph)
    start.find("div", class_="source-legend").find_all("span")[3].string = "附录：原始课堂记录"
    second_card.find("h3").string = "页面里的几种信息"
    start.find("p", style=True).string = "正文已经包含学习所需的讲解和例子。章节末尾的课堂记录只是核对来源的附录；模拟题对应的是这套练习材料，具体环境与正式考试可能不同。"
    for section_id, filename in (("exam", "14-模拟题与官方目标.md"), ("manual", "15-现场查文档与验收.md")):
        section = doc.find(id=section_id)
        src = (CHAPTERS / filename).read_text()
        rendered = BeautifulSoup(markdown(src, extensions=["fenced_code", "tables"]), "html.parser")
        title = rendered.find("h1")
        section.find("h2").string = title.get_text(strip=True)
        title.decompose()
        for old in list(section.children):
            if getattr(old, "get", None) and old.get("class") and "chapter-head" not in old.get("class"):
                old.decompose()
        body = doc.new_tag("div", attrs={"class": "lecture"})
        for child in list(rendered.contents):
            body.append(child)
        section.append(body)
    practice_source = (CHAPTERS / "16-十九题动手路线.md").read_text()
    practice_rendered = BeautifulSoup(markdown(practice_source, extensions=["fenced_code", "tables"]), "html.parser")
    practice_title = practice_rendered.find("h1").get_text(strip=True)
    practice_rendered.find("h1").decompose()
    practice = doc.new_tag("section", id="practice", attrs={"class": "chapter searchable"})
    practice_head = doc.new_tag("div", attrs={"class": "chapter-head"})
    practice_number = doc.new_tag("div", attrs={"class": "chapter-no"})
    practice_number.string = "19"
    practice_head.append(practice_number)
    practice_title_box = doc.new_tag("div")
    practice_h2 = doc.new_tag("h2")
    practice_h2.string = practice_title
    practice_title_box.append(practice_h2)
    practice_head.append(practice_title_box)
    practice.append(practice_head)
    practice_body = doc.new_tag("div", attrs={"class": "lecture"})
    for child in list(practice_rendered.contents):
        practice_body.append(child)
    practice.append(practice_body)
    doc.find(id="manual").insert_before(practice)
    practice_link = doc.new_tag("a", href="#practice")
    practice_link_span = doc.new_tag("span")
    practice_link_span.string = "19"
    practice_link.append(practice_link_span)
    practice_link.append("模拟题动手路线")
    aside.find("nav").find("a", href="#manual").insert_before(practice_link)
    doc.find("footer").string = "正文依据《RHCE课程笔记》的 13 份 PDF 与《RHCE9.0模拟题新版(答案)(1)》重写，并参考红帽公开的 EX294 考试目标。模拟题中的主机、路径和答案只对应这套练习；章节末的课堂记录用于核对细节。"
    # Retain the visual system and chapter navigation; repair the original JS.
    style = doc.find("style")
    style.string += "\n.lecture blockquote{background:var(--soft);border-left:3px solid #8a9990;margin:16px 0;padding:10px 14px;border-radius:7px}.lecture blockquote p{margin:0}.lecture pre code{color:inherit}.lecture ul{padding-left:1.35em}.lecture li{margin:3px 0}.lecture h3{margin-top:27px}#exam .lecture{overflow:auto}#exam table{min-width:980px}.note-label{display:block;margin:12px 0 4px;color:var(--muted);font-size:11px}.exercise textarea{display:block;width:100%;border:1px solid #d6d5cf;border-radius:6px;padding:9px;background:#fffefa;color:var(--ink);font:inherit;resize:vertical;min-height:65px}.mobile-nav{display:none}@media(max-width:1050px){.mobile-nav{display:flex;position:sticky;top:0;z-index:3;gap:8px;padding:8px 12px;background:#2c322f}.mobile-nav select,.mobile-nav input{min-width:0;flex:1;color:#f4f7f4;background:#3a423e;border:1px solid #606b63;border-radius:7px;padding:8px}.mobile-nav button{white-space:nowrap;color:#f4f7f4;background:#3a423e;border:1px solid #606b63;border-radius:7px;padding:8px}}\n"
    style.string += "\np code,li code,td code{overflow-wrap:anywhere;word-break:break-word}\n"
    mobile = doc.new_tag("div", attrs={"class": "mobile-nav"})
    selector = doc.new_tag("select", id="mobileSections", attrs={"aria-label": "选择章节"})
    for link in aside.find("nav").find_all("a"):
        option = doc.new_tag("option", value=link.get("href"))
        option.string = link.get_text(" ", strip=True)
        selector.append(option)
    mobile.append(selector)
    mobile_search = doc.new_tag("input", id="mobileSearch", attrs={"type": "search", "placeholder": "搜索章节", "aria-label": "搜索章节"})
    mobile.append(mobile_search)
    mobile_export = doc.new_tag("button", id="mobileExportNotes", attrs={"type": "button", "aria-label": "导出随堂思路"})
    mobile_export.string = "导出"
    mobile.append(mobile_export)
    doc.find("main").insert(0, mobile)
    doc.find("script").string = r"""
const key = 'rhce-expanded-progress-v1';
let saved = {};
try { saved = JSON.parse(localStorage.getItem(key) || '{}'); } catch (_) { saved = {}; }
const boxes = [...document.querySelectorAll('[data-progress]')];
function updateProgress() {
  const n = boxes.filter(box => box.checked).length;
  document.getElementById('progressText').textContent = `已学 ${n} / ${boxes.length}`;
  localStorage.setItem(key, JSON.stringify(Object.fromEntries(boxes.map(box => [box.dataset.progress, box.checked]))));
}
boxes.forEach(box => { box.checked = !!saved[box.dataset.progress]; box.addEventListener('change', updateProgress); });
updateProgress();
document.getElementById('resetProgress').addEventListener('click', () => {
  if (confirm('清空 13 章学习进度？')) { boxes.forEach(box => box.checked = false); updateProgress(); }
});
document.getElementById('sourceToggle').addEventListener('click', () => document.body.classList.toggle('dim-source'));
function searchSections(value) {
  const q = value.trim().toLowerCase();
  document.querySelectorAll('.searchable').forEach(section => {
    const visibleText = [...section.children].filter(child => !child.classList?.contains('raw-notes')).map(child => child.textContent || '').join(' ').toLowerCase();
    section.classList.toggle('hidden', !!q && !visibleText.includes(q));
  });
}
document.getElementById('search').addEventListener('input', e => searchSections(e.target.value));
document.getElementById('mobileSearch').addEventListener('input', e => searchSections(e.target.value));
document.getElementById('mobileSections').addEventListener('change', e => { location.hash = e.target.value; });
const noteKey = 'rhce-course-notes-v1';
let notes = {};
try { notes = JSON.parse(localStorage.getItem(noteKey) || '{}'); } catch (_) { notes = {}; }
document.querySelectorAll('[data-note]').forEach(area => {
  area.value = notes[area.dataset.note] || '';
  area.addEventListener('input', () => {
    notes[area.dataset.note] = area.value;
    localStorage.setItem(noteKey, JSON.stringify(notes));
  });
});
function exportNotes() {
  const content = [...document.querySelectorAll('[data-note]')].map(area => {
    const chapter = area.closest('.chapter');
    return `## ${chapter.querySelector('h2').textContent}\n\n${area.value || '（尚未填写）'}`;
  }).join('\n\n');
  const objectUrl = URL.createObjectURL(new Blob([`# RHCE 随堂思路\n\n${content}\n`], {type:'text/markdown;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = 'RHCE_随堂思路.md';
  link.click();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
document.getElementById('exportNotes').addEventListener('click', exportNotes);
document.getElementById('mobileExportNotes').addEventListener('click', exportNotes);
document.querySelectorAll('pre').forEach(pre => {
  const content = pre.querySelector('code')?.textContent ?? pre.textContent;
  const button = document.createElement('button');
  button.textContent = '复制';
  button.style = 'float:right;margin:-5px -5px 6px 10px;border:0;border-radius:5px;padding:4px 7px;background:#37403b;color:#dfe5e1;font-size:10px;cursor:pointer';
  button.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(content); button.textContent = '已复制'; }
    catch (_) { button.textContent = '复制失败'; }
    setTimeout(() => button.textContent = '复制', 1200);
  });
  pre.prepend(button);
});
"""
    OUTPUT.write_text(str(doc))
    print(f"Built {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("import", "build"):
        raise SystemExit("Use: python build_rhce.py import|build")
    (import_original if sys.argv[1] == "import" else build)()
