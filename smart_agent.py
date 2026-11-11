import os
import re
import glob
import json
import time
from bs4 import BeautifulSoup
from groq import Groq

# ---------------- Config ----------------
MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
MAX_OUT_TOKENS = 3000
TOKENS_PER_MIN = 6000          # Groq Console ke TPM se neeche rakho
TEMPLATE = "index.html"        # index.html hi design ka source hai
STATE_FILE = "builder_state.json"
MAX_FAILURES = 3
MIN_WORDS = {False: 1500, True: 1200}
REQUIRED_IDS = {False: ["theory", "derivations"], True: ["pyqs", "case-studies", "mindmap"]}
IGNORE_KEYWORDS = ["privacy", "terms", "cookie", "disclaimer", "about", "contact", "framework"]
IGNORE_FILES = {"index.html", "about.html", "about-notes.html", "exam-info.html",
                "privacy.html", "cookies.html"}

BRAND = "Shorveer Notes"
AUTHOR = "Jatin Sandilya"
OLD_SURNAME = "Sharma"

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
    "PYQ means real past-year papers, which you cannot verify. So for any question you write, "
    "label it as 'Practice Question' and never call it a PYQ."
)

api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY missing. Repo Settings -> Secrets mein add karo.")
client = Groq(api_key=api_key)


class DailyQuotaExhausted(Exception):
    pass


# ---------------- State & helpers ----------------
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


def clean_code(text):
    text = text.strip()
    text = re.sub(r"^```(?:html)?\s*", "", text)
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


# ---------------- Groq call ----------------
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
        f"""Continue chapter "{chapter}" of CBSE Class 12 {subject}. Output exactly two blocks:
1. <section class="section container reveal" id="case-studies"> with 2 case-study articles (passage, sub-questions, full solutions) in real-life cards.
2. <section class="section container reveal" id="mindmap"> with a visual mind-map built as nested HTML lists or a flow of boxes (one idea after another, easy to scroll), plus examiner traps and scoring strategy.
Real content only. Aim for at least 1200 words.""",
    ]


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
        body = "\n\n".join(parts)
        problems = check_body(body, is_part2)
        if not problems:
            return body
        feedback = f"\n\nPrevious attempt problems: {', '.join(problems)}. Fix them completely."
    raise RuntimeError(f"Validation failed: {problems}")


# ---------------- Page building ----------------
def hero(subject, chapter, is_part2):
    label = ("Part 2: Practice Questions & Case Studies" if is_part2
             else "Part 1: Theory & Complete Derivations")
    return (f'<section class="hero container"><div class="hero-copy">'
            f'<div class="kicker"><span class="dot"></span>'
            f'<span>Class 12 · {subject}</span></div>'
            f'<h1>{chapter}</h1>'
            f'<p class="hero-description">{label}</p></div></section>')


def fix_brand_and_author(soup):
    """Purana surname hatao aur brand/author ek jaisa karo."""
    for node in soup.find_all(string=True):
        text = str(node)
        if OLD_SURNAME in text:
            node.replace_with(text.replace("Jatin Sharma", AUTHOR).replace(OLD_SURNAME, AUTHOR.split()[-1]))
    for tag in soup.find_all(class_=re.compile(r"sn-founder-name")):
        for s in tag.find_all("strong"):
            s.string = AUTHOR


