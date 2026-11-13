import argparse
import html
import json
import os
import re
import time
from pathlib import Path
from bs4 import BeautifulSoup
from groq import Groq

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "builder_state.json"
DOMAIN = "https://shorveernotes.website"
MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
REQUEST_DELAY = 30  # हर रिक्वेस्ट के बीच 30 सेकंड का गैप

SUBJECTS = {
    "mathematics": "Mathematics",
    "physics": "Physics",
    "chemistry": "Chemistry",
    "english": "English"
}

PROTECTED = {
    "index.html", "about.html", "about-notes.html", "exam-info.html",
    "privacy.html", "cookies.html", "ads.txt", "404.html",
    "terms.html", "disclaimer.html", "contact.html"
}

FOOTER_HTML = r"""<footer class="sn-clean-footer">
  <div class="container sn-f-wrap">
    <div class="sn-f-grid">
      <div class="sn-f-col brand-col">
        <a class="brand" href="index.html" style="margin-bottom: 12px; display: inline-flex;">
          <span class="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 64 64" fill="none">
              <path d="M44 20c-2.5-3.5-7-5-12-5-9 0-14 5.5-14 11.5 0 8 7.5 10 14 12 6.5 2 10 3.5 10 7.5 0 5-5 8-11 8-6.5 0-11-3-13.5-7.5l-4 4.5C17 56 23 60 31 60c11 0 18-6.5 18-15 0-9-8-11.5-14.5-13.5-6-2-9.5-3-9.5-6.5 0-4 4-6 9.5-6 4.5 0 8 1.5 10.5 4.5L44 20z" fill="#e8b64c"/>
            </svg>
          </span>
          <span class="brand-name">Shorveer<em>Notes</em></span>
        </a>
        <p class="sn-f-desc">A student-focused Class 12 Science learning platform with structured Physics, Chemistry, Mathematics and English resources.</p>
        <div class="sn-f-author">Created with pride by <strong>Jatin Sandilya</strong></div>
        <div style="margin-top: 14px;">
          <a class="btn btn-dark" style="min-height: 38px; padding: 0 14px; font-size: 13px;" href="https://www.youtube.com/@JSEDIZ" target="_blank" rel="noopener noreferrer">JS EDIZ on YouTube →</a>
        </div>
      </div>
      <div class="sn-f-col">
        <h3 class="sn-f-title">Subjects</h3>
        <ul class="sn-f-links">
          <li><a href="physics/index.html">Physics Hub</a></li>
          <li><a href="chemistry/index.html">Chemistry Hub</a></li>
          <li><a href="mathematics/index.html">Mathematics Hub</a></li>
          <li><a href="english/index.html">English Hub</a></li>
        </ul>
      </div>
      <div class="sn-f-col">
        <h3 class="sn-f-title">Resources</h3>
        <ul class="sn-f-links">
          <li><a href="exam-info.html">Exam Info</a></li>
          <li><a href="about-notes.html">About Notes</a></li>
          <li><a href="about.html">About Shorveer</a></li>
          <li><a href="cookies.html">Cookies &amp; Storage</a></li>
        </ul>
      </div>
    </div>
    <div class="sn-f-bottom">
      <p>&copy; <span id="year">2026</span> Shorveer Notes · All rights reserved.</p>
      <p>Built with pride in India 🇮🇳</p>
    </div>
  </div>
  <style>
    .sn-clean-footer { background: var(--paper-2); border-top: 1px solid var(--line); padding: 60px 0 30px; margin-top: 80px; color: var(--ink); }
    .sn-f-wrap { width: min(var(--max), calc(100% - 40px)); margin: 0 auto; }
    .sn-f-grid { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 40px; margin-bottom: 40px; }
    .sn-f-desc { font-size: 14.5px; line-height: 1.6; color: var(--muted); margin: 12px 0; max-width: 420px; }
    .sn-f-author { font-size: 13.5px; color: var(--muted); }
    .sn-f-author strong { color: var(--ink); }
    .sn-f-title { font-family: var(--font-body); font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; color: var(--rust); margin-bottom: 16px; }
    .sn-f-links { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
    .sn-f-links a { color: var(--ink-2); font-size: 14.5px; transition: color .2s ease; text-decoration: none; }
    .sn-f-links a:hover { color: var(--rust); text-decoration: underline; }
    .sn-f-bottom { border-top: 1px solid var(--line-soft); padding-top: 20px; display: flex; justify-content: space-between; gap: 16px; font-size: 13px; color: var(--muted); flex-wrap: wrap; }
    @media (max-width: 768px) { .sn-f-grid { grid-template-columns: 1fr; gap: 30px; } .sn-f-bottom { flex-direction: column; text-align: center; } }
  </style>
</footer>"""

