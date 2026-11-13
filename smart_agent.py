import os
import re
import glob
import json
import time
import html as htmllib
from bs4 import BeautifulSoup, NavigableString
from groq import Groq

MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
MAX_OUT_TOKENS = 3000
TOKENS_PER_MIN = 7000
GAP_SEC = 30
STATE_FILE = "builder_state.json"
TEMPLATE = "index.html"
HARD_LOCK_LINES = 2000
HARD_LOCK_BYTES = 120 * 1024
SUBJECT_ORDER = ["english", "mathematics", "physics", "chemistry"]
PROTECTED_FILES = {"index.html", "about.html", "about-notes.html", "exam-info.html",
                   "privacy.html", "cookies.html", "ads.txt", "404.html"}
BRAND = "Shorveer Notes"
AUTHOR = "Jatin Sandilya"
OLD_SURNAME = "Sharma"
SUBJECT_LABEL = {"english": "English", "mathematics": "Mathematics",
                 "physics": "Physics", "chemistry": "Chemistry"}
MIN_THEORY_WORDS = 1200
MCQ_COUNT = 12
FORBIDDEN = {
    "mathematics": ["arrhenius", "activation energy", "reaction rate", "haloalkane", "aldehyde", "ketone"],
    "physics": ["reaction mechanism", "organic chemistry", "haloalkanes", "aldol condensation"],
    "chemistry": ["direction cosines", "matrix adjoint", "integration by parts"],
    "english": ["derivative", "integral", "matrix", "reaction rate", "numerical"],
}
AI_FILLER = re.compile(r"(In this section[^.]*\.|Here is[^.]*\.|Made by AI[^.]*\.|Authored with[^.]*\.)", re.I)

SYSTEM = (
    "You are a CBSE Class 12 {subject} teacher writing notes for '" + BRAND + "', by " + AUTHOR + ". "
    "Write ONLY about the chapter named in the user message. Never mention other chapters or books. "
    "Output raw HTML fragment only: no markdown fences, no <html>, <head>, <body>. "
    "No intro, no outro, no meta text. Math: inline $...$ and display $$...$$ only. "
    "Never use \\( \\) or \\[ \\] delimiters. Never write square-bracket placeholders."
)

MATHJAX_CFG = (
    "window.MathJax={tex:{inlineMath:[['$','$'],['\\\\(','\\\\)']],"
    "displayMath:[['$$','$$'],['\\\\[','\\\\]']],processEscapes:true},"
    "options:{skipHtmlTags:['script','noscript','style','textarea','pre','code']}};"
)

