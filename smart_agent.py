import os
import re
import glob
import json
import time
import html as htmllib
from bs4 import BeautifulSoup, NavigableString
from groq import Groq

MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
MAX_OUT_TOKENS = 3500
TOKENS_PER_MIN = 6000
MAX_ATTEMPTS = 3
STATE_FILE = "builder_state.json"
TEMPLATE = "index.html"
HARD_LOCK_LINES = 2000
HARD_LOCK_BYTES = 120 * 1024
SUBJECT_ORDER = ["mathematics", "physics", "chemistry", "english"]
PROTECTED_FILES = {"index.html", "about.html", "about-notes.html", "exam-info.html",
                   "privacy.html", "cookies.html", "ads.txt", "404.html"}
BRAND = "Shorveer Notes"
AUTHOR = "Jatin Sandilya"
OLD_SURNAME = "Sharma"
TOPIC_MIN, TOPIC_MAX = 6, 12
MCQ_COUNT = 15
MIN_THEORY_WORDS = 1200

SUBJECT_LABEL = {"mathematics": "Mathematics", "physics": "Physics",
                 "chemistry": "Chemistry", "english": "English"}

FORBIDDEN = {
    "mathematics": ["arrhenius", "activation energy", "reaction rate", "haloalkane", "aldehyde", "ketone"],
    "physics": ["reaction mechanism", "organic chemistry", "haloalkanes", "aldol condensation"],
    "chemistry": ["direction cosines", "matrix adjoint", "integration by parts"],
    "english": ["derivative", "integral", "vector", "matrix", "reaction rate"],
}

SYSTEM = (
    f"You are a CBSE Class 12 {{subject}} teacher writing notes for '{BRAND}', by {AUTHOR}. "
    "Write ONLY about the chapter named in the user message. Never mention or write about any other chapter or book. "
    "Output raw HTML fragment only: no markdown fences, no <html>, <head>, <body>. "
    "No intro, no outro, no meta text (never write 'In this section', 'Made by AI', 'Here is'). "
    "Math: inline $...$ and display $$...$$ only. Never use \\( \\) or \\[ \\] delimiters. "
    "Never write square-bracket placeholders."
)

MATHJAX_CFG = (
    "window.MathJax={tex:{inlineMath:[['$','$'],['\\\\(','\\\\)']],"
    "displayMath:[['$$','$$'],['\\\\[','\\\\]']],processEscapes:true},"
    "options:{skipHtmlTags:['script','noscript','style','textarea','pre','code']}};"
)