CSS = r"""<style>
.svb{max-width:920px;margin:auto;padding:18px 16px 48px}
.svb-hero{padding:26px 0}.svb-hero h1{font-size:clamp(28px,5vw,44px);margin:8px 0}
.svb-meta{color:var(--muted);font-size:14px}.svb-nav{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
.svb-nav a,.svb-btn{padding:9px 14px;border:1px solid var(--line);border-radius:999px;text-decoration:none;cursor:pointer}
.svb-card{margin:18px 0;padding:22px;background:var(--card);border:1px solid var(--line);border-radius:var(--r-md);box-shadow:var(--shadow-sm)}
.svb-card h2{font-size:clamp(22px,3vw,30px);margin-bottom:12px}.svb-card h3{font-size:19px;margin:14px 0 8px}
.svb-card p,.svb-card li{line-height:1.8;color:var(--ink-2);overflow-wrap:anywhere}
.svb-card table{width:100%;border-collapse:collapse;margin:14px 0}
.svb-card th,.svb-card td{border:1px solid var(--line);padding:10px;text-align:left}
.svb-note{padding:14px;background:var(--paper-2);border-left:4px solid var(--gold-dark);border-radius:9px;margin-top:12px}
.svb-badge{display:inline-block;padding:3px 10px;font-size:12px;font-weight:700;background:var(--paper-2);border:1px solid var(--line);border-radius:6px;margin-bottom:8px}
.svb-quiz-q{padding:18px;margin:14px 0;border:1px solid var(--line);border-radius:10px}
.svb-opt{display:flex;gap:9px;padding:8px;cursor:pointer}.svb-result{padding:16px;margin:12px 0;border:1px solid var(--line);border-radius:10px}
mjx-container{max-width:100%}mjx-container[display=true]{overflow-x:auto;max-width:100%}
</style>"""

MATHJAX = r"""window.MathJax={tex:{inlineMath:[['$','$'],['\\(','\\)']],displayMath:[['$$','$$'],['\\[','\\]']]},options:{skipHtmlTags:['script','style','textarea','pre','code']}};"""

QUIZ_JS = r"""(()=>{const root=document.getElementById('svb-quiz');if(!root)return;
const data=JSON.parse(document.getElementById('svb-data').textContent),form=document.getElementById('svb-form');
const timer=document.getElementById('svb-timer'),result=document.getElementById('svb-result');
let left=Number(root.dataset.minutes)*60,started=false,done=false,iv;
const fmt=n=>String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');
function renderMath(){if(window.MathJax&&MathJax.typesetPromise)MathJax.typesetPromise([form,result]).catch(()=>{});}
function finish(){if(done)return;done=true;clearInterval(iv);let score=0;
data.forEach((q,i)=>{const picked=form.querySelector('input[name="q'+i+'"]:checked');
const ok=!!picked&&Number(picked.value)===q.answer;if(ok)score++;
const box=document.createElement('section');box.className='svb-result';
const h=document.createElement('h3');h.textContent='Q'+(i+1)+' — '+(ok?'Correct':'Review');
const p=document.createElement('p');p.textContent='Correct answer: '+q.options[q.answer];
const e=document.createElement('p');e.textContent=q.explain;box.append(h,p,e);result.append(box);});
const h=document.createElement('h2');h.textContent='Score: '+score+'/'+data.length+' ('+Math.round(score/data.length*100)+'%)';result.prepend(h);
Array.from(form.elements).forEach(x=>x.disabled=true);renderMath();}
document.getElementById('svb-start').addEventListener('click',()=>{if(started)return;started=true;form.hidden=false;
data.forEach((q,i)=>{const field=document.createElement('fieldset');field.className='svb-quiz-q';
const legend=document.createElement('legend');legend.textContent='Q'+(i+1)+'. '+q.q;field.append(legend);
q.options.forEach((o,j)=>{const label=document.createElement('label');label.className='svb-opt';
const input=document.createElement('input');input.type='radio';input.name='q'+i;input.value=j;
const span=document.createElement('span');span.textContent=o;label.append(input,span);field.append(label);});form.append(field);});
const submit=document.createElement('button');submit.type='button';submit.className='svb-btn';submit.textContent='Submit';submit.onclick=finish;form.append(submit);
renderMath();
iv=setInterval(()=>{left--;timer.textContent=fmt(left);if(left<=0)finish();},1000);});
})();"""


def esc(x):
    return html.escape(str(x), quote=True)