PAGE_CSS = """<style>
.chap-wrap{max-width:820px;margin:0 auto;padding:0 4px}
.quick-jump{display:flex;flex-wrap:wrap;gap:8px;padding:14px 16px;margin:0 0 28px;background:var(--paper-2);border:1px solid var(--line-soft);border-radius:var(--r-md)}
.quick-jump a{font-size:14px;padding:6px 12px;border:1px solid var(--line);border-radius:999px;color:var(--ink-2);background:var(--card)}
.topic-card{display:block;width:100%;margin:0 0 28px;padding:28px 28px 22px;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--gold-dark);border-radius:var(--r-md);box-shadow:var(--shadow-sm);scroll-margin-top:110px}
.topic-card h2{font-size:clamp(24px,3vw,32px);margin-bottom:14px;color:var(--ink)}
.topic-card h3{font-size:19px;margin:20px 0 8px;color:var(--ink)}
.topic-card p,.topic-card li{font-size:16px;line-height:1.75;color:var(--ink-2);overflow-wrap:anywhere}
.topic-card ul{padding-left:20px}
.real-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:16px 0}
.real-box{padding:14px 16px;border-radius:var(--r-md);color:#fff;font-size:15px;line-height:1.6}
.real-box b{display:block;margin-bottom:4px}
.rb1{background:#bf5a3c}.rb2{background:#2a7d7a}.rb3{background:#7a4b8a}.rb4{background:#a67823}.rb5{background:#3d6b9a}.rb6{background:#5a8c62}
.formula-box{margin:16px 0;padding:14px 16px;background:var(--paper-2);border-left:4px solid var(--gold-dark);border-radius:var(--r-md)}
.practice-box{margin:16px 0;padding:14px 16px;border:1px solid var(--line);border-radius:var(--r-md)}
mjx-container{max-width:100%}
mjx-container[display="true"]{display:block;overflow-x:auto;overflow-y:hidden;max-width:100%;padding:8px 0}
.flow-wrap{max-width:720px;margin:0 auto;display:flex;flex-direction:column}
.flow-node{padding:14px 18px;background:var(--card);border:1px solid var(--line);border-radius:var(--r-md);box-shadow:var(--shadow-sm)}
.flow-node.root{background:var(--ink);color:var(--paper);text-align:center;font-family:var(--font-display);font-size:22px}
.flow-node h3{font-size:19px;margin-bottom:6px;overflow-wrap:anywhere}
.flow-node ul{padding-left:18px;color:var(--muted);font-size:15px;line-height:1.6}
.flow-arrow{align-self:center;width:2px;height:26px;background:var(--gold-dark);margin:0 auto}
.mm-wrap{max-width:900px;margin:0 auto;display:grid;gap:18px}
.mm-root{font-family:var(--font-display);font-size:clamp(22px,3vw,30px);padding:18px 22px;border-radius:var(--r-lg);background:var(--ink);color:var(--paper);text-align:center;overflow-wrap:anywhere}
.mm-card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--gold-dark);border-radius:var(--r-md);padding:18px 20px}
.mm-card h3{font-family:var(--font-display);font-size:20px;color:var(--ink);margin-bottom:10px}
.mm-card ul{list-style:none;display:grid;gap:8px;padding:0}
.mm-card li{font-size:15px;line-height:1.6;color:var(--muted);padding-left:16px;position:relative;overflow-wrap:anywhere}
.mm-card li::before{content:"";position:absolute;left:0;top:.6em;width:6px;height:6px;border-radius:50%;background:var(--rust)}
.mcq-wrap{max-width:860px;margin:0 auto}
.mcq-top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.mcq-timer{font-family:var(--font-display);font-size:30px;font-weight:600;color:var(--rust)}
.mcq-q{padding:20px 22px;margin-bottom:14px;background:var(--card);border:1px solid var(--line);border-radius:8px}
.mcq-opt{display:flex;gap:10px;padding:8px 10px;border-radius:6px;cursor:pointer}
.mcq-modal{position:fixed;inset:0;z-index:5000;display:none;align-items:center;justify-content:center;padding:20px;background:color-mix(in srgb,var(--ink) 55%,transparent)}
.mcq-modal.open{display:flex}
.mcq-box{width:min(720px,100%);max-height:86vh;overflow:auto;background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:26px;box-shadow:var(--shadow-lg)}
.mcq-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0 20px}
.mcq-stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;text-align:center}
.mcq-stat b{display:block;font-family:var(--font-display);font-size:22px;color:var(--ink)}
.mcq-exp{padding:12px 14px;margin:10px 0;border-left:3px solid var(--line);font-size:14.5px;line-height:1.6}
.mcq-exp.ok{border-color:var(--green)}
.mcq-exp.no{border-color:var(--rust)}
.page-nav{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin:24px 0}
@media (max-width:620px){.mcq-stats{grid-template-columns:1fr 1fr}}
</style>"""