def ensure_mathjax(soup):
    """Head mein MathJax na ho to add karo."""
    head = soup.find("head")
    if head is None or soup.find("script", src=re.compile(r"tex-chtml")):
        return
    cfg = soup.new_tag("script")
    cfg.string = (
        "window.MathJax = {tex:{inlineMath:[['$','$'],['\\\\(','\\\\)']],"
        "displayMath:[['$$','$$'],['\\\\[','\\\\]']],processEscapes:true},"
        "options:{skipHtmlTags:['script','noscript','style','textarea','pre','code']}};"
    )
    lib = soup.new_tag("script", id="MathJax-script", src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js")
    lib["async"] = True
    head.append(cfg)
    head.append(lib)


def build_page(path, subject, chapter, is_part2, body, add_hero=True):
    depth = len(os.path.normpath(path).split(os.sep)) - 1
    prefix = "../" * depth
    shell = BeautifulSoup(open(TEMPLATE, encoding="utf-8").read(), "html.parser")

    for tag in shell.find_all(["a", "link", "script", "img", "source"]):
        for attr in ("href", "src"):
            v = tag.get(attr)
            if v and not v.startswith(("http", "#", "mailto:", "tel:", "data:", "//", "/")):
                tag[attr] = prefix + v

    main = shell.find("main")
    if main is None:
        raise RuntimeError(f"{TEMPLATE} mein <main> nahi mila")
    main.clear()
    if add_hero:
        main.append(BeautifulSoup(hero(subject, chapter, is_part2), "html.parser"))
    main.append(BeautifulSoup(body, "html.parser"))
    if shell.title:
        shell.title.string = f"{chapter} · Class 12 {subject} | {BRAND}"

    fix_brand_and_author(shell)
    ensure_mathjax(shell)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(str(shell))
    os.replace(tmp, path)


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
            soup = BeautifulSoup(open(source, encoding="utf-8").read(), "html.parser")
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
    text = BeautifulSoup(open(path, encoding="utf-8").read(), "html.parser").get_text(" ").lower()
    hits = [w for w in words if re.search(r"\b" + re.escape(w) + r"\b", text)]
    return len(hits) >= 2


def audit_page(soup, is_part2):
    """Purane pages mein MathJax, delimiters, naam aur surname ki galti pakdo."""
    problems = []
    html_text = str(soup)
    if "tex-chtml" not in html_text:
        problems.append("MathJax script missing")
    if re.search(r"\\\(|\\\[", html_text):
        problems.append("bad math delimiters \\( or \\[")
    if OLD_SURNAME in html_text:
        problems.append("old surname present")
    if BRAND not in html_text and "ShorveerNotes" in html_text:
        problems.append("brand name mismatch")
    return problems


def find_target(state):
    for page in discover_pages():
        path = page["path"]
        rec = state.get(path, {})
        if rec.get("status") == "done" or rec.get("failures", 0) >= MAX_FAILURES:
            continue
        if not os.path.exists(path):
            return {**page, "action": "build"}
        soup = BeautifulSoup(open(path, encoding="utf-8").read(), "html.parser")
        main = soup.find("main")
        if main is None or check_body(str(main), page["is_part2"]) or is_mismatched(path, page["subject"]):
            return {**page, "action": "build"}
        if audit_page(soup, page["is_part2"]):
            return {**page, "action": "shell_fix"}
        if soup.find(class_="site-header") is None:
            return {**page, "action": "shell_fix"}
        state[path] = {"status": "done"}
    return None


def main():
    state = load_state()
    target = find_target(state)
    if target is None:
        print("Saare pages complete aur design-match hain.")
        set_output("has_more", "false")
        save_state(state)
        return

    path = target["path"]
    print(f"[{target['action']}] {path} | {target['subject']}: {target['chapter']}")
    try:
        if target["action"] == "shell_fix":
            old = BeautifulSoup(open(path, encoding="utf-8").read(), "html.parser")
            body = "".join(str(c) for c in old.find("main").children)
            build_page(path, target["subject"], target["chapter"], target["is_part2"], body, add_hero=False)
        else:
            body = generate_body(target["subject"], target["chapter"], target["is_part2"])
            build_page(path, target["subject"], target["chapter"], target["is_part2"], body)
        state[path] = {"status": "done"}
        print("OK")
    except DailyQuotaExhausted as e:
        print(f"Groq daily quota khatam. Agle scheduled run par resume hoga. ({e})")
        set_output("has_more", "false")
        save_state(state)
        return
    except Exception as e:
        rec = state.setdefault(path, {})
        rec["failures"] = rec.get("failures", 0) + 1
        rec["last_error"] = str(e)[:300]
        print(f"FAILED ({rec['failures']}/{MAX_FAILURES}): {e}")

    save_state(state)
    set_output("has_more", "true")
def generate_mindmap(subject, chapter):
    prompt = f"""Create a complete mind map for CBSE Class 12 {subject}, chapter "{chapter}".
Output ONLY this HTML structure, no markdown fences:
<div class="mindmap">
  <div class="mm-root">{chapter}</div>
  <div class="mm-branch">
    <div class="mm-node">Concept</div>
    <ul class="mm-children"><li>Sub point</li></ul>
  </div>
</div>
Use 6 to 8 main branches, each with 3 to 5 sub points. Use LaTeX $...$ for formulas. Real content only."""
    return call_groq(prompt)


def build_mindmap_page(theory_path, subject, chapter):
    mm_path = theory_path.replace(".html", "-mindmap.html")
    body = generate_mindmap(subject, chapter)
    if "<div class=\"mindmap\"" not in body:
        raise RuntimeError("mindmap HTML format galat hai")
    build_page(mm_path, subject, chapter, False, f'<section class="section container reveal">{body}</section>')
    return mm_path

if __name__ == "__main__":
    main()