def slug(x):
    return re.sub(r"[^a-z0-9]+", "-", str(x).lower()).strip("-") or "topic"


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def analyze_website():
    """वेबसाइट के subject/index.html को स्कैन करके सही चैप्टर नंबर और नाम निकालता है"""
    targets = []
    for subj in SUBJECTS:
        folder = ROOT / subj
        idx = folder / "index.html"
        if not idx.exists():
            continue
        soup = BeautifulSoup(idx.read_text(encoding="utf-8", errors="replace"), "html.parser")
        seen_paths = set()
        auto_num = 1

        for a in soup.select("a[href]"):
            href = a["href"].strip()
            if href.startswith(("#", "http:", "https:", "mailto:", "tel:", "javascript:", "//")):
                continue
            target_file = href.split("?")[0].split("#")[0]
            if not target_file.lower().endswith(".html") or Path(target_file).name.lower() == "index.html":
                continue
            if re.search(r"mindmap|mcq|practice|flow|pyq|short|numerical|extract|character|visual-maps", target_file, re.I):
                continue

            dest = (folder / target_file).resolve()
            if ROOT.resolve() not in dest.parents:
                continue
            rel_path = dest.relative_to(ROOT.resolve()).as_posix()
            if rel_path in seen_paths or Path(rel_path).name.lower() in PROTECTED:
                continue
            seen_paths.add(rel_path)

            card = a.find_parent(class_=re.compile("card|item|chapter|unit|box", re.I))
            block_text = card.get_text(" ", strip=True) if card else a.get_text(" ", strip=True)

            num_match = re.search(r"(?:chapter|ch|unit|lesson)[\s\-:_.]*0*(\d+)", block_text, re.I)
            if not num_match:
                num_match = re.search(r"(?:chapter|ch|unit)[\s\-_]*0*(\d+)", Path(target_file).stem, re.I)
            ch_num = int(num_match.group(1)) if num_match else auto_num
            auto_num += 1

            heading = card.find(["h2", "h3", "h4"]) if card else None
            raw_title = heading.get_text(" ", strip=True) if heading else a.get_text(" ", strip=True)
            clean_title = re.sub(r"^(?:chapter|ch|unit|lesson)[\s\-:_.]*\d+[\s\-:_.]*", "", raw_title, flags=re.I)
            clean_title = re.sub(r"\b(open|read more|view notes|start|notes)\b", "", clean_title, flags=re.I).strip(" -–:|")
            if not clean_title:
                clean_title = Path(target_file).stem.replace("-", " ").title()

            targets.append({
                "subject": subj,
                "chapter_num": ch_num,
                "chapter": clean_title,
                "path": rel_path
            })
    return targets


