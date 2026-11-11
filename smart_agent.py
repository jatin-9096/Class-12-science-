import os
import re
import glob
import json
import time
import html as htmllib
from bs4 import BeautifulSoup, NavigableString
from groq import Groq

# ---------------- Config ----------------
MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
MAX_OUT_TOKENS = 3000
TOKENS_PER_MIN = 6000          # Groq Console ke TPM se neeche rakho
TEMPLATE = "index.html"
STATE_FILE = "builder_state.json"
MAX_ATTEMPTS = 3               # ek page par itni baar koshish, phir skip
MIN_WORDS = {False: 1500, True: 1200}
REQUIRED_IDS = {False: ["theory", "derivations"], True: ["pyqs", "case-studies", "mcq"]}
IGNORE_KEYWORDS = ["privacy", "terms", "cookie", "disclaimer", "about", "contact", "framework"]
IGNORE_FILES = {"index.html", "about.html", "about-notes.html", "exam-info.html",
                "privacy.html", "cookies.html"}

BRAND = "Shorveer Notes"
AUTHOR = "Jatin Sandilya"
OLD_SURNAME = "Sharma"
SURNAME = "Sandilya"

LABEL_1 = "Part 1: Theory and Complete Derivations"
LABEL_2 = "Part 2: Practice Questions and Case Studies"

FORBIDDEN = {
    "mathematics": ["arrhenius", "activation energy", "reaction rate", "haloalkane",
                    "sn1", "sn2", "aldehyde", "ketone"],
    "physics": ["reaction mechanism", "organic chemistry", "haloalkanes",
                "aldol condensation", "coordination compounds"],
    "chemistry": ["direction cosines", "shortest distance between skew lines",
                  "matrix adjoint", "integration by parts"],
}

SYSTEM = (
    "You are a CBSE Class 12 subject expert writing for the site "
    f"'{BRAND}', authored by {AUTHOR}. Output ONLY an HTML fragment: no markdown fences, "
    "no <html>, <head>, <body> or <footer>. "
    "All math must be LaTeX: inline $...$ and display $$...$$. "
    "Never use \\( \\) or \\[ \\] delimiters. Never escape dollar signs. "
    "Never write square-bracket placeholders or instructions in the output. "
    "PYQ means real past-year papers, which you cannot verify. So never call any question a PYQ "
    "or Board question. Label every question you write as a Practice Question."
)

MATHJAX_CFG = r"""window.MathJax={tex:{inlineMath:[['$','$'],['\\(','\\)']],displayMath:[['$$','$$'],['\\[','\\]']],processEscapes:true},options:{skipHtmlTags:['script','noscript','style','textarea','pre','code']}};"""

MM_CSS = """<style>
.mindmap{display:flex;flex-direction:column;gap:22px;max-width:880px;margin:0 auto}
.mm-root{font-family:var(--font-display);font-size:28px;padding:18px 24px;border-radius:var(--r-lg);background:var(--ink);color:var(--paper);text-align:center}
.mm-branch{border-left:3px solid var(--gold-dark);padding-left:18px}
.mm-node{font-family:var(--font-display);font-size:20px;font-weight:600;color:var(--ink);margin-bottom:8px}
.mm-children{list-style:none;display:grid;gap:6px;padding-left:10px}
.mm-children li{font-size:15px;color:var(--muted)}
.mm-children li::before{content:"› ";color:var(--rust)}
@media (max-width:720px){.mm-root{font-size:22px}.mm-node{font-size:18px}}
</style>"""

MCQ_CSS = """<style>
.mcq-wrap{max-width:820px;margin:0 auto}
.mcq-top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.mcq-timer{font-family:var(--font-display);font-size:28px;font-weight:600;color:var(--rust)}
.mcq-q{padding:20px 22px;margin-bottom:14px;background:var(--card);border:1px solid var(--line);border-radius:8px}
.mcq-opt{display:flex;gap:10px;padding:8px 10px;border-radius:6px;cursor:pointer}
.mcq-opt:hover{background:var(--paper-2)}
.mcq-exp{padding:10px 12px;margin:8px 0;border-left:3px solid var(--line);font-size:14.5px}
.mcq-exp.ok{border-color:var(--green)}
.mcq-exp.no{border-color:var(--rust)}
#mcq-submit{margin-top:10px}
</style>"""