MCQ_JS = """
(function(){
  var data = JSON.parse(document.getElementById('mcq-data').textContent);
  var body = document.getElementById('mcq-body');
  var timerEl = document.getElementById('mcq-timer');
  var startBtn = document.getElementById('mcq-start');
  var modal = document.getElementById('mcq-modal');
  var mBody = document.getElementById('mcq-modal-body');
  var TOTAL = 900, left = TOTAL, iv = null, done = false;
  function fmt(s){ return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0'); }
  function typeset(el){ if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([el]); }
  function build(){
    body.innerHTML = ''; done = false;
    data.forEach(function(it, i){
      var d = document.createElement('div'); d.className = 'mcq-q';
      var p = document.createElement('p'); p.innerHTML = '<b>Q' + (i+1) + '.</b> ' + it.q; d.appendChild(p);
      it.options.forEach(function(o, j){
        var l = document.createElement('label'); l.className = 'mcq-opt';
        var r = document.createElement('input'); r.type = 'radio'; r.name = 'q' + i; r.value = j;
        var s = document.createElement('span'); s.innerHTML = o;
        l.appendChild(r); l.appendChild(s); d.appendChild(l);
      });
      body.appendChild(d);
    });
    var sub = document.createElement('button');
    sub.className = 'btn btn-dark'; sub.type = 'button'; sub.textContent = 'Submit answers';
    sub.addEventListener('click', finish);
    body.appendChild(sub);
    typeset(body);
  }
  function finish(){
    if (done) return;
    done = true; clearInterval(iv);
    var right = 0, wrong = 0, out = '';
    data.forEach(function(it, i){
      var sel = document.querySelector('input[name="q' + i + '"]:checked');
      var ok = !!sel && Number(sel.value) === it.answer;
      if (ok) right++; else wrong++;
      out += '<div class="mcq-exp ' + (ok ? 'ok' : 'no') + '"><b>Q' + (i+1) + '.</b> ' +
             (ok ? 'Correct.' : 'Correct answer: ' + it.options[it.answer] + '.') + ' ' + it.explain + '</div>';
    });
    var total = data.length, pct = Math.round(right / total * 100);
    mBody.innerHTML =
      '<h2>Your score</h2>' +
      '<div class="mcq-stats">' +
        '<div class="mcq-stat"><b>' + right + ' / ' + total + '</b>Marks</div>' +
        '<div class="mcq-stat"><b>' + pct + '%</b>Percentage</div>' +
        '<div class="mcq-stat"><b>' + right + '</b>Right</div>' +
        '<div class="mcq-stat"><b>' + wrong + '</b>Wrong / skipped</div>' +
      '</div>' + out +
      '<div style="text-align:center;margin-top:18px"><button class="btn btn-dark" id="mcq-close" type="button">Close</button></div>';
    modal.classList.add('open');
    document.getElementById('mcq-close').addEventListener('click', function(){ modal.classList.remove('open'); });
    typeset(mBody);
  }
  startBtn.addEventListener('click', function(){
    build(); left = TOTAL; timerEl.textContent = fmt(left);
    clearInterval(iv);
    iv = setInterval(function(){
      left--; timerEl.textContent = fmt(left);
      if (left <= 0) { timerEl.textContent = '00:00'; finish(); }
    }, 1000);
  });
})();
"""

api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY missing. Repo Settings -> Secrets mein add karo.")
client = Groq(api_key=api_key)

_sent = []
_last_call = [0.0]
_model_block = {}


class DailyQuotaExhausted(Exception):
    pass


def set_output(name, value):
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"{name}={value}\n")


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_soup(path):
    return BeautifulSoup(read_text(path), "html.parser")


def write_atomic(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def wait_for_budget(tokens):
    tokens = min(tokens, TOKENS_PER_MIN)
    while True:
        now = time.time()
        _sent[:] = [(t, n) for t, n in _sent if now - t < 60]
        if sum(n for _, n in _sent) + tokens <= TOKENS_PER_MIN:
            _sent.append((now, tokens))
            return
        time.sleep(5)


def gap_wait():
    # Do API requests ke beech kam se kam 30 second
    elapsed = time.time() - _last_call[0]
    if elapsed < GAP_SEC:
        time.sleep(GAP_SEC - elapsed)
    _last_call[0] = time.time()


def clean_output(text):
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = AI_FILLER.sub("", text)
    return text.strip()


def model_ok(m):
    return time.time() >= _model_block.get(m, 0)


def call_groq(system, prompt, min_len=150):
    errors = []
    for model in MODELS:
        if not model_ok(model):
            errors.append(f"{model}: cooling")
            continue
        for attempt in range(1, 4):
            gap_wait()
            wait_for_budget(len(system + prompt) // 3 + MAX_OUT_TOKENS)
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=0.3,
                    max_completion_tokens=MAX_OUT_TOKENS,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": prompt}],
                )
                text = clean_output((resp.choices[0].message.content or "").strip())
                if len(text) >= min_len:
                    return text
                errors.append(f"{model}: short")
                break
            except Exception as e:
                msg = str(e)
                low = msg.lower()
                if "per day" in low or "(tpd)" in low:
                    _model_block[model] = time.time() + 3600
                    errors.append(f"{model}: daily quota")
                    break
                if "429" in msg or "rate limit" in low:
                    _model_block[model] = time.time() + 30
                    errors.append(f"{model}: rate limited")
                    break
                errors.append(f"{model}: {msg[:120]}")
                time.sleep(5 * attempt)
    if errors and all("daily quota" in e for e in errors):
        raise DailyQuotaExhausted("; ".join(errors))
    raise RuntimeError("; ".join(errors) or "no output")


def call_json(system, prompt):
    raw = call_groq(system, prompt + "\nReturn ONLY valid JSON. No markdown fences.", min_len=5)
    raw = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw.strip())
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"(\[.*\]|\{.*\})", raw, re.S)
        if not m:
            raise RuntimeError("JSON parse failed")
        return json.loads(m.group(1))