PAGE_CSS = """<style>
.chap-wrap{max-width:820px;margin:0 auto;padding:0 4px}
.quick-jump{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:14px 16px;margin:0 0 28px;background:var(--paper-2);border:1px solid var(--line-soft);border-radius:var(--r-md)}
.qj-title{width:100%;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--rust)}
.quick-jump a{font-size:14px;padding:6px 12px;border:1px solid var(--line);border-radius:999px;color:var(--ink-2);background:var(--card)}
.topic-card{margin:0 0 26px;padding:26px 26px 20px;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--gold-dark);border-radius:var(--r-md);box-shadow:var(--shadow-sm);scroll-margin-top:110px}
.topic-card h2{font-size:clamp(24px,3vw,32px);margin-bottom:12px;color:var(--ink)}
.topic-card h3{font-size:19px;margin:18px 0 8px;color:var(--ink)}
.topic-card p,.topic-card li{font-size:16px;line-height:1.75;color:var(--ink-2);overflow-wrap:anywhere}
.topic-card ul{padding-left:20px}
mjx-container[display="true"]{display:block;overflow-x:auto;overflow-y:hidden;max-width:100%;padding:8px 0}
.formula-box{margin:16px 0;padding:14px 16px;background:var(--paper-2);border-left:4px solid var(--gold-dark);border-radius:var(--r-md)}
.practice-box{margin:16px 0;padding:14px 16px;border:1px solid var(--line);border-radius:var(--r-md)}
.flow-wrap{max-width:720px;margin:0 auto;display:flex;flex-direction:column}
.flow-node{padding:14px 18px;background:var(--card);border:1px solid var(--line);border-radius:var(--r-md);box-shadow:var(--shadow-sm)}
.flow-node.root{background:var(--ink);color:var(--paper);text-align:center;font-family:var(--font-display);font-size:22px}
.flow-node h3{font-size:19px;margin-bottom:6px;overflow-wrap:anywhere}
.flow-node ul{padding-left:18px;color:var(--muted);font-size:15px;line-height:1.6}
.flow-arrow{align-self:center;width:2px;height:26px;background:var(--gold-dark);margin:0 auto}
.mm-wrap{max-width:900px;margin:0 auto;display:grid;gap:18px}
.mm-root{font-family:var(--font-display);font-size:clamp(22px,3vw,30px);padding:18px 22px;border-radius:var(--r-lg);background:var(--ink);color:var(--paper);text-align:center;overflow-wrap:anywhere}
.mm-card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--gold-dark);border-radius:var(--r-md);padding:18px 20px}
.mm-card h3{font-family:var(--font-display);font-size:20px;color:var(--ink);margin-bottom:10px;overflow-wrap:anywhere}
.mm-card ul{list-style:none;display:grid;gap:8px;padding:0}
.mm-card li{font-size:15px;line-height:1.6;color:var(--muted);padding-left:16px;position:relative;overflow-wrap:anywhere}
.mm-card li::before{content:"";position:absolute;left:0;top:.6em;width:6px;height:6px;border-radius:50%;background:var(--rust)}
.mcq-wrap{max-width:860px;margin:0 auto}
.mcq-top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.mcq-timer{font-family:var(--font-display);font-size:30px;font-weight:600;color:var(--rust)}
.mcq-q{padding:20px 22px;margin-bottom:14px;background:var(--card);border:1px solid var(--line);border-radius:8px}
.mcq-opt{display:flex;gap:10px;padding:8px 10px;border-radius:6px;cursor:pointer}
.mcq-opt:hover{background:var(--paper-2)}
.mcq-modal{position:fixed;inset:0;z-index:5000;display:none;align-items:center;justify-content:center;padding:20px;background:color-mix(in srgb,var(--ink) 55%,transparent)}
.mcq-modal.open{display:flex}
.mcq-box{width:min(720px,100%);max-height:86vh;overflow:auto;background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:26px;box-shadow:var(--shadow-lg)}
.mcq-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0 20px}
.mcq-stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;text-align:center}
.mcq-stat b{display:block;font-family:var(--font-display);font-size:22px;color:var(--ink)}
.mcq-stat small{color:var(--muted);font-size:12px}
.mcq-exp{padding:12px 14px;margin:10px 0;border-left:3px solid var(--line);font-size:14.5px;line-height:1.6}
.mcq-exp.ok{border-color:var(--green)}
.mcq-exp.no{border-color:var(--rust)}
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
      var p = document.createElement('p'); p.innerHTML = '<b>Q' + (i+1) + '.</b> ';
      var qs = document.createElement('span'); qs.innerHTML = it.q; p.appendChild(qs); d.appendChild(p);
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
        '<div class="mcq-stat"><b>' + right + ' / ' + total + '</b><small>Marks</small></div>' +
        '<div class="mcq-stat"><b>' + pct + '%</b><small>Percentage</small></div>' +
        '<div class="mcq-stat"><b>' + right + '</b><small>Right</small></div>' +
        '<div class="mcq-stat"><b>' + wrong + '</b><small>Wrong or skipped</small></div>' +
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


def cleanup_loop_artifacts():
    for fpath in glob.glob("**/*mindmap*mindmap*.html", recursive=True):
        try:
            os.remove(fpath)
            print(f"[CLEANUP] removed {fpath}")
        except Exception as e:
            print(f"cleanup fail {fpath}: {e}")


_sent = []


def wait_for_budget(tokens):
    tokens = min(tokens, TOKENS_PER_MIN)
    while True:
        now = time.time()
        _sent[:] = [(t, n) for t, n in _sent if now - t < 60]
        if sum(n for _, n in _sent) + tokens <= TOKENS_PER_MIN:
            _sent.append((now, tokens))
            return
        time.sleep(5)


def clean_code(text):
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def call_groq(system, prompt, min_len=150):
    errors = []
    for model in MODELS:
        for attempt in range(1, 4):
            wait_for_budget(len(system + prompt) // 3 + MAX_OUT_TOKENS)
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=0.3,
                    max_completion_tokens=MAX_OUT_TOKENS,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": prompt}],
                )
                text = clean_code((resp.choices[0].message.content or "").strip())
                if len(text) >= min_len:
                    return text
                errors.append(f"{model}: short output")
                break
            except Exception as e:
                msg = str(e)
                low = msg.lower()
                if "per day" in low or "(tpd)" in low:
                    errors.append(f"{model}: daily quota")
                    break
                if "429" in msg or "rate limit" in low:
                    print(f"429 on {model}, waiting {30 * attempt}s")
                    time.sleep(30 * attempt)
                    continue
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
    for s in SUBJECT_ORDER:
        if s in d:
            return s
    if "physic" in d: return "physics"
    if "chem" in d: return "chemistry"
    if "eng" in d: return "english"
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
        if any(k in low for k in ["mindmap", "mcq", "cases", "flow", "part1", "part2", "pyq"]):
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
            "mcq": base + "-mcq.html", "flow": base + "-flow.html"}


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
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower() or "topic"


def chapter_brief(subject, chapter):
    return (f'Subject: {SUBJECT_LABEL[subject]}. Chapter: "{chapter}". '
            f'Stay only on this chapter. Every sentence must belong to "{chapter}".')


def practice_spec(subject):
    if subject == "english":
        return ("Create practice questions of these types, all from this chapter only: "
                "long answer questions (theme, character, plot, message), "
                "comparison questions (between two characters, two poems or two incidents), "
                "short answer and value-based questions, "
                "extract-based questions (give a short passage from the chapter and ask questions on it). "
                "Each item needs a model answer outline.")
    return ("Create practice questions of these types, all from this chapter only: "
            "numericals, derivations, conceptual and application questions, "
            "with full step-by-step solutions in $...$ and $$...$$.")


def list_topics(subject, chapter):
    prompt = (f"{chapter_brief(subject, chapter)}\n"
              f"List 6 to 12 core topics or themes of this exact chapter. "
              f"Return a JSON array of short topic title strings.")
    items = call_json(chapter_system(subject), prompt)
    topics = [t.strip() for t in items if isinstance(t, str) and t.strip()][:TOPIC_MAX]
    if len(topics) < TOPIC_MIN:
        raise RuntimeError(f"only {len(topics)} topics")
    return topics


def topic_card(subject, chapter, topic):
    if subject == "english":
        body_rules = ("Cover: summary of this part, key characters or ideas, literary devices, "
                 