MCQ_JS = """
(function(){
  var data = JSON.parse(document.getElementById('mcq-data').textContent);
  var body = document.getElementById('mcq-body'), res = document.getElementById('mcq-result');
  var timer = document.getElementById('mcq-timer'), start = document.getElementById('mcq-start');
  var left = 600, iv = null, done = false;
  function fmt(s){ return String(Math.floor(s/60)).padStart(2,'0') + ':' + String(s%60).padStart(2,'0'); }
  function typeset(el){ if (window.MathJax && MathJax.typesetPromise) { MathJax.typesetPromise([el]); } }
  function finish(){
    if (done) return;
    done = true; clearInterval(iv);
    var score = 0, out = '';
    data.forEach(function(it, i){
      var sel = document.querySelector('input[name="q' + i + '"]:checked');
      var ok = !!sel && Number(sel.value) === it.answer;
      if (ok) score++;
      out += '<div class="mcq-exp ' + (ok ? 'ok' : 'no') + '"><b>Q' + (i+1) + '.</b> ' +
             (ok ? 'Correct.' : 'Correct answer: ' + it.options[it.answer] + '.') + ' ' + it.explain + '</div>';
    });
    res.innerHTML = '<h3>Score: ' + score + ' / ' + data.length + '</h3>' + out;
    typeset(res);
    res.scrollIntoView({behavior: 'smooth'});
  }
  function build(){
    body.innerHTML = ''; done = false;
    data.forEach(function(it, i){
      var d = document.createElement('div'); d.className = 'mcq-q';
      d.innerHTML = '<p><b>Q' + (i+1) + '.</b> ' + it.q + '</p>';
      it.options.forEach(function(o, j){
        var l = document.createElement('label'); l.className = 'mcq-opt';
        l.innerHTML = '<input type="radio" name="q' + i + '" value="' + j + '"><span>' + o + '</span>';
        d.appendChild(l);
      });
      body.appendChild(d);
    });
    var sub = document.createElement('button');
    sub.id = 'mcq-submit'; sub.className = 'btn btn-dark'; sub.type = 'button';
    sub.textContent = 'Submit answers';
    sub.addEventListener('click', finish);
    body.appendChild(sub);
    typeset(body);
  }
  start.addEventListener('click', function(){
    build(); res.innerHTML = ''; left = 600; timer.textContent = fmt(left);
    clearInterval(iv);
    iv = setInterval(function(){
      left--; timer.textContent = fmt(left);
      if (left <= 0) { timer.textContent = '00:00'; finish(); }
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


# ---------------- Helpers ----------------
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


def read_soup(path):
    with open(path, encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "html.parser")


def clean_code(text):
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


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


# ---------------- Groq ----------------
def call_groq(prompt):
    errors = []
    for model in MODELS:
        for attempt in range(1, 4):
            wait_for_budget(len(SYSTEM + prompt) // 3 + MAX_OUT_TOKENS)
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=0.4,
                    max_completion_tokens=MAX_OUT_TOKENS,
                    messages=[{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": prompt}],
                )
                text = (resp.choices[0].message.content or "").strip()
                if len(text) > 200:
                    return clean_code(text)
                errors.append(f"{model}: short output")
                break
            except Exception as e:
                msg = str(e)
                low = msg.lower()
                if "per day" in low or "(tpd)" in low:
                    errors.append(f"{model}: daily quota")
                    break
                if "429" in msg or "rate limit" in low:
                    print(f"429 on {model}, {30 * attempt}s wait...")
                    time.sleep(30 * attempt)
                    continue
                errors.append(f"{model}: {msg[:120]}")
                time.sleep(5 * attempt)
    if errors and all("daily quota" in e for e in errors):
        raise DailyQuotaExhausted("; ".join(errors))
    raise RuntimeError("; ".join(errors) or "no output")


# ---------------- Content prompts ----------------
def prompts_for(subject, chapter, is_part2):
    if not is_part2:
        return [
            f"""Write the THEORY section for CBSE Class 12 {subject}, chapter "{chapter}".
Output exactly one block:
<section class="section container reveal" id="theory">
  <div class="section-head"><span class="section-eyebrow">Comprehensive Academic Theory</span><h2>1. Conceptual Framework</h2></div>
  <div class="real-life">
    <article class="rl-card"><div class="rl-body"><div class="rl-subject">...</div><div class="rl-title">...</div><p class="rl-text">...</p></div></article>
    (4 to 6 such articles covering definitions, laws, intuition, exceptions, worked examples)
  </div>