def chapter_system(subject):
    return SYSTEM.replace("{subject}", SUBJECT_LABEL[subject])


def subject_of_dir(d):
    d = d.lower()
    if "eng" in d: return "english"
    if "math" in d: return "mathematics"
    if "physic" in d: return "physics"
    if "chem" in d: return "chemistry"
    return None


def chapter_list_from_index(subject_dir):
    idx = os.path.join(subject_dir, "index.html")
    if not os.path.exists(idx):
        return []
    soup = read_soup(idx)
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "http", "mailto:", "tel:", "javascript:")):
            continue
        target = href.split("?")[0].split("#")[0]
        low = target.lower()
        if not low.endswith(".html") or low.endswith("index.html"):
            continue
        if any(k in low for k in ["mindmap", "mcq", "practice", "cases", "flow", "part1", "part2", "pyq"]):
            continue
        card = a.find_parent(class_=re.compile(r"card|item|chapter|resource", re.I))
        title = ""
        if card:
            h = card.find(["h2", "h3", "h4"])
            if h:
                title = h.get_text(" ", strip=True)
        if not title:
            title = a.get_text(" ", strip=True)
        title = re.sub(r"\b(open|read more|view|chapter)\b", "", title, flags=re.I)
        title = re.sub(r"\s+", " ", title).strip(" -–:·")
        if not title:
            continue
        path = os.path.normpath(os.path.join(subject_dir, target))
        if path in seen:
            continue
        seen.add(path)
        out.append({"path": path, "title": title})
    return out


def discover_targets():
    targets = []
    for sub in SUBJECT_ORDER:
        for d in sorted(glob.glob("*/")):
            name = d.rstrip("/")
            if subject_of_dir(name) != sub:
                continue
            for ch in chapter_list_from_index(name):
                targets.append({"subject": sub, "chapter": ch["title"], "path": ch["path"]})
    return targets


def chapter_key(t):
    return f"{t['subject']}::{t['path'].lower()}"


def part_paths(theory_path):
    base = os.path.splitext(theory_path)[0]
    return {"theory": theory_path, "mind": base + "-mindmap.html",
            "mcq": base + "-mcq.html", "flow": base + "-flow.html",
            "practice": base + "-practice.html"}


def is_locked(path):
    if os.path.basename(path).lower() in PROTECTED_FILES:
        return True
    if not os.path.exists(path):
        return False
    if os.path.getsize(path) > HARD_LOCK_BYTES:
        return True
    with open(path, encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f) > HARD_LOCK_LINES


def rel_prefix(path):
    depth = len(os.path.normpath(path).split(os.sep)) - 1
    return "../" * depth


def fix_names(soup):
    for node in list(soup.find_all(string=True)):
        text = str(node)
        if OLD_SURNAME in text:
            node.replace_with(NavigableString(text.replace(OLD_SURNAME, "Sandilya")))