class GroqBot:
    def __init__(self):
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY missing in GitHub Secrets / Environment!")
        self.client = Groq(api_key=key)
        self.last_call = 0.0

    def ask(self, subject, prompt):
        system = (
            f"You are an expert CBSE Class 12 {SUBJECTS[subject]} teacher for Shorveer Notes (by Jatin Sandilya). "
            "Write exhaustive, crystal-clear, exam-oriented content strictly following the latest CBSE Class 12 syllabus. "
            "Output ONLY valid JSON as requested."
        )
        for model in MODELS:
            for attempt in range(3):
                wait = REQUEST_DELAY - (time.time() - self.last_call)
                if wait > 0:
                    print(f"Waiting {wait:.1f}s before next API request...")
                    time.sleep(wait)
                try:
                    res = self.client.chat.completions.create(
                        model=model,
                        temperature=0.25,
                        max_completion_tokens=4096,
                        response_format={"type": "json_object"},
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    self.last_call = time.time()
                    raw = (res.choices[0].message.content or "").strip()
                    raw = re.sub(r"^```json\s*|\s*```$", "", raw, flags=re.I)
                    return json.loads(raw)
                except Exception as e:
                    self.last_call = time.time()
                    print(f"[{model}] Error (attempt {attempt+1}): {str(e)[:120]}")
                    time.sleep(15)
        raise RuntimeError("All Groq models failed after retries.")


def sanitize_html(raw):
    soup = BeautifulSoup(str(raw), "html.parser")
    allowed = {
        "h3", "h4", "p", "ul", "ol", "li", "strong", "b", "em", "i",
        "table", "thead", "tbody", "tr", "th", "td", "blockquote", "div", "span", "code", "sub", "sup", "br"
    }
    for tag in list(soup.find_all(True)):
        if tag.name not in allowed:
            tag.unwrap()
        else:
            tag.attrs = {}
    return str(soup)


def render_page(rel_path, title, ch_num, chapter, subject, badge, body, nav_links):
    template = ROOT / "index.html"
    soup = BeautifulSoup(template.read_text(encoding="utf-8"), "html.parser")
    main = soup.find("main")
    if main is None:
        raise RuntimeError("Template index.html must contain a <main> element. No files were changed.")

    for old_f in soup.find_all("footer"):
        old_f.decompose()
    new_f = BeautifulSoup(FOOTER_HTML, "html.parser").find("footer")
    if soup.body and new_f:
        soup.body.append(new_f)

    prefix = "../" * len(Path(rel_path).parent.parts)
    for tag in soup.find_all(["a", "link", "script", "img", "source"]):
        for attr in ("href", "src"):
            val = tag.get(attr)
            if val and not val.startswith(("http://", "https://", "//", "#", "mailto:", "tel:", "data:", "/")):
                tag[attr] = prefix + val

    main.clear()
    nav_html = "".join(f'<a class="svb-btn" href="{esc(href)}">{esc(lbl)}</a>' for href, lbl in nav_links)
    hero = (
        f'{CSS}<section class="svb"><header class="svb-hero">'
        f'<p class="svb-meta">Class 12 · {esc(SUBJECTS[subject])} · Chapter {ch_num} · {esc(badge)}</p>'
        f'<h1>{esc(chapter)}</h1>'
        f'<nav class="svb-nav">{nav_html}</nav></header>{body}</section>'
    )
    frag = BeautifulSoup(hero, "html.parser")
    for node in list(frag.contents):
        main.append(node.extract())

    head = soup.find("head")
    if head:
        desc_text = f"CBSE Class 12 {SUBJECTS[subject]} Chapter {ch_num} {chapter} - {badge} on Shorveer Notes."
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if not meta_desc:
            head.append(soup.new_tag("meta", attrs={"name": "description", "content": desc_text}))
        else:
            meta_desc["content"] = desc_text

        canonical = soup.find("link", attrs={"rel": "canonical"})
        canon_url = f"{DOMAIN}/{Path(rel_path).as_posix()}"
        if not canonical:
            head.append(soup.new_tag("link", attrs={"rel": "canonical", "href": canon_url}))
        else:
            canonical["href"] = canon_url

        if main.select_one(".mermaid") and not soup.find("script", src=re.compile("mermaid")):
            mermaid_cfg = soup.new_tag("script")
            mermaid_cfg.string = "document.addEventListener('DOMContentLoaded',()=>mermaid.initialize({startOnLoad:true, securityLevel:'strict', theme:'default'}));"
            mermaid_lib = soup.new_tag("script", src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js")
            mermaid_lib["defer"] = ""
            head.append(mermaid_lib)
            head.append(mermaid_cfg)

        if subject != "english" and not soup.find("script", src=re.compile("tex-chtml")):
            cfg = soup.new_tag("script")
            cfg.string = MATHJAX
            lib = soup.new_tag("script", src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js")
            lib["async"] = ""
            head.append(cfg)
            head.append(lib)

    if soup.title:
        soup.title.string = title

    out_file = ROOT / rel_path
    out_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_file.with_suffix(".tmp")
    tmp.write_text(str(soup), encoding="utf-8")
    tmp.replace(out_file)


def sub_path(base, suffix):
    p = Path(base)
    return p.with_name(f"{p.stem}-{suffix}.html").as_posix()


def build_english(bot, target, rec, state, force):
    ch_num, chapter, base = target["chapter_num"], target["chapter"], target["path"]
    p_notes = base
    p_chars = sub_path(base, "characters")
    p_extract = sub_path(base, "extracts")
    p_practice = sub_path(base, "practice")
    p_mcq = sub_path(base, "mcq")
    p_maps = sub_path(base, "visual-maps")

    nav = [
        (Path(p_chars).name, "Character Sketches"),
        (Path(p_extract).name, "Extract Questions"),
        (Path(p_practice).name, "Value & Long Q&A"),
        (Path(p_mcq).name, "MCQ Test"),
        (Path(p_maps).name, "Mind Map & Flowchart")
    ]

    if "summary" not in rec or force:
        res = bot.ask("english", f"""
        Class 12 English Chapter {ch_num}: "{chapter}".
        Return JSON: {{"sections": [{{"heading": "...", "html": "..."}}]}}
        Include: 1) Introduction & Author Background, 2) Detailed Scene-by-Scene / Stanza-by-Stanza Summary (exhaustive), 3) Central Theme & Message, 4) Literary Devices & Poetic/Prose Style, 5) Important Word Meanings & Phrases (HTML table).
        Use clean HTML tags (p, ul, li, strong, table, tr, th, td).
        """)
        rec["summary"] = res["sections"]
        save_state(state)

    toc = '<nav class="svb-nav">' + ''.join(f'<a href="#s-{slug(x["heading"])}">{esc(x["heading"])}</a>' for x in rec["summary"]) + '</nav>'
    body_notes = toc + ''.join(f'<section class="svb-card" id="s-{slug(x["heading"])}"><h2>{esc(x["heading"])}</h2>{sanitize_html(x["html"])}</section>' for x in rec["summary"])
    render_page(p_notes, f"Ch {ch_num}: {chapter} Summary | Shorveer Notes", ch_num, chapter, "english", "Detailed Summary & Analysis", body_notes, nav)

    if "characters" not in rec or force:
        res = bot.ask("english", f"""
        Class 12 English Chapter {ch_num}: "{chapter}".
        Return JSON: {{"characters": [{{"name": "...", "role": "...", "sketch_html": "..."}}]}}
        Provide deep, exam-ready character sketches of all major and minor characters (if it is a poem, analyze the Poet/Speaker and key figures mentioned). Include traits, textual evidence, and role in the plot.
        """)
        rec["characters"] = res["characters"]
        save_state(state)

    body_chars = ''.join(
        f'<section class="svb-card"><span class="svb-badge">{esc(c.get("role", "Character"))}</span><h2>{esc(c["name"])}</h2>{sanitize_html(c["sketch_html"])}</section>'
        for c in rec["characters"]
    )
    render_page(p_chars, f"Character Sketches · {chapter}", ch_num, chapter, "english", "Character Sketches", body_chars, [(Path(p_notes).name, "Back to Summary")])

    if "extracts" not in rec or force:
        res = bot.ask("english", f"""
        Class 12 English Chapter {ch_num}: "{chapter}".
        Return JSON: {{"extracts": [{{"passage": "...", "questions": [{{"q": "...", "ans": "..."}}]}}]}}
        Create 3 important CBSE board-style Reference-to-Context (Extract-Based) passages from this chapter, each with 4 sub-questions and exact answers.
        """)
        rec["extracts"] = res["extracts"]
        save_state(state)

    body_ext = ""
    for i, ext in enumerate(rec["extracts"], 1):
        qs_html = ''.join(f'<div class="svb-note"><p><strong>Q{j}. {esc(q["q"])}</strong></p><p>Ans: {sanitize_html(q["ans"])}</p></div>' for j, q in enumerate(ext["questions"], 1))
        body_ext += f'<section class="svb-card"><span class="svb-badge">Extract {i}</span><blockquote>{sanitize_html(ext["passage"])}</blockquote>{qs_html}</section>'
    render_page(p_extract, f"Extract Questions · {chapter}", ch_num, chapter, "english", "Extract-Based Questions (RTC)", body_ext, [(Path(p_notes).name, "Back to Summary")])

    if "practice" not in rec or force:
        res = bot.ask("english", f"""
        Class 12 English Chapter {ch_num}: "{chapter}".
        Return JSON: {{"items": [{{"type": "Short Answer / Long Answer / Value-Based Question", "question": "...", "answer": "..."}}]}}
        Provide 10 high-probability CBSE board questions: 4 Short Answer (40-50 words), 3 Long Answer (120-150 words), and 3 Value-Based / Extrapolation Questions with complete model answers.
        """)
        rec["practice"] = res["items"]
        save_state(state)

    body_prac = ''.join(
        f'<section class="svb-card"><span class="svb-badge">{esc(x.get("type", "Question"))}</span><h3>Q{i}. {esc(x["question"])}</h3><div class="svb-note"><strong>Model Answer:</strong>{sanitize_html(x["answer"])}</div></section>'
        for i, x in enumerate(rec["practice"], 1)
    )
    render_page(p_practice, f"Practice & Value Q&A · {chapter}", ch_num, chapter, "english", "Practice & Value-Based Questions", body_prac, [(Path(p_notes).name, "Back to Summary")])

    build_mcq(bot, "english", ch_num, chapter, p_mcq, p_notes, rec, state, force)
    build_visual_maps(bot, "english", ch_num, chapter, p_maps, p_notes, rec, state, force)


def build_science_math(bot, target, rec, state, force):
    subj, ch_num, chapter, base = target["subject"], target["chapter_num"], target["chapter"], target["path"]
    p_notes = base
    p_short = sub_path(base, "short-notes")
    p_num = sub_path(base, "numericals")
    p_pyq = sub_path(base, "pyq")
    p_mcq = sub_path(base, "mcq")
    p_maps = sub_path(base, "visual-maps")

    nav = [
        (Path(p_short).name, "Short Revision Notes"),
        (Path(p_num).name, "Solved Numericals"),
        (Path(p_pyq).name, "CBSE PYQ-Pattern Questions"),
        (Path(p_mcq).name, "MCQ Test"),
        (Path(p_maps).name, "Mind Map & Flowchart")
    ]

    if "topics" not in rec or force:
        res = bot.ask(subj, f"""
        CBSE Class 12 {SUBJECTS[subj]} Chapter {ch_num}: "{chapter}".
        Return JSON: {{"topics": ["Topic 1", "Topic 2", ...]}}
        List 8 to 12 sequential syllabus topics covering the entire chapter completely from basic definitions to advanced derivations/theorems.
        """)
        rec["topics"] = res["topics"][:12]
        save_state(state)

    notes_map = rec.setdefault("long_notes", {})
    for topic in rec["topics"]:
        if topic not in notes_map or force:
            res = bot.ask(subj, f"""
            CBSE Class 12 {SUBJECTS[subj]} Chapter {ch_num}: "{chapter}" — Topic: "{topic}".
            Return JSON: {{"html": "..."}}
            Write exhaustive, crystal-clear Long Detailed Notes (350-500 words). Include exact definitions, step-by-step mathematical derivations, laws/theorems, SI units, edge cases, and a solved example. Use LaTeX ($...$ and $$...$$) for all equations and clean HTML (p, ul, li, strong, table, tr, th, td).
            """)
            notes_map[topic] = sanitize_html(res["html"])
            save_state(state)

    toc = '<nav class="svb-nav">' + ''.join(f'<a href="#s-{slug(t)}">{esc(t)}</a>' for t in rec["topics"]) + '</nav>'
    body_notes = toc + ''.join(f'<section class="svb-card" id="s-{slug(t)}"><h2>{esc(t)}</h2>{notes_map[t]}</section>' for t in rec["topics"])
    render_page(p_notes, f"Ch {ch_num}: {chapter} Notes | Shorveer Notes", ch_num, chapter, subj, "Long Detailed Notes", body_notes, nav)

    if "short_notes" not in rec or force:
        res = bot.ask(subj, f"""
        CBSE Class 12 {SUBJECTS[subj]} Chapter {ch_num}: "{chapter}".
        Return JSON: {{"cards": [{{"title": "...", "html": "..."}}]}}
        Create crisp, high-yield Short Revision Notes for last-minute board exam revision: 1) All Important Formulas Table, 2) Key Definitions & Laws, 3) Important Graphs/Reactions/Theorems Summary, 4) Common Exam Mistakes to Avoid. Use LaTeX ($...$ / $$...$$).
        """)
        rec["short_notes"] = res["cards"]
        save_state(state)

    body_short = ''.join(f'<section class="svb-card"><h2>{esc(c["title"])}</h2>{sanitize_html(c["html"])}</section>' for c in rec["short_notes"])
    render_page(p_short, f"Short Notes · {chapter}", ch_num, chapter, subj, "Short Revision Notes & Formula Sheet", body_short, [(Path(p_notes).name, "Back to Detailed Notes")])

    if "numericals" not in rec or force:
        res = bot.ask(subj, f"""
        CBSE Class 12 {SUBJECTS[subj]} Chapter {ch_num}: "{chapter}".
        Return JSON: {{"problems": [{{"level": "NCERT Level / Board Standard / HOTS", "question": "...", "solution_html": "..."}}]}}
        Create 10 important solved numericals (or step-by-step proofs/conversions for Math/Organic Chem) covering every formula in the chapter. Show Given, Formula Used, Step-by-Step Calculation, and Final Answer with units using LaTeX ($...$ / $$...$$).
        """)
        rec["numericals"] = res["problems"]
        save_state(state)

    body_num = ''.join(
        f'<section class="svb-card"><span class="svb-badge">{esc(p.get("level", "Numerical"))}</span><h3>Problem {i}. {sanitize_html(p["question"])}</h3><div class="svb-note"><strong>Step-by-Step Solution:</strong>{sanitize_html(p["solution_html"])}</div></section>'
        for i, p in enumerate(rec["numericals"], 1)
    )
    render_page(p_num, f"Numericals · {chapter}", ch_num, chapter, subj, "Solved Numericals & Problems", body_num, [(Path(p_notes).name, "Back to Detailed Notes")])

    if "pyq" not in rec or force:
        res = bot.ask(subj, f"""
        CBSE Class 12 {SUBJECTS[subj]} Chapter {ch_num}: "{chapter}".
        Return JSON: {{"pyqs": [{{"marks": "2 Marks / 3 Marks / 5 Marks (Case Study / Long)", "tag": "Frequently Repeated Board Concept", "question": "...", "answer_html": "..."}}]}}
        Create 10 authentic CBSE Board PYQ-pattern subjective questions (covering 2-mark reasoning, 3-mark derivations/problems, and 5-mark long analytical questions) based on actual CBSE Class 12 board exam trends. Do not fabricate fake year numbers; label by marks and concept importance. Provide full marking-scheme answers with LaTeX ($...$ / $$...$$).
        """)
        rec["pyq"] = res["pyqs"]
        save_state(state)

    body_pyq = ''.join(
        f'<section class="svb-card"><span class="svb-badge">{esc(q.get("marks", "3 Marks"))} · {esc(q.get("tag", "Board Important"))}</span><h3>Q{i}. {sanitize_html(q["question"])}</h3><div class="svb-note"><strong>CBSE Marking Scheme Answer:</strong>{sanitize_html(q["answer_html"])}</div></section>'
        for i, q in enumerate(rec["pyq"], 1)
    )
    render_page(p_pyq, f"CBSE PYQ Bank · {chapter}", ch_num, chapter, subj, "CBSE Board PYQ-Pattern Questions", body_pyq, [(Path(p_notes).name, "Back to Detailed Notes")])

    build_mcq(bot, subj, ch_num, chapter, p_mcq, p_notes, rec, state, force)
    build_visual_maps(bot, subj, ch_num, chapter, p_maps, p_notes, rec, state, force)


def build_visual_maps(bot, subj, ch_num, chapter, p_maps, p_notes, rec, state, force):
    """Generate a Mermaid mind map and flowchart for a chapter."""
    if "visual_maps" not in rec or force:
        res = bot.ask(subj, f"""
        CBSE Class 12 {SUBJECTS[subj]} Chapter {ch_num}: "{chapter}".
        Create two accurate, compact visual learning diagrams based on the chapter.
        Return JSON only in this exact shape:
        {{"mindmap_mermaid":"mindmap\\n  root((Chapter))\\n    Topic\\n      Subtopic",
          "flowchart_mermaid":"flowchart TD\\n  A[Start] --> B[Concept]\\n  B --> C[Result]",
          "revision_points":["point 1","point 2"]}}
        Rules: Mermaid syntax only in diagram fields; no Markdown fences; use short plain labels without parentheses or quotes inside node text;
        avoid HTML; do not invent syllabus topics. For English, map plot/theme/characters;
        for Physics/Chemistry/Maths, map concepts, formulas, laws and relationships.
        """)
        mind = str(res.get("mindmap_mermaid", "")).strip()
        flow = str(res.get("flowchart_mermaid", "")).strip()
        if not mind.startswith("mindmap"):
            mind = "mindmap\n  root((" + chapter.replace("[", "").replace("]", "") + "))\n    Revise key concepts"
        if not (flow.startswith("flowchart") or flow.startswith("graph ")):
            flow = "flowchart TD\n  A[" + chapter.replace("[", "").replace("]", "") + "] --> B[Revise key concepts]"
        rec["visual_maps"] = {
            "mindmap": mind,
            "flowchart": flow,
            "revision_points": [str(x) for x in res.get("revision_points", [])[:12]]
        }
        save_state(state)

    maps = rec["visual_maps"]
    body = (
        '<section class="svb-card"><h2>Chapter Mind Map</h2>'
        '<pre class="mermaid">' + esc(maps["mindmap"]) + '</pre></section>'
        '<section class="svb-card"><h2>Concept Flowchart</h2>'
        '<pre class="mermaid">' + esc(maps["flowchart"]) + '</pre></section>'
    )
    if maps.get("revision_points"):
        body += '<section class="svb-card"><h2>Quick Revision Connections</h2><ul>' + ''.join(
            '<li>' + esc(x) + '</li>' for x in maps["revision_points"]
        ) + '</ul></section>'
    render_page(p_maps, f"Mind Map & Flowchart · {chapter}", ch_num, chapter, subj,
                "Visual Learning Maps", body, [(Path(p_notes).name, "Back to Chapter Notes")])


def build_mcq(bot, subj, ch_num, chapter, p_mcq, p_notes, rec, state, force):
    if "mcq" not in rec or force:
        res = bot.ask(subj, f"""
        CBSE Class 12 {SUBJECTS[subj]} Chapter {ch_num}: "{chapter}".
        Return JSON: {{"questions": [{{"q": "...", "options": ["A", "B", "C", "D"], "answer": 0, "explain": "..."}}]}}
        Create 12 high-quality CBSE board-level MCQs (including Assertion-Reason style). 'answer' must be integer 0, 1, 2, or 3. Use $...$ for inline math equations.
        """)
        qs = []
        for q in res.get("questions", []):
            if isinstance(q, dict) and isinstance(q.get("options"), list) and len(q["options"]) == 4 and isinstance(q.get("answer"), int) and 0 <= q["answer"] < 4:
                qs.append({"q": str(q["q"]), "options": [str(o) for o in q["options"]], "answer": q["answer"], "explain": str(q.get("explain", ""))})
        rec["mcq"] = qs[:12]
        save_state(state)

    payload = json.dumps(rec["mcq"], ensure_ascii=False).replace("</", "<\\/")
    body_mcq = (
        f'<div id="svb-quiz" data-minutes="15"><p class="svb-meta">CBSE Board Practice Test · {len(rec["mcq"])} MCQs</p>'
        f'<nav class="svb-nav"><span id="svb-timer" class="svb-btn">15:00</span><button id="svb-start" class="svb-btn" type="button">Start Test</button></nav>'
        f'<form id="svb-form" hidden></form><div id="svb-result"></div><script type="application/json" id="svb-data">{payload}</script><script>{QUIZ_JS}</script></div>'
    )
    render_page(p_mcq, f"MCQ Test · {chapter}", ch_num, chapter, subj, "Timed MCQ Test", body_mcq, [(Path(p_notes).name, "Back to Notes")])


def update_sitemap():
    """रूट फोल्डर में sitemap.xml को ऑटोमैटिक अपडेट करता है"""
    urls = []
    for file in sorted(ROOT.rglob("*.html")):
        if file.name.lower() == "404.html":
            continue
        rel = file.relative_to(ROOT).as_posix()
        urls.append(f"{DOMAIN}/{rel}")
    today = time.strftime("%Y-%m-%d")
    items = "\n".join(f"  <url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{items}\n</urlset>\n'
    (ROOT / "sitemap.xml").write_text(xml, encoding="utf-8")
    print(f"sitemap.xml updated with {len(urls)} URLs.")


def audit_website():
    """Audit local HTML files for broken local links, missing assets and basic SEO gaps."""
    html_files = sorted(ROOT.rglob("*.html"))
    broken_links, missing_assets, seo_warnings = [], [], []
    for file in html_files:
        try:
            soup = BeautifulSoup(file.read_text(encoding="utf-8", errors="replace"), "html.parser")
        except OSError as exc:
            seo_warnings.append(f"Cannot read {file.relative_to(ROOT)}: {exc}")
            continue
        rel = file.relative_to(ROOT).as_posix()
        if not soup.title or not soup.title.get_text(strip=True):
            seo_warnings.append(f"Missing title: {rel}")
        if not soup.find("meta", attrs={"name": re.compile("description", re.I)}):
            seo_warnings.append(f"Missing meta description: {rel}")
        for tag, attr in (("a", "href"), ("link", "href"), ("script", "src"), ("img", "src"), ("source", "src")):
            for node in soup.find_all(tag):
                value = (node.get(attr) or "").strip()
                if not value or value.startswith(("#", "http://", "https://", "//", "mailto:", "tel:", "data:", "javascript:")):
                    continue
                target = (file.parent / value.split("#")[0].split("?")[0]).resolve()
                try:
                    target.relative_to(ROOT.resolve())
                except ValueError:
                    continue
                if not target.exists():
                    item = f"{rel} -> {value}"
                    if tag == "a":
                        broken_links.append(item)
                    else:
                        missing_assets.append(item)
    report = {
        "html_files_scanned": len(html_files),
        "broken_internal_links": broken_links,
        "missing_local_assets": missing_assets,
        "seo_warnings": seo_warnings
    }
    out = ROOT / "shorveer_audit_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    update_sitemap()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nAudit report saved: {out.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", choices=list(SUBJECTS))
    parser.add_argument("--chapter", type=int, help="Specific chapter number to build")
    parser.add_argument("--limit", type=int, default=1, help="Max chapters per run")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--scan", action="store_true", help="Only print detected chapters")
    parser.add_argument("--audit", action="store_true", help="Audit local links, assets and basic SEO")
    args = parser.parse_args()

    if args.audit:
        audit_website()
        return

    targets = analyze_website()
    if args.subject:
        targets = [t for t in targets if t["subject"] == args.subject]
    if args.chapter:
        targets = [t for t in targets if t["chapter_num"] == args.chapter]

    if args.scan:
        print(json.dumps(targets, indent=2, ensure_ascii=False))
        return

    if not targets:
        print("No chapters detected from subject index.html files.")
        return

    state = load_state()
    bot = GroqBot()
    processed = 0

    for t in targets:
        key = f"{t['subject']}::ch{t['chapter_num']}::{t['path']}"
        rec = state.setdefault(key, {})

        if rec.get("status") == "done" and not args.force and (ROOT / t["path"]).exists():
            continue

        if args.limit and processed >= args.limit:
            break

        print(f"\n>>> Building [{t['subject'].upper()}] Chapter {t['chapter_num']}: {t['chapter']} -> {t['path']}")
        try:
            if t["subject"] == "english":
                build_english(bot, t, rec, state, args.force)
            else:
                build_science_math(bot, t, rec, state, args.force)
            rec["status"] = "done"
            rec["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            save_state(state)
            processed += 1
            print(f"<<< Completed Chapter {t['chapter_num']}: {t['chapter']}")
        except Exception as e:
            rec["last_error"] = str(e)
            save_state(state)
            print(f"!!! Failed Chapter {t['chapter_num']}: {e}")

    update_sitemap()


if __name__ == "__main__":
    main()