</section>
Real textbook content only. Aim for at least 1500 words.""",
            f"""Continue chapter "{chapter}" of CBSE Class 12 {subject}. Output exactly one block:
<section class="section container reveal" id="derivations">
  <div class="section-head"><span class="section-eyebrow">Formulas and Derivations</span><h2>2. Master Equation Bank</h2></div>
  <div class="resource-grid">
    <article class="resource"><h3>...</h3><p>...</p></article>
  </div>
</section>
Include step-by-step CBSE-standard derivations with LaTeX math, and a formula list with variables, SI units and conditions. Aim for at least 1500 words.""",
        ]
    return [
        f"""For CBSE Class 12 {subject}, chapter "{chapter}", write a section with id="pyqs".
Give exactly 8 PRACTICE questions (2 five-mark, 3 three-mark, 3 two-mark), each with a marking scheme.
Do not call them PYQs or Board questions. Use <section class="section container reveal" id="pyqs"> with section-head and resource-grid cards. Output only that block.""",
        f"""Continue chapter "{chapter}" of CBSE Class 12 {subject}. Output exactly one block:
<section class="section container reveal" id="case-studies"> with 2 case-study articles (passage, sub-questions, full solutions) in real-life cards.
Real content only. Aim for at least 1000 words.""",
    ]


def generate_mcq(subject, chapter):
    prompt = f"""Create 10 practice multiple-choice questions for CBSE Class 12 {subject}, chapter "{chapter}".
These are practice questions, not PYQs. Return ONLY a JSON array, no markdown, no extra text.
Each item must look exactly like this:
{{"q": "question text with LaTeX if needed", "options": ["option A", "option B", "option C", "option D"], "answer": 0, "explain": "one or two line reason"}}
"answer" is the index 0 to 3 of the correct option. Mix easy and hard questions."""
    raw = call_groq(prompt)
    try:
        items = json.loads(raw)
    except Exception:
        raise RuntimeError("MCQ JSON parse failed")
    good = [i for i in items
            if isinstance(i, dict) and i.get("q") and isinstance(i.get("options"), list)
            and len(i["options"]) == 4 and isinstance(i.get("answer"), int)
            and 0 <= i["answer"] <= 3]
    if len(good) < 5:
        raise RuntimeError(f"only {len(good)} valid MCQs")
    return good


def render_mcq(items):
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    return f"""{MCQ_CSS}
<section class="section container reveal" id="mcq">
  <div class="section-head"><span class="section-eyebrow">Practice Section</span><h2>3. Timed MCQ Practice</h2></div>
  <div class="mcq-wrap">
    <div class="mcq-top">
      <span id="mcq-timer" class="mcq-timer">10:00</span>
      <button id="mcq-start" class="btn btn-dark" type="button">Start test</button>
    </div>
    <div id="mcq-body"></div>
    <div id="mcq-result"></div>
  </div>
  <script type="application/json" id="mcq-data">{data}</script>
  <script>{MCQ_JS}</script>
</section>"""


def check_body(html_fragment, is_part2):
    soup = BeautifulSoup(html_fragment, "html.parser")
    ids = {t.get("id") for t in soup.find_all(id=True)}
    missing = [i for i in REQUIRED_IDS[is_part2] if i not in ids]
    words = len(soup.get_text(" ", strip=True).split())
    problems = []
    if missing:
        problems.append(f"missing sections {missing}")
    if words < MIN_WORDS[is_part2]:
        problems.append(f"only {words} words")
    if re.search(r"\[(Provide|Write|Insert|Add)[^\]]*\]", html_fragment, re.I):
        problems.append("placeholder text found")
    return problems


def generate_body(subject, chapter, is_part2):
    feedback, problems = "", []
    for _ in range(2):
        parts = [call_groq(p + feedback) for p in prompts_for(subject, chapter, is_part2)]
        if is_part2:
            parts.append(render_mcq(generate_mcq(subject, chapter)))
        body = "\n\n".join(parts)
        problems = check_body(body, is_part2)
        if not problems:
            return body
        feedback = f"\n\nPrevious attempt problems: {', '.join(problems)}. Fix them completely."
    raise RuntimeError(f"Validation failed: {problems}")


def generate_mindmap_body(subject, chapter):
    prompt = f"""Create a complete mind map for CBSE Class 12 {subject}, chapter "{chapter}".