def ensure_mathjax(soup):
    if soup.find("script", src=re.compile(r"tex-chtml")):
        return
    head = soup.find("head")
    if head is None:
        return
    cfg = soup.new_tag("script")
    cfg.string = MATHJAX_CFG
    lib = soup.new_tag("script", src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js")
    lib["async"] = ""
    head.append(cfg)
    head.append(lib)


def page_shell(path, title):
    shell = read_soup(TEMPLATE)
    prefix = rel_prefix(path)
    for tag in shell.find_all(["a", "link", "script", "img", "source"]):
        for attr in ("href", "src"):
            v = tag.get(attr)
            if v and not v.startswith(("http", "#", "mailto:", "tel:", "data:", "//", "/")):
                tag[attr] = prefix + v
    for a in shell.find_all("a", href=True):
        if a["href"].endswith("mindmap.html"):
            a.decompose()
    if shell.title:
        shell.title.string = title
    fix_names(shell)
    ensure_mathjax(shell)
    return shell


def hero_html(subject, chapter, label, links):
    btns = "".join(f'<a class="btn {c}" href="{h}">{txt}</a>' for h, txt, c in links)
    return (f'<section class="hero container"><div class="hero-copy">'
            f'<div class="kicker"><span class="dot"></span>'
            f'<span>Class 12 · {htmllib.escape(SUBJECT_LABEL[subject])}</span></div>'
            f'<h1>{htmllib.escape(chapter)}</h1>'
            f'<p class="hero-description">{htmllib.escape(label)}</p>'
            f'<div class="hero-actions">{btns}</div></div></section>')


def write_page(path, title, label, subject, chapter, main_html, links):
    shell = page_shell(path, title)
    main = shell.find("main")
    main.clear()
    frag = BeautifulSoup(PAGE_CSS + hero_html(subject, chapter, label, links) + main_html, "html.parser")
    for node in list(frag.contents):
        main.append(node.extract())
    write_atomic(path, str(shell))


def slugify(s):
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower() or "section"


def brief(subject, chapter):
    return (f'Subject: {SUBJECT_LABEL[subject]}. Chapter: "{chapter}". '
            f'Stay strictly on this chapter. Every sentence must belong to "{chapter}". '
            f'No filler, no AI meta text.')


def sys_for(subject):
    return chapter_system(subject)


def list_sections(subject, chapter):
    n_hint = "17 to 25"
    prompt = (f"{brief(subject, chapter)}\n"
              f"List {n_hint} detailed section titles that together cover this chapter fully, "
              f"in teaching order. Return a JSON array of short title strings.")
    items = call_json(sys_for(subject), prompt)
    titles = [t.strip() for t in items if isinstance(t, str) and t.strip()]
    if len(titles) < 8:
        raise RuntimeError(f"only {len(titles)} sections")
    return titles[:25]


def notes_section(subject, chapter, title):
    prompt = (f"{brief(subject, chapter)}\n"
              f'Write one detailed notes section titled "{title}". '
              f"Output exactly: <section class=\"topic-card\" id=\"s-{slugify(title)}\">"
              f"<h2>{htmllib.escape(title)}</h2> then several paragraphs of explanation, "
              f"definitions, and for Maths/Physics/Chemistry derivations in $$...$$, "
              f"then a formula-box if relevant, then a div class=\"real-grid\" with 3 to 4 "
              f"real-life application boxes, each <div class=\"real-box rbN\"><b>Title</b>text</div> "
              f"with N from 1 to 6 and different N per box. Close with </section>. "
              f"At least 300 words.")
    return call_groq(sys_for(subject), prompt, min_len=300)


def english_extra(chapter, subject):
    prompt = (f"{brief(subject, chapter)}\n"
              f"Write these as HTML only, each in its own <section class=\"topic-card\">: "
              f"1) Character sketch (for each main character, if the chapter has characters). "
              f"2) Chapter summary. 3) Long answer questions with model answer outlines. "
              f"4) Extract-based questions with a short passage from this chapter and questions on it. "
              f"5) Value-based questions with answers. "
              f"Do NOT include any numerical or derivation questions.")
    return call_groq(sys_for(subject), prompt, min_len=400)


def practice_page_html(subject, chapter):
    if subject == "english":
        return None
    prompt = (f"{brief(subject, chapter)}\n"
              f"Write a practice paper as HTML only: 8 to 10 questions in CBSE board style "
              f"(short, long and numerical as applicable), each in a <div class=\"practice-box\"> "
              f"with a full step-by-step solution. Math in $...$ and $$...$$. No PYQ labels.")
    return call_groq(sys_for(subject), prompt, min_len=400)


def mindmap_html(subject, chapter, sections):
    prompt = (f"{brief(subject, chapter)}\n"
              f"Mind map for these sections: {json.dumps(sections, ensure_ascii=False)}.\n"
              f'Return JSON: {{"branches": [{{"title": "...", "points": ["...", "..."]}}]}} '
              f"with one branch per section, 3 to 5 points each.")
    data = call_json(sys_for(subject), prompt)
    branches = data.get("branches", []) if isinstance(data, dict) else []
    if not branches:
        raise RuntimeError("mindmap empty")
    cards = "".join(
        f'<div class="mm-card"><h3>{b.get("title", "")}</h3><ul>'
        + "".join(f"<li>{p}</li>" for p in b.get("points", [])) + "</ul></div>"
        for b in branches)
    return f'<div class="mm-wrap"><div class="mm-root">{htmllib.escape(chapter)}</div>{cards}</div>'


def flow_html(subject, chapter, sections):
    prompt = (f"{brief(subject, chapter)}\n"
              f"Flow chart of this chapter in teaching order: {json.dumps(sections, ensure_ascii=False)}.\n"
              f'Return JSON: {{"steps": [{{"title": "...", "points": ["..."]}}]}} with 6 to 10 steps.')
    data = call_json(sys_for(subject), prompt)
    steps = data.get("steps", []) if isinstance(data, dict) else []
    if not steps:
        raise RuntimeError("flow empty")
    parts = [f'<div class="flow-node root">{htmllib.escape(chapter)}</div>']
    for s in steps:
        pts = "".join(f"<li>{p}</li>" for p in s.get("points", []))
        parts.append('<div class="flow-arrow"></div>')
        parts.append(f'<div class="flow-node"><h3>{htmllib.escape(s.get("title", ""))}</h3><ul>{pts}</ul></div>')
    return f'<div class="chap-wrap"><div class="flow-wrap">{"".join(parts)}</div></div>'


def mcq_items(subject, chapter):
    if subject == "english":
        spec = "Literature comprehension and character/theme questions only. No numericals."
    else:
        spec = "Conceptual and numerical MCQs on this chapter only."
    prompt = (f"{brief(subject, chapter)}\n{spec}\n"
              f"Create {MCQ_COUNT} MCQs. Return a JSON array, each item: "
              f'{{"q": "...", "options": ["A","B","C","D"], "answer": 0, "explain": "..."}}. '
              f"answer is index 0 to 3.")
    items = call_json(sys_for(subject), prompt)
    good = [i for i in items
            if isinstance(i, dict) and i.get("q") and isinstance(i.get("options"), list)
            and len(i["options"]) == 4 and isinstance(i.get("answer"), int)
            and 0 <= i["answer"] <= 3 and i.get("explain")]
    if len(good) < 8:
        raise RuntimeError(f"only {len(good)} valid MCQs")
    return good


def mcq_page_html(items):
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    return f"""
<section class="section container reveal">
  <div class="mcq-wrap">
    <div class="mcq-top">
      <span id="mcq-timer" class="mcq-timer">15:00</span>
      <button id="mcq-start" class="btn btn-dark" type="button">Start test</button>
    </div>
    <div id="mcq-body"></div>
  </div>
  <div id="mcq-modal" class="mcq-modal" role="dialog" aria-modal="true">
    <div class="mcq-box"><div id="mcq-modal-body"></div></div>
  </div>
  <script type="application/json" id="mcq-data">{data}</script>
  <script>{MCQ_JS}</script>
</section>"""


def theory_check(path, subject):
    soup = read_soup(path)
    text = soup.get_text(" ", strip=True)
    low = text.lower()
    if len(text.split()) < MIN_THEORY_WORDS:
        return False, "too short"
    for w in FORBIDDEN.get(subject, []):
        if re.search(r"\b" + re.escape(w) + r"\b", low):
            return False, f"off-topic: {w}"
    if re.search(r"\\\(|\\\[", str(soup)):
        return False, "bad delimiters"
    if OLD_SURNAME in str(soup):
        return False, "old surname"
    if not soup.find("script", src=re.compile(r"tex-chtml")):
        return False, "mathjax missing"
    return True, "ok"


def step_for(t, rec):
    """Ek run = ek API request. Order: sections list -> notes sections -> english extras -> theory page -> mind map -> flow -> MCQ -> practice."""
    s, c, theory = t["subject"], t["chapter"], t["path"]
    P = part_paths(theory)

    if "sections" not in rec:
        rec["sections"] = list_sections(s, c)
        return "sections listed"

    notes = rec.setdefault("notes", {})
    for title in rec["sections"]:
        if title not in notes:
            notes[title] = notes_section(s, c, title)
            return f"notes: {title}"

    if s == "english" and "english_extra" not in rec:
        rec["english_extra"] = english_extra(c, s)
        return "english extras"

    if not os.path.exists(theory):
        body = "".join(notes[t_] for t_ in rec["sections"])
        if s == "english":
            body += rec.get("english_extra", "")
        toc = "".join(f'<a href="#s-{slugify(t_)}">{htmllib.escape(t_)}</a>' for t_ in rec["sections"])
        links = [(os.path.basename(P["mind"]), "View Mind Map", "btn-gold"),
                 (os.path.basename(P["flow"]), "Flow Chart", "btn-light"),
                 (os.path.basename(P["mcq"]), "Timed MCQ Test", "btn-dark")]
        if s != "english":
            links.append((os.path.basename(P["practice"]), "Practice Questions", "btn-light"))
        write_page(theory, f"{c} · Class 12 {SUBJECT_LABEL[s]} | {BRAND}",
                   "Part 1: Detailed Notes", s, c,
                   f'<div class="chap-wrap"><nav class="quick-jump">{toc}</nav>{body}</div>', links)
        return "theory page written"

    if not os.path.exists(P["mind"]):
        write_page(P["mind"], f"Mind Map · {c} | {BRAND}", "Visual mind map", s, c,
                   mindmap_html(s, c, rec["sections"]),
                   [(os.path.basename(theory), "Back to notes", "btn-dark")])
        return "mind map written"

    if not os.path.exists(P["flow"]):
        write_page(P["flow"], f"Flow Chart · {c} | {BRAND}", "Flow chart", s, c,
                   flow_html(s, c, rec["sections"]),
                   [(os.path.basename(theory), "Back to notes", "btn-dark")])
        return "flow chart written"

    if not os.path.exists(P["mcq"]):
        items = mcq_items(s, c)
        write_page(P["mcq"], f"MCQ · {c} | {BRAND}", "Timed practice test", s, c,
                   mcq_page_html(items),
                   [(os.path.basename(theory), "Back to notes", "btn-dark")])
        return "mcq written"

    if s != "english" and not os.path.exists(P["practice"]):
        html_body = practice_page_html(s, c)
        write_page(P["practice"], f"Practice Questions · {c} | {BRAND}", "Practice question paper", s, c,
                   f'<div class="chap-wrap">{html_body}</div>',
                   [(os.path.basename(theory), "Back to notes", "btn-dark")])
        return "practice written"

    return None


def remove_chapter_files(P):
    for p in P.values():
        if os.path.exists(p):
            os.remove(p)


def main():
    state = load_state()
    targets = discover_targets()
    print(f"Chapters from indexes: {len(targets)}")

    for t in targets:
        key = chapter_key(t)
        rec = state.setdefault(key, {})
        if rec.get("done") or is_locked(t["path"]):
            if is_locked(t["path"]):
                rec["done"] = True
            continue
        if rec.get("attempts", 0) >= 3:
            continue

        P = part_paths(t["path"])
        if all(os.path.exists(p) for p in P.values()):
            ok, why = theory_check(t["path"], t["subject"])
            rec["done"] = ok
            rec["last_error"] = None if ok else why
            save_state(state)
            if not ok:
                print(f"[audit] {t['chapter']}: {why} -> rebuild")
                remove_chapter_files(P)
                rec.clear()
                save_state(state)
            set_output("has_more", "true")
            return

        rec["attempts"] = rec.get("attempts", 0) + 1
        print(f"[step] {t['subject']} | {t['chapter']} attempt {rec['attempts']}")
        try:
            msg = step_for(t, rec)
            if msg is None:
                ok, why = theory_check(t["path"], t["subject"])
                rec["done"] = ok
                rec["last_error"] = None if ok else why
                print("OK" if ok else f"validation: {why}")
            else:
                rec["attempts"] = 0
                print(msg)
            save_state(state)
            set_output("has_more", "true")
            return
        except DailyQuotaExhausted as e:
            rec["attempts"] -= 1
            save_state(state)
            print(f"Groq daily quota. Next run par resume. ({e})")
            set_output("has_more", "false")
            return
        except Exception as e:
            rec["last_error"] = str(e)[:300]
            save_state(state)
            print(f"FAILED ({rec['attempts']}/3): {e}")
            set_output("has_more", "true")
            return

    print("Saare chapters complete aur audit pass.")
    save_state(state)
    set_output("has_more", "false")


if __name__ == "__main__":
    main()
