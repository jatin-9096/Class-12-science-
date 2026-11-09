import os
import re
import glob
import time
from bs4 import BeautifulSoup
from google import genai
from google.genai.errors import ServerError, APIError

# API Quota Safe: Ek run me ek page
BATCH_SIZE = 1

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable missing.")

client = genai.Client(api_key=api_key)

# Clean MathJax with proper Delimiters & processEscapes
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

IGNORE_KEYWORDS = ["privacy", "terms", "cookie", "disclaimer", "about", "contact"]

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
                print(f"Server demand spike ({e}). Waiting 10s for retry...")
                time.sleep(10)
            except Exception as e:
                print(f"Error calling {model_name}: {e}")
                time.sleep(5)
                break
    raise RuntimeError("All Gemini model attempts exhausted.")

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
            chapter_name = a_tag.get_text(strip=True)

            if not href or href.startswith(("#", "http://", "https://", "mailto:", "tel:", "javascript:")):
                continue
            
            clean_href = href.split("?")[0].split("#")[0]
            if not clean_href.endswith(".html"):
                continue

            if any(k in clean_href.lower() or k in chapter_name.lower() for k in IGNORE_KEYWORDS):
                continue

            normalized_href = clean_href.lstrip("/\\")
            target_path = os.path.normpath(os.path.join(base_dir, normalized_href))

            if not os.path.exists(target_path) and target_path not in seen_paths:
                seen_paths.add(target_path)
                pending_targets.append({
                    "target_path": target_path,
                    "chapter_name": chapter_name if chapter_name else os.path.splitext(os.path.basename(normalized_href))[0],
                    "clean_href": normalized_href,
                    "source_file": source_file
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

def patch_file_errors(file_path):
    """Puri file rewrite nahi karega; sirf broken closing tags patch karega"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    unclosed = []
    for tag in ["html", "head", "body", "main", "article", "section", "div"]:
        open_c = len(re.findall(rf"<{tag}\b", content, re.I))
        close_c = len(re.findall(rf"</{tag}>", content, re.I))
        if open_c > close_c:
            unclosed.append(tag)

    if unclosed:
        print(f"Patching unclosed structural tags in {file_path}: {unclosed}")
        patch_str = ""
        for tag in reversed(unclosed):
            patch_str += f"</{tag}>\n"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("\n" + patch_str)

def build_chapter_page(target):
    target_path = target["target_path"]
    chapter_name = target["chapter_name"]

    # Calculate correct relative path to style.css based on folder depth
    depth = len(os.path.normpath(target_path).split(os.sep)) - 1
    css_rel = ("../" * depth) + "style.css" if depth > 0 else "style.css"
    hub_link = "index.html" if depth == 1 else "../index.html"

    prompt = f"""
    Write detailed, structured Class 12 educational chapter notes in HTML for: '{chapter_name}'.
    
    Required Components inside HTML cards:
    1. Comprehensive Chapter Overview & Core Concepts.
    2. Key Theorems / Reaction Mechanisms / Core Formulas (wrap in <div class="formula-box">, use valid inline $...$ and display $$...$$ LaTeX math).
    3. Solved High-Yield CBSE Board PYQs (3 standard questions with clear step-by-step marking steps).
    4. Quick Revision Summary Box.
    5. Concept Mind-Map points list.

    STRICT RULES:
    - Output ONLY the HTML contents to be placed inside <main class="container">.
    - DO NOT include <!DOCTYPE>, <html>, <head>, <header>, or <footer> tags.
    - Author attribution must strictly be 'Jatin Sandilya'.
    """

    raw_body = call_gemini_with_fallback(prompt)
    main_body = clean_code(raw_body)

    # Master Verified Branded Template with Stable Grid Footer
    full_html = f"""<!DOCTYPE html>
<html lang="en" data-theme="sunset">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{chapter_name} | Shorveer Notes</title>
  
  {MATHJAX_HEADER}

  <!-- Fonts -->
  <link rel="preconnect" href="[https://fonts.googleapis.com](https://fonts.googleapis.com)">
  <link rel="preconnect" href="[https://fonts.gstatic.com](https://fonts.gstatic.com)" crossorigin>
  <link href="[https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700&family=JetBrains+Mono:wght@400;500;700&family=Karla:wght@400;500;600;700&display=swap](https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700&family=JetBrains+Mono:wght@400;500;700&family=Karla:wght@400;500;600;700&display=swap)" rel="stylesheet">

  <link rel="stylesheet" href="{css_rel}">

  <style>
    body {{
      background: var(--bg, #241226);
      color: var(--ink, #ffe9d6);
      font-family: var(--font-body, 'Karla', sans-serif);
      margin: 0;
      padding-top: 76px;
    }}
    .container {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 0 24px;
    }}
    .site-header {{
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 72px;
      background: rgba(36, 18, 38, 0.95);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--line, rgba(255, 255, 255, 0.12));
      z-index: 1000;
      display: flex;
      align-items: center;
    }}
    .nav-inner {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      width: 100%;
    }}
    .brand-title {{
      font-family: var(--font-heading, 'Fraunces', serif);
      font-size: 1.35rem;
      font-weight: 700;
      color: #fff;
      text-decoration: none;
    }}
    .brand-title em {{
      color: var(--gold, #ff8a5b);
      font-style: normal;
    }}
    .nav-links a {{
      color: var(--muted, #a090a0);
      text-decoration: none;
      font-weight: 600;
      margin-left: 20px;
      font-size: 0.95rem;
    }}
    .nav-links a:hover {{
      color: var(--gold, #ff8a5b);
    }}
    .chapter-hero {{
      padding: 35px 0 20px;
      border-bottom: 1px dashed var(--line, rgba(255, 255, 255, 0.15));
      margin-bottom: 30px;
    }}
    .back-btn {{
      display: inline-block;
      margin-bottom: 12px;
      color: var(--gold, #ff8a5b);
      text-decoration: none;
      font-weight: 700;
      font-size: 0.95rem;
    }}
    .chapter-hero h1 {{
      font-family: var(--font-heading, 'Fraunces', serif);
      font-size: 2.4rem;
      margin: 0 0 10px 0;
      color: #fff;
    }}
    .content-card {{
      background: var(--card, rgba(255, 255, 255, 0.04));
      border: 1px solid var(--line, rgba(255, 255, 255, 0.12));
      border-radius: 14px;
      padding: 28px;
      margin-bottom: 24px;
    }}
    .content-card h2, .content-card h3 {{
      font-family: var(--font-heading, 'Fraunces', serif);
      color: var(--gold, #ff8a5b);
      margin-top: 0;
    }}
    .formula-box {{
      background: rgba(0, 0, 0, 0.35);
      border-left: 4px solid var(--gold, #ff8a5b);
      padding: 18px;
      border-radius: 8px;
      margin: 18px 0;
      overflow-x: auto;
    }}
    /* Clean Solid Footer */
    .sn-footer {{
      background: #190c1a;
      border-top: 1px solid var(--line, rgba(255, 255, 255, 0.12));
      padding: 50px 0 30px;
      margin-top: 60px;
    }}
    .sn-footer-grid {{
      display: grid;
      grid-template-columns: 2fr 1fr 1fr;
      gap: 36px;
      margin-bottom: 36px;
    }}
    .sn-brand h3 {{
      font-family: var(--font-heading, 'Fraunces', serif);
      font-size: 1.4rem;
      margin: 0 0 10px 0;
      color: #fff;
    }}
    .sn-brand p {{
      color: var(--muted, #a090a0);
      font-size: 0.92rem;
      line-height: 1.6;
    }}
    .footer-col h4 {{
      font-size: 0.95rem;
      text-transform: uppercase;
      color: #fff;
      margin: 0 0 14px 0;
      letter-spacing: 0.5px;
    }}
    .footer-col ul {{
      list-style: none;
      padding: 0;
      margin: 0;
    }}
    .footer-col li {{
      margin-bottom: 8px;
    }}
    .footer-col a {{
      color: var(--muted, #a090a0);
      text-decoration: none;
      font-size: 0.9rem;
    }}
    .footer-col a:hover {{
      color: var(--gold, #ff8a5b);
    }}
    .bottom-bar {{
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      padding-top: 20px;
      text-align: center;
      color: var(--muted, #a090a0);
      font-size: 0.85rem;
    }}
    @media (max-width: 768px) {{
      .sn-footer-grid {{ grid-template-columns: 1fr; gap: 24px; }}
      .chapter-hero h1 {{ font-size: 1.9rem; }}
      .content-card {{ padding: 20px; }}
    }}
  </style>
</head>
<body>

  <header class="site-header">
    <div class="container nav-inner">
      <a class="brand-title" href="{hub_link}">Shorveer<em>Notes</em></a>
      <nav class="nav-links">
        <a href="{hub_link}">Portal Hub</a>
        <a href="[https://www.youtube.com/@JSEDIZ](https://www.youtube.com/@JSEDIZ)" target="_blank" rel="noopener noreferrer">JS EDIZ</a>
      </nav>
    </div>
  </header>

  <main class="container">
    <div class="chapter-hero">
      <a class="back-btn" href="{hub_link}">← Back to Hub</a>
      <h1>{chapter_name}</h1>
      <p style="color:var(--muted, #a090a0); margin:0;">Class 12 Science · Authored by <strong>Jatin Sandilya</strong></p>
    </div>

    {main_body}
  </main>

  <footer class="sn-footer">
    <div class="container">
      <div class="sn-footer-grid">
        <div class="sn-brand">
          <h3>Shorveer<em>Notes</em></h3>
          <p>High-yield Class 12 Science & Mathematics preparation. Concept breakdowns, verified formulas, and board derivations created with precision by <strong>Jatin Sandilya</strong>.</p>
        </div>
        <div class="footer-col">
          <h4>Subjects</h4>
          <ul>
            <li><a href="../physics/index.html">Physics</a></li>
            <li><a href="../chemistry/index.html">Chemistry</a></li>
            <li><a href="../mathematics/index.html">Mathematics</a></li>
          </ul>
        </div>
        <div class="footer-col">
          <h4>Platform</h4>
          <ul>
            <li><a href="[https://www.youtube.com/@JSEDIZ](https://www.youtube.com/@JSEDIZ)" target="_blank" rel="noopener noreferrer">JS EDIZ YouTube</a></li>
            <li><a href="mailto:support.shorveernotes@gmail.com">Contact</a></li>
          </ul>
        </div>
      </div>
      <div class="bottom-bar">
        <p>&copy; 2026 Shorveer Notes · Built with pride in India 🇮🇳</p>
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

    patch_file_errors(target_path)
    print(f"Successfully generated: {target_path}")

def main():
    pending_list = scan_website_links()
    if not pending_list:
        print("Saare chapters complete ho chuke hain! No more files pending.")
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write("has_more=false\n")
        return

    target = pending_list[0]
    print(f"Target selected: {target['chapter_name']} -> {target['target_path']}")
    build_chapter_page(target)

    remaining = len(pending_list) - 1
    print(f"Done. Remaining chapters: {remaining}")
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"has_more={'true' if remaining > 0 else 'false'}\n")

if __name__ == "__main__":
    main()
