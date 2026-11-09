import os
import re
import glob
import time
from bs4 import BeautifulSoup
from google import genai
from google.genai.errors import ServerError, APIError

# Quota protection
BATCH_SIZE = 1

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable missing.")

client = genai.Client(api_key=api_key)

MATHJAX_HEADER = """
<script>
  window.MathJax = {
    tex: {
      inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
      displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
      processEscapes: true
    },
    options: {
      skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
    }
  };
</script>
<script type="text/javascript" id="MathJax-script" async
  src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js">
</script>
"""

IGNORE_KEYWORDS = ["privacy", "terms", "cookie", "disclaimer", "about", "contact", "framework"]

def call_gemini_with_fallback(prompt, max_retries=3):
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    for model_name in models:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                return response.text
            except (ServerError, APIError) as e:
                print(f"Demand spike on {model_name}. Waiting 10s for retry...")
                time.sleep(10)
            except Exception as e:
                print(f"Error calling {model_name}: {e}")
                time.sleep(5)
                break
    raise RuntimeError("All Gemini attempts failed.")

def clean_code(raw_text):
    text = raw_text.strip()
    if text.startswith("```html"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def detect_subject(file_path):
    lower = file_path.lower()
    if "physic" in lower:
        return "Physics"
    elif "chem" in lower:
        return "Chemistry"
    elif "math" in lower:
        return "Mathematics"
    elif "eng" in lower:
        return "English"
    return "Science"

def is_file_corrupt_or_weak(file_path, subject):
    """File quality & corrupt link checker"""
    if not os.path.exists(file_path):
        return True, "Missing File"
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Size check: In-depth notes must be at least 4.5 KB
    if len(content) < 4500:
        return True, "Content too short (needs deep notes)"

    # 2. Giant SVG bug check
    if 'class="sn-wordmark-svg"' in content or 'viewBox="0 0 64 64" fill="none">\n            <path' in content and 'height: 36px;' not in content:
        return True, "Corrupt Giant SVG Logo bug"

    # 3. Subject Contamination Cross-Check
    content_lower = content.lower()
    if subject == "Mathematics":
        if any(w in content_lower for w in ["arrhenius", "chemical kinetics", "activation energy", "haloalkane"]):
            return True, "Cross-contamination: Chemistry found in Math"
    elif subject == "Physics":
        if any(w in content_lower for w in ["organic chemistry", "reaction mechanism"]):
            return True, "Cross-contamination: Chemistry found in Physics"

    return False, "OK"

def scan_website_queue():
    pending_targets = []
    seen_paths = set()
    html_files = glob.glob("**/*.html", recursive=True)

    # 1. Link extraction from index & navigation files
    for source_file in html_files:
        base_dir = os.path.dirname(source_file)
        with open(source_file, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith(("#", "http://", "https://", "mailto:", "tel:", "javascript:")):
                continue
            
            clean_href = href.split("?")[0].split("#")[0]
            if not clean_href.endswith(".html"):
                continue

            if any(k in clean_href.lower() for k in IGNORE_KEYWORDS):
                continue

            normalized_href = clean_href.lstrip("/\\")
            target_path = os.path.normpath(os.path.join(base_dir, normalized_href))

            # Exclude hub/index pages from generation queue
            if os.path.basename(target_path).lower() in ["index.html", "about.html", "about-notes.html", "exam-info.html"]:
                continue

            subject = detect_subject(target_path)
            corrupt, reason = is_file_corrupt_or_weak(target_path, subject)

            if corrupt and target_path not in seen_paths:
                seen_paths.add(target_path)

                title_text = ""
                parent_card = a_tag.find_parent(class_=re.compile(r"card|item|subject", re.I))
                if parent_card:
                    h_tag = parent_card.find(["h2", "h3", "h4"])
                    if h_tag:
                        title_text = h_tag.get_text(strip=True)
                if not title_text:
                    title_text = a_tag.get_text(strip=True)

                if re.search(r"open\s+chapter|read\s+more|chapter\s+\d+", title_text, re.I) or not title_text:
                    file_base = os.path.splitext(os.path.basename(normalized_href))[0]
                    title_text = file_base.replace("-", " ").replace("_", " ").title()

                pending_targets.append({
                    "target_path": target_path,
                    "chapter_name": title_text,
                    "subject": subject,
                    "reason": reason
                })

    return pending_targets

def generate_deep_content(subject, chapter_name):
    """Multi-stage in-depth content generation for textbook-grade length"""
    print(f"-> Generating Stage 1: Theory & Core Concepts for {chapter_name}...")
    p1 = f"""
    Act as a Senior CBSE Examiner and Subject Master in Class 12 {subject}.
    Write an exhaustive, deeply detailed academic Section 1 for the chapter: '{chapter_name}'.
    
    Structure:
    <section class="section container">
      <div class="section-head">
        <span class="section-eyebrow">Exhaustive Theory</span>
        <h2>1. Fundamental Principles, Core Definitions & Complete Theory</h2>
      </div>
      <div class="real-life">
        <article class="rl-card" style="--rl-color: #bf5a3c">
          <div class="rl-body">
            <div class="rl-title">In-Depth Theoretical Framework</div>
            <p class="rl-text">
              Explain every single theorem, law, condition, and graphical variation. Provide multi-paragraph analysis. No brief summaries or placeholders.
            </p>
          </div>
        </article>
      </div>
    </section>
    Return ONLY this HTML section.
    """
    sec1 = clean_code(call_gemini_with_fallback(p1))
    time.sleep(3)

    print(f"-> Generating Stage 2: Formulas, Proofs & Solved PYQs...")
    p2 = f"""
    Continue Class 12 {subject} notes for: '{chapter_name}'.
    Write Section 2 (Complete Formula & Derivations) and Section 3 (CBSE 5-Marker Solved PYQs).
    
    Requirements:
    1. Formulas & Derivations: Use MathJax LaTeX ($...$ for inline, $$...$$ for blocks). Provide full step-by-step proofs.
    2. 3 Solved High-Yield CBSE Board PYQs with full marking step solutions.
    
    Structure:
    <section class="section container">
      <div class="section-head">
        <span class="section-eyebrow">Formulas & Derivations</span>
        <h2>2. High-Yield Equations & Step-by-Step Proofs</h2>
      </div>
      <div class="resource-grid">
        <article class="resource">
          <h3>Full Mathematical Framework</h3>
          <p><!-- formulas & derivations --></p>
        </article>
      </div>
    </section>

    <section class="section container">
      <div class="section-head">
        <span class="section-eyebrow">CBSE Examination Focus</span>
        <h2>3. Solved Board PYQs (5-Mark & 3-Mark Standards)</h2>
      </div>
      <div class="resource-grid">
        <article class="resource">
          <div class="resource-icon">PYQ 1</div>
          <h3>Question 1 (5-Marker)</h3>
          <p><strong>Problem:</strong> ...</p>
          <p><strong>Marking Scheme Solution:</strong> ...</p>
        </article>
        <article class="resource">
          <div class="resource-icon">PYQ 2</div>
          <h3>Question 2 (4-Marker)</h3>
          <p><strong>Problem:</strong> ...</p>
          <p><strong>Marking Scheme Solution:</strong> ...</p>
        </article>
      </div>
    </section>
    Return ONLY these HTML sections.
    """
    sec2_3 = clean_code(call_gemini_with_fallback(p2))
    time.sleep(3)

    print(f"-> Generating Stage 3: Mind Map & Fast Revision Checklist...")
    p3 = f"""
    Finalize Class 12 {subject} notes for: '{chapter_name}'.
    Write Section 4: Mind-Map & Summary Checklist.
    
    Structure:
    <section class="section container">
      <div class="section-head">
        <span class="section-eyebrow">Visual Framework</span>
        <h2>4. High-Yield Mind-Map & Fast Revision Checklist</h2>
      </div>
      <div class="trust">
        <div class="trust-inner container">
          <div class="trust-item"><b>Core Rule</b>Exhaustive summary point</div>
          <div class="trust-item"><b>Board Trap</b>Common error where students lose marks</div>
          <div class="trust-item"><b>Scoring Strategy</b>Key formulas to write for step-marking</div>
        </div>
      </div>
    </section>
    Return ONLY this HTML section.
    """
    sec4 = clean_code(call_gemini_with_fallback(p3))

    return f"{sec1}\n\n{sec2_3}\n\n{sec4}"

def build_chapter_page(target):
    target_path = target["target_path"]
    chapter_name = target["chapter_name"]
    subject = target["subject"]

    depth = len(os.path.normpath(target_path).split(os.sep)) - 1
    css_rel = ("../" * depth) + "style.css" if depth > 0 else "style.css"
    hub_link = "index.html" if depth == 1 else "../index.html"
    root_link = "../index.html" if depth == 1 else "index.html"

    main_body = generate_deep_content(subject, chapter_name)

    full_html = f"""<!DOCTYPE html>
<html lang="en" data-theme="sunset">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="author" content="Jatin Sandilya">
  <title>{chapter_name} · Class 12 {subject} | Shorveer Notes</title>

  {MATHJAX_HEADER}

  <!-- Fonts -->
  <link rel="preconnect" href="[https://fonts.googleapis.com](https://fonts.googleapis.com)">
  <link rel="preconnect" href="[https://fonts.gstatic.com](https://fonts.gstatic.com)" crossorigin>
  <link href="[https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700&family=JetBrains+Mono:wght@400;500;700&family=Karla:wght@400;500;600;700&display=swap](https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700&family=JetBrains+Mono:wght@400;500;700&family=Karla:wght@400;500;600;700&display=swap)" rel="stylesheet">

  <link rel="stylesheet" href="{css_rel}">

  <style>
    /* Strict Layout Alignment & Responsive Safeguards */
    body {{
      background: var(--bg, #241226);
      color: var(--ink, #ffe9d6);
      font-family: var(--font-body, 'Karla', sans-serif);
      margin: 0;
      padding-top: 80px;
    }}
    .site-header {{
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 72px;
      background: rgba(23, 22, 19, 0.94);
      backdrop-filter: blur(14px);
      border-bottom: 1px solid var(--line, rgba(255, 255, 255, 0.15));
      z-index: 1000;
      display: flex;
      align-items: center;
    }}
    .nav-actions {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .palette-dot {{
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: var(--gold, #ff8a5b);
      display: inline-block;
    }}
    .nav-icon {{
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid var(--line, rgba(255, 255, 255, 0.15));
      border-radius: 8px;
      padding: 8px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    /* Fixed Brand Mark Constraints (Stops the giant S bug) */
    .brand-mark, .sn-brand__mark {{
      width: 36px !important;
      height: 36px !important;
      max-width: 36px !important;
      max-height: 36px !important;
      background: #1c1c1a;
      border-radius: 9px;
      display: inline-flex !important;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      flex-shrink: 0;
    }}
    .brand-mark svg, .sn-brand__mark svg {{
      width: 24px !important;
      height: 24px !important;
      max-width: 24px !important;
    }}
    .theme-pop {{
      position: fixed;
      top: 80px;
      right: 24px;
      background: #1c1b18;
      border: 1px solid var(--line, rgba(255,255,255,0.2));
      border-radius: 12px;
      padding: 16px;
      z-index: 2000;
      display: none;
      box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }}
    .theme-pop.open {{
      display: block;
    }}
    .theme-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin: 10px 0;
    }}
    .theme-opt {{
      background: #2a2824;
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 8px;
      padding: 8px 12px;
      color: #fff;
      cursor: pointer;
      text-align: left;
    }}
    /* Solid Aligned Footer */
    .sn-footer {{
      background: #141311 !important;
      border-top: 1px solid var(--line, rgba(255, 255, 255, 0.12));
      padding: 60px 0 35px;
      margin-top: 80px;
      position: relative;
    }}
    .sn-footer__grid {{
      display: grid;
      grid-template-columns: 2fr 1fr 1fr;
      gap: 40px;
      margin-bottom: 40px;
    }}
    @media (max-width: 768px) {{
      .sn-footer__grid {{ grid-template-columns: 1fr; gap: 24px; }}
    }}
  </style>
</head>
<body>

  <!-- ============ HEADER ============ -->
  <header class="site-header">
    <nav class="nav container" aria-label="Primary">
      <a class="brand" href="{root_link}">
        <span class="brand-mark">
          <svg viewBox="0 0 64 64" fill="none">
            <path d="M44 20c-2.5-3.5-7-5-12-5-9 0-14 5.5-14 11.5 0 8 7.5 10 14 12 6.5 2 10 3.5 10 7.5 0 5-5 8-11 8-6.5 0-11-3-13.5-7.5l-4 4.5C17 56 23 60 31 60c11 0 18-6.5 18-15 0-9-8-11.5-14.5-13.5-6-2-9.5-3-9.5-6.5 0-4 4-6 9.5-6 4.5 0 8 1.5 10.5 4.5L44 20z" fill="#e8b64c"/>
          </svg>
        </span>
        <span class="brand-name">Shorveer<em>Notes</em></span>
      </a>

      <div class="nav-links">
        <a href="{root_link}">Home</a>
        <a href="{hub_link}" style="color:var(--ink); font-weight:700;">{subject} Hub</a>
        <a href="[https://www.youtube.com/@JSEDIZ](https://www.youtube.com/@JSEDIZ)" target="_blank" rel="noopener noreferrer">JS EDIZ</a>
      </div>

      <div class="nav-actions">
        <button class="nav-icon" id="themeButton" aria-label="Change theme" title="Pick Theme">
          <span class="palette-dot"></span>
        </button>
      </div>
    </nav>
  </header>

  <!-- ============ THEME PICKER POPOVER ============ -->
  <div class="theme-pop" id="themePop">
    <h4 style="margin:0 0 8px; color:#fff;">Pick a look</h4>
    <div class="theme-grid">
      <button class="theme-opt" data-theme-value="notebook"><b>Notebook</b></button>
      <button class="theme-opt" data-theme-value="chalkboard"><b>Chalkboard</b></button>
      <button class="theme-opt" data-theme-value="blueprint"><b>Blueprint</b></button>
      <button class="theme-opt" data-theme-value="sunset"><b>Sunset</b></button>
    </div>
  </div>

  <main id="main">
    <section class="hero container">
      <div class="hero-copy">
        <div class="kicker">
          <span class="dot"></span>
          <span>CBSE Class 12 · {subject} Comprehensive Notes</span>
        </div>
        <h1>{chapter_name}</h1>
        <p class="hero-description">
          Exhaustive conceptual breakdowns, complete derivations, and step-by-step solved CBSE board exam questions.
        </p>
        <div class="hero-note">
          <span>Curated with Precision by <strong>Jatin Sandilya</strong> · 100% Board Aligned</span>
        </div>
      </div>
    </section>

    {main_body}

    <section class="final-cta container reveal">
      <div class="cta-content">
        <h2>Completed {chapter_name}? <em>Return to the hub.</em></h2>
        <p>Explore formula cards, high-yield mind-maps, and next chapter solutions.</p>
        <a class="btn btn-gold" href="{hub_link}">
          Back to {subject} Hub
          <span class="btn-arrow">→</span>
        </a>
      </div>
    </section>
  </main>

  <!-- ============ FULL SOLID FOOTER ============ -->
  <footer class="sn-footer">
    <div class="container sn-footer__container">
      <div class="sn-footer__grid">
        
        <div class="sn-footer__brand">
          <div class="brand" style="margin-bottom:12px;">
            <span class="sn-brand__mark">
              <svg viewBox="0 0 64 64" fill="none">
                <path d="M44 20c-2.5-3.5-7-5-12-5-9 0-14 5.5-14 11.5 0 8 7.5 10 14 12 6.5 2 10 3.5 10 7.5 0 5-5 8-11 8-6.5 0-11-3-13.5-7.5l-4 4.5C17 56 23 60 31 60c11 0 18-6.5 18-15 0-9-8-11.5-14.5-13.5-6-2-9.5-3-9.5-6.5 0-4 4-6 9.5-6 4.5 0 8 1.5 10.5 4.5L44 20z" fill="#e8b64c"/>
              </svg>
            </span>
            <span class="brand-name" style="color:#fff; margin-left:8px;">Shorveer<em>Notes</em></span>
          </div>
          <p style="color:var(--muted); font-size:0.95rem; line-height:1.6;">
            A student-focused platform providing Class 12 Science notes, derivations, and board examination preparation.
          </p>
          <div style="margin-top:14px; color:var(--muted); font-size:0.9rem;">
            Created with pride by <strong>Jatin Sandilya</strong>
          </div>
        </div>

        <div class="sn-nav-col">
          <h3 style="color:#fff; font-size:1rem; margin-bottom:14px;">Portals</h3>
          <ul style="list-style:none; padding:0; margin:0; line-height:2;">
            <li><a href="../physics/index.html" style="color:var(--muted); text-decoration:none;">Physics Hub</a></li>
            <li><a href="../chemistry/index.html" style="color:var(--muted); text-decoration:none;">Chemistry Hub</a></li>
            <li><a href="../mathematics/index.html" style="color:var(--muted); text-decoration:none;">Mathematics Hub</a></li>
          </ul>
        </div>

        <div class="sn-nav-col">
          <h3 style="color:#fff; font-size:1rem; margin-bottom:14px;">Connect</h3>
          <ul style="list-style:none; padding:0; margin:0; line-height:2;">
            <li><a href="[https://www.youtube.com/@JSEDIZ](https://www.youtube.com/@JSEDIZ)" target="_blank" rel="noopener noreferrer" style="color:var(--muted); text-decoration:none;">JS EDIZ on YouTube</a></li>
            <li><a href="mailto:support.shorveernotes@gmail.com" style="color:var(--muted); text-decoration:none;">Contact Support</a></li>
          </ul>
        </div>

      </div>

      <div style="border-top:1px solid rgba(255,255,255,0.08); padding-top:20px; text-align:center; color:var(--muted); font-size:0.85rem;">
        <p>&copy; 2026 Shorveer Notes · Built with pride in India 🇮🇳</p>
      </div>
    </div>
  </footer>

  <script>
    // Theme Switcher Engine
    const themeBtn = document.getElementById("themeButton");
    const themePop = document.getElementById("themePop");
    const themeOpts = document.querySelectorAll(".theme-opt");

    function applyTheme(name) {{
      document.documentElement.setAttribute("data-theme", name);
      try {{ localStorage.setItem("shorveer-theme-name", name); }} catch(e) {{}}
    }}

    applyTheme(localStorage.getItem("shorveer-theme-name") || "sunset");

    themeBtn.addEventListener("click", (e) => {{
      e.stopPropagation();
      themePop.classList.toggle("open");
    }});

    themeOpts.forEach(btn => {{
      btn.addEventListener("click", () => {{
        applyTheme(btn.dataset.themeValue);
        themePop.classList.remove("open");
      }});
    }});

    document.addEventListener("click", (e) => {{
      if (!themePop.contains(e.target) && !themeBtn.contains(e.target)) {{
        themePop.classList.remove("open");
      }}
    }});
  </script>
</body>
</html>"""

    parent_dir = os.path.dirname(target_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Generated deep, high-yield chapter: {target_path}")

def main():
    pending_list = scan_website_queue()
    if not pending_list:
        print("All chapters are healthy, comprehensive, and up-to-date!")
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write("has_more=false\n")
        return

    target = pending_list[0]
    print(f"Processing [{target['subject']}]: {target['chapter_name']} -> {target['target_path']} (Reason: {target['reason']})")
    build_chapter_page(target)

    remaining = len(pending_list) - 1
    print(f"Remaining in queue: {remaining}")
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"has_more={'true' if remaining > 0 else 'false'}\n")

if __name__ == "__main__":
    main()
