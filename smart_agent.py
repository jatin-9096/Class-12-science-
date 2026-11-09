import os
import re
import glob
import time
from bs4 import BeautifulSoup
from google import genai
from google.genai.errors import ServerError, APIError

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
                print(f"Demand spike on {model_name}. Retrying in 8s...")
                time.sleep(8)
            except Exception as e:
                print(f"Error calling {model_name}: {e}")
                time.sleep(4)
                break
    raise RuntimeError("All Gemini attempts failed.")

def detect_subject_from_path(file_path):
    lower = file_path.lower()
    if "physic" in lower:
        return "Physics"
    elif "chem" in lower:
        return "Chemistry"
    elif "math" in lower:
        return "Mathematics"
    elif "bio" in lower:
        return "Biology"
    return "Science"

def scan_website_links():
    pending_targets = []
    seen_paths = set()
    html_files = glob.glob("**/*.html", recursive=True)

    for source_file in html_files:
        base_dir = os.path.dirname(source_file)
        with open(source_file, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            
            # Card ya item se meaningful heading nikaalna
            title_text = ""
            parent_card = a_tag.find_parent(class_=re.compile(r"card|item|subject", re.I))
            if parent_card:
                h_tag = parent_card.find(["h2", "h3", "h4"])
                if h_tag:
                    title_text = h_tag.get_text(strip=True)
            
            if not title_text:
                title_text = a_tag.get_text(strip=True)

            if not href or href.startswith(("#", "http://", "https://", "mailto:", "tel:", "javascript:")):
                continue
            
            clean_href = href.split("?")[0].split("#")[0]
            if not clean_href.endswith(".html"):
                continue

            if any(k in clean_href.lower() for k in IGNORE_KEYWORDS):
                continue

            normalized_href = clean_href.lstrip("/\\")
            target_path = os.path.normpath(os.path.join(base_dir, normalized_href))

            if not os.path.exists(target_path) and target_path not in seen_paths:
                seen_paths.add(target_path)
                
                subject_name = detect_subject_from_path(target_path)
                
                clean_title = title_text
                if re.search(r"open\s+chapter|click\s+here|read\s+more", clean_title, re.I) or not clean_title:
                    file_base = os.path.splitext(os.path.basename(normalized_href))[0]
                    clean_title = file_base.replace("-", " ").replace("_", " ").title()

                pending_targets.append({
                    "target_path": target_path,
                    "chapter_name": clean_title,
                    "subject": subject_name,
                    "clean_href": normalized_href
                })

    return pending_targets

def clean_code(raw_text):
    text = raw_text.strip()
    if text.startswith("```html"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def build_chapter_page(target):
    target_path = target["target_path"]
    chapter_name = target["chapter_name"]
    subject = target["subject"]

    # Calculate exact relative path to the root style.css
    depth = len(os.path.normpath(target_path).split(os.sep)) - 1
    css_rel = ("../" * depth) + "style.css" if depth > 0 else "style.css"
    hub_link = "index.html" if depth == 1 else "../index.html"
    root_link = "../index.html" if depth == 1 else "index.html"

    # Gemini sirf pure semantic HTML content generate karega
    prompt = f"""
    Generate comprehensive Class 12 CBSE revision notes in semantic HTML for:
    Subject: {subject}
    Chapter: {chapter_name}

    HTML Architecture Requirements:
    Use clean sections and cards matching this structure:

    <section class="section container">
      <div class="section-head">
        <span class="section-eyebrow">Concept Core</span>
        <h2>1. Theoretical Principles & Definitions</h2>
      </div>
      <div class="real-life">
        <article class="rl-card" style="--rl-color: #bf5a3c">
          <div class="rl-badge">§</div>
          <div class="rl-body">
            <div class="rl-title">Fundamental Overview</div>
            <p class="rl-text">Detailed explanation with definitions and principles...</p>
          </div>
        </article>
      </div>
    </section>

    <section class="section container">
      <div class="section-head">
        <span class="section-eyebrow">High Yield Formulas</span>
        <h2>2. Essential Equations & Derivations</h2>
      </div>
      <!-- Use clean MathJax syntax ($...$ for inline and $$...$$ for display equations) -->
      <div class="resource-grid">
        <article class="resource">
          <h3>Key Equations</h3>
          <p>Equation proofs and expressions using MathJax.</p>
        </article>
      </div>
    </section>

    <section class="section container">
      <div class="section-head">
        <span class="section-eyebrow">Board Examination Questions</span>
        <h2>3. Solved High-Yield CBSE PYQs</h2>
      </div>
      <div class="resource-grid">
        <article class="resource">
          <div class="resource-icon">Q1</div>
          <h3>Question Title</h3>
          <p><strong>Problem:</strong> ...</p>
          <p><strong>Step-by-step Solution:</strong> ...</p>
        </article>
        <article class="resource">
          <div class="resource-icon">Q2</div>
          <h3>Question Title</h3>
          <p><strong>Problem:</strong> ...</p>
          <p><strong>Step-by-step Solution:</strong> ...</p>
        </article>
      </div>
    </section>

    <section class="section container">
      <div class="section-head">
        <span class="section-eyebrow">Fast Revision</span>
        <h2>4. Quick Mind-Map & Summary</h2>
      </div>
      <div class="trust">
        <div class="trust-inner container">
          <div class="trust-item"><b>Core Rule 1</b>Summary detail</div>
          <div class="trust-item"><b>Core Rule 2</b>Summary detail</div>
          <div class="trust-item"><b>Board Tip</b>Common mistake to avoid</div>
        </div>
      </div>
    </section>

    RULES:
    1. Output pure HTML content ONLY.
    2. Do NOT write <!DOCTYPE>, <html>, <head>, <header>, or <footer> tags.
    3. Strictly write content relevant to '{subject}' only.
    """

    raw_body = call_gemini_with_fallback(prompt)
    main_body = clean_code(raw_body)

    # Pure HTML template wired entirely to ../style.css and Dynamic Theme Engine
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="author" content="Jatin Sandilya">
  <title>{chapter_name} · Class 12 {subject} | Shorveer Notes</title>

  {MATHJAX_HEADER}

  <!-- Fonts directly aligned with main site -->
  <link rel="preconnect" href="[https://fonts.googleapis.com](https://fonts.googleapis.com)">
  <link rel="preconnect" href="[https://fonts.gstatic.com](https://fonts.gstatic.com)" crossorigin>
  <link href="[https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700;1,9..144,400;1,9..144,500&family=JetBrains+Mono:wght@400;500;700&family=Karla:wght@400;500;600;700&display=swap](https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700;1,9..144,400;1,9..144,500&family=JetBrains+Mono:wght@400;500;700&family=Karla:wght@400;500;600;700&display=swap)" rel="stylesheet">

  <!-- Main Website Stylesheet: Pure styling without inline overrides -->
  <link rel="stylesheet" href="{css_rel}">

  <script>
    // Theme Engine: Reads user choice from localStorage (notebook, chalkboard, blueprint, sunset)
    (function() {{
      try {{
        var savedTheme = localStorage.getItem('shorveer-theme-name') || 'sunset';
        document.documentElement.setAttribute('data-theme', savedTheme);
        document.documentElement.classList.add('js');
      }} catch(e) {{
        document.documentElement.setAttribute('data-theme', 'sunset');
      }}
    }})();
  </script>
</head>
<body>

  <!-- ============ SITE HEADER ============ -->
  <header class="site-header">
    <nav class="nav container" aria-label="Primary">
      <a class="brand" href="{root_link}" aria-label="Shorveer Notes home">
        <span class="brand-mark" aria-hidden="true">
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
    </nav>
  </header>

  <main id="main">

    <!-- Hero Title -->
    <section class="hero container">
      <div class="hero-copy">
        <div class="kicker">
          <span class="dot"></span>
          <span>CBSE Class 12 · {subject} Hub</span>
        </div>
        <h1>{chapter_name}</h1>
        <p class="hero-description">
          Detailed theory breakdowns, verified derivations, and board examination questions curated for precision.
        </p>
        <div class="hero-note">
          <span>Curated by <strong>Jatin Sandilya</strong> · High-Yield Board Solutions</span>
        </div>
      </div>
    </section>

    <!-- AI Generated Content Sections -->
    {main_body}

    <!-- Bottom Hub Navigation -->
    <section class="final-cta container reveal">
      <div class="cta-content">
        <h2>Completed this chapter? <em>Return to the hub.</em></h2>
        <p>Check formula sheets, other syllabus chapters, and high-yield study resources.</p>
        <a class="btn btn-gold" href="{hub_link}">
          Back to {subject} Hub
          <span class="btn-arrow">→</span>
        </a>
      </div>
    </section>

  </main>

  <!-- ============ FOOTER ============ -->
  <footer class="sn-footer">
    <div class="sn-footer__container container">
      <div class="sn-footer__grid">
        
        <div class="sn-footer__brand">
          <a class="sn-brand__logo" href="{root_link}" aria-label="Shorveer Notes home">
            <span class="sn-brand__mark" aria-hidden="true">
              <svg viewBox="0 0 64 64" fill="none">
                <path d="M44 20c-2.5-3.5-7-5-12-5-9 0-14 5.5-14 11.5 0 8 7.5 10 14 12 6.5 2 10 3.5 10 7.5 0 5-5 8-11 8-6.5 0-11-3-13.5-7.5l-4 4.5C17 56 23 60 31 60c11 0 18-6.5 18-15 0-9-8-11.5-14.5-13.5-6-2-9.5-3-9.5-6.5 0-4 4-6 9.5-6 4.5 0 8 1.5 10.5 4.5L44 20z" fill="#e8b64c"/>
              </svg>
            </span>
            <span class="sn-brand__title-txt">Shorveer<em>Notes</em></span>
          </a>

          <h2 class="sn-brand__heading">Class 12 Science, Clearly Organised</h2>
          <p class="sn-brand__sub">A student-focused learning platform for Class 12 Science notes, derivations, and board examination preparation.</p>

          <div class="sn-brand__badge-box">
            <div class="sn-founder-pill">
              <span class="sn-founder-tag">JS</span>
              <span class="sn-founder-name">Created by <strong>Jatin Sandilya</strong></span>
            </div>
          </div>
        </div>

        <div class="sn-nav-col">
          <h3 class="sn-col-head">Portals</h3>
          <ul class="sn-col-links">
            <li><a href="../physics/index.html">Physics Hub</a></li>
            <li><a href="../chemistry/index.html">Chemistry Hub</a></li>
            <li><a href="../mathematics/index.html">Mathematics Hub</a></li>
          </ul>
        </div>

        <div class="sn-nav-col">
          <h3 class="sn-col-head">Connect</h3>
          <ul class="sn-col-links">
            <li><a href="[https://www.youtube.com/@JSEDIZ](https://www.youtube.com/@JSEDIZ)" target="_blank" rel="noopener noreferrer">JS EDIZ on YouTube</a></li>
            <li><a href="mailto:support.shorveernotes@gmail.com">Contact Support</a></li>
          </ul>
        </div>

      </div>
    </div>

    <div class="sn-bottom-bar">
      <div class="sn-bottom-container container">
        <p>&copy; 2026 Shorveer Notes. All rights reserved.</p>
        <p>Built with pride in India 🇮🇳</p>
      </div>
    </div>
  </footer>

</body>
</html>"""

    parent_dir = os.path.dirname(target_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Generated clean HTML page linked to style.css: {target_path}")

def main():
    pending_list = scan_website_links()
    if not pending_list:
        print("All chapters are complete!")
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write("has_more=false\n")
        return

    target = pending_list[0]
    print(f"Generating [{target['subject']}]: {target['chapter_name']} -> {target['target_path']}")
    build_chapter_page(target)

    remaining = len(pending_list) - 1
    print(f"Remaining in queue: {remaining}")
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"has_more={'true' if remaining > 0 else 'false'}\n")

if __name__ == "__main__":
    main()