Output ONLY this HTML structure, no markdown fences:
<div class="mindmap">
  <div class="mm-root">{chapter}</div>
  <div class="mm-branch">
    <div class="mm-node">Concept</div>
    <ul class="mm-children"><li>Sub point</li><li>Sub point</li></ul>
  </div>
</div>
Use 6 to 8 main branches, each with 3 to 5 sub points, ordered so a student scrolls from one idea to the next.
Use LaTeX $...$ for formulas. Real content only."""
    body = call_groq(prompt)
    if 'class="mindmap"' not in body:
        raise RuntimeError("mindmap HTML format galat hai")
    return body


# ---------------- Paths ----------------
def base_of(path):
    root = os.path.splitext(path)[0]
    return re.sub(r"[-_]?(part[12]|pyqs?)$", "", root, flags=re.I)


def mm_path_for(path):
    return base_of(path) + "-mindmap.html"


def mm_link_for(path):
    p = mm_path_for(path)
    return os.path.basename(p) if os.path.exists(p) else None


# ---------------- Page building ----------------
def hero_html(subject, chapter, label, mm_link=None):
    btn = f'<a class="btn btn-light" href="{mm_link}">View mind map</a>' if mm_link else ""
    return (f'<section class="hero container"><div class="hero-copy">'
            f'<div class="kicker"><span class="dot"></span>'
            f'<span>Class 12 · {htmllib.escape(subject)}</span></div>'
            f'<h1>{htmllib.escape(chapter)}</h1>'
            f'<p class="hero-description">{htmllib.escape(label)}</p>'
            f'<div class="hero-actions">{btn}</div></div></section>')


def fix_names(soup):
    for node in list(soup.find_all(string=True)):
        text = str(node)
        if OLD_SURNAME in text:
            node.replace_with(NavigableString(
                text.replace("Jatin Sharma", AUTHOR).replace(OLD_SURNAME, SURNAME)))


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


def build_page(path, subject, chapter, label, body, mm_link=None, add_hero=True):
    depth = len(os.path.normpath(path).split(os.sep)) - 1
    prefix = "../" * depth
    shell = read_soup(TEMPLATE)

    for tag in shell.find_all(["a", "link", "script", "img", "source"]):
        for attr in ("href", "src"):
            v = tag.get(attr)
            if v and not v.startswith(("http", "#", "mailto:", "tel:", "data:", "//", "/")):
                tag[attr] = prefix + v

    # Header ka mind map icon: chapter ke mind map se link, warna hata do
    for a in shell.find_all("a", href=True):
        if a["href"].endswith("mindmap.html"):
            if mm_link:
                a["href"] = mm_link
            else:
                a.decompose()

    main = shell.find("main")
    if main is None:
        raise RuntimeError(f"{TEMPLATE} mein <main> nahi mila")
    main.clear()
    if add_hero:
        main.append(read_fragment(hero_html(subject, chapter, label, mm_link)))
    main.append(read_fragment(body))

    if shell.title:
        shell.title.string = f"{chapter} · Class 12 {subject} | {BRAND}"

    fix_names(shell)
    ensure_mathjax(shell)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(str(shell))
    os.replace(tmp, path)


def read_fragment(fragment):
    return BeautifulSoup(fragment, "html.parser")


def is_hero(node):
    return getattr(node, "name", None) == "section" and "hero" in (node.get("class") or [])


def make_mindmap(subject, chapter, theory_path):
    body = generate_mindmap_body(subject, chapter)
    mm_path = mm_path_for(theory_path)
    build_page(mm_path, subject, chapter, "Mind map: quick revision overview",
               f'<section class="section container reveal">{MM_CSS}{body}</section>')
    return mm_path


def build_theory(path, subject, chapter):
    try:
        make_mindmap(subject, chapter, path)
    except DailyQuotaExhausted:
        raise
    except Exception as e:
        print(f"Mind map skip: {e}")
    body = generate_body(subject, chapter, False)
    build_page(path, subject, chapter, LABEL_1, body, mm_link_for(path))


def shell_fix(t):
    soup = read_soup(t["path"])
    main = soup.find("main")
    keep = "".join(str(c) for c in main.children if not is_hero(c))
    label = LABEL_2 if t["is_part2"] else LABEL_1
    build_page(t["path"], t["subject"], t["chapter"], label, keep, mm_link_for(t["path"]))


# ---------------- Discovery & audit ----------------
def detect_subject(path):
    lower = path.lower()
    if "physic" in lower: return "Physics"
    if "chem" in lower: return "Chemistry"
    if "math" in lower: return "Mathematics"
    if "eng" in lower: return "English"
    return "Science"


def clean_title(a, fname):
    title = ""
    card = a.find_parent(class_=re.compile(r"card|item|subject|resource", re.I))
    if card and card.find(["h2", "h3", "h4"]):
        title = card.find(["h2", "h3", "h4"]).get_text(strip=True)
    if not title:
        title = a.get_text(strip=True)
    if not title or re.search(r"open\s+chapter|read\s+more|chapter\s+\d+", title, re.I):
        title = os.path.splitext(os.path.basename(fname))[0].replace("-", " ").replace("_", " ").title()
    return re.sub(r"\s*\(?(Part\s*[12]|PYQs?)\)?", "", title, flags=re.I).strip()


def discover_pages():
    seen = set()
    for source in glob.glob("**/*.html", recursive=True):
        base_dir = os.path.dirname(source)
        try:
            soup = read_soup(source)
        except Exception:
            continue
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("#", "http", "mailto:", "tel:", "javascript:")):
                continue
            clean = href.split("?")[0].split("#")[0]
            if not clean.endswith(".html") or any(k in clean.lower() for k in IGNORE_KEYWORDS):
                continue
            path = os.path.normpath(os.path.join(base_dir, clean.lstrip("/\\")))
            fname = os.path.basename(path).lower()
            if fname in IGNORE_FILES or path in seen:
                continue
            seen.add(path)
            yield {
                "path": path,
                "subject": detect_subject(path),
                "chapter": clean_title(a, clean),
                "is_part2": "part2" in fname or "pyq" in fname,
            }


def is_mismatched(path, subject):
    words = FORBIDDEN.get(subject.lower())
    if not words:
        return False
    text = read_soup(path).get_text(" ").lower()
    hits = [w for w in words if re.search(r"\b" + re.escape(w) + r"\b", text)]
    return len(hits) >= 2


def audit_page(soup):
    """Purani galtiyan: MathJax nahi, galat delimiters, purana surname."""
    problems = []
    if not soup.find("script", src=re.compile(r"tex-chtml")):
        problems.append("mathjax missing")
    main = soup.find("main")
    if main is not None and re.search(r"\\\(|\\\[", str(main)):
        problems.append("bad math delimiters")
    if OLD_SURNAME in str(soup):
        problems.append("old surname")
    return problems


def find_target(state):
    for page in discover_pages():
        path = page["path"]
        rec = state.setdefault(path, {})
        if rec.get("attempts", 0) >= MAX_ATTEMPTS:
            continue
        if not os.path.exists(path):
            return {**page, "action": "build"}
        soup = read_soup(path)
        main = soup.find("main")
        if main is None or check_body(str(main), page["is_part2"]) or is_mismatched(path, page["subject"]):
            return {**page, "action": "build"}
        if audit_page(soup):
            return {**page, "action": "shell_fix"}
        if not page["is_part2"] and not os.path.exists(mm_path_for(path)):
            return {**page, "action": "mindmap"}
        rec["attempts"] = 0
    return None


def run_target(t):
    s, c, path = t["subject"], t["chapter"], t["path"]
    if t["action"] == "build":
        if t["is_part2"]:
            body = generate_body(s, c, True)
            build_page(path, s, c, LABEL_2, body, mm_link_for(path))
        else:
            build_theory(path, s, c)
    elif t["action"] == "mindmap":
        make_mindmap(s, c, path)
        shell_fix(t)
    else:
        shell_fix(t)


def main():
    state = load_state()
    t = find_target(state)
    if t is None:
        print("Saare pages complete, design aur MathJax theek hain.")
        set_output("has_more", "false")
        save_state(state)
        return

    path = t["path"]
    rec = state.setdefault(path, {})
    rec["attempts"] = rec.get("attempts", 0) + 1
    print(f"[{t['action']}] {path} | {t['subject']}: {t['chapter']} (attempt {rec['attempts']})")

    try:
        run_target(t)
        print("OK")
        set_output("has_more", "true")
    except DailyQuotaExhausted as e:
        print(f"Groq daily quota khatam. Agle scheduled run par resume hoga. ({e})")
        set_output("has_more", "false")
    except Exception as e:
        rec["last_error"] = str(e)[:300]
        print(f"FAILED ({rec['attempts']}/{MAX_ATTEMPTS}): {e}")
        set_output("has_more", "true")
    finally:
        save_state(state)


if __name__ == "__main__":
    main()
