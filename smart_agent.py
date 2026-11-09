import os
import re
import glob
import time
from bs4 import BeautifulSoup
from google import genai
from google.genai.errors import ServerError, APIError

# Ek run me 1 page (Safe & Fast)
BATCH_SIZE = 1

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY missing.")

client = genai.Client(api_key=api_key)

MATHJAX_HEADER = """
<script>
  window.MathJax = {
    tex: { inlineMath: [['$', '$'], ['\\\\(', '\\\\)']] },
    svg: { fontCache: 'global' }
  };
</script>
<script type="text/javascript" id="MathJax-script" async
  src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js">
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
                print(f"Warning: {model_name} attempt {attempt+1} failed ({e}). Retrying in 6s...")
                time.sleep(6)
            except Exception as e:
                print(f"Unexpected error with {model_name}: {e}")
                time.sleep(4)
                break
    raise RuntimeError("All Gemini models failed due to server demand.")

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

            # Agar file exist nahi karti
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

def build_chapter_page(target):
    target_path = target["target_path"]
    chapter_name = target["chapter_name"]
    source_file = target["source_file"]

    # Source index file se exact head, header, footer uthana
    with open(source_file, "r", encoding="utf-8") as f:
        src_soup = BeautifulSoup(f.read(), "html.parser")

    header_tag = src_soup.find("header", class_="site-header")
    footer_tag = src_soup.find("footer", class_="sn-footer")
    header_html = str(header_tag) if header_tag else ""
    footer_html = str(footer_tag) if footer_tag else ""

    # Subfolder level check taaki ../style.css ka relative path sahi rahe
    depth = len(os.path.normpath(target_path).split(os.sep)) - 1
    css_rel_path = ("../" * depth) + "style.css" if depth > 0 else "style.css"

    prompt = f"""
    You are writing ONLY the <main id="main"> content block for an educational chapter page.
    Chapter Name: '{chapter_name}'
    Target Subject Context: Class 12 Science / Mathematics

    Requirements:
    - Use only valid HTML tags (<section class="section container">, <div class="content-card">, etc.)
    - MathJax/LaTeX expressions ($...$ for inline, $$...$$ for display equations)
    - Section 1: Detailed Chapter Concept & Definitions
    - Section 2: Important Derivations / Key Formulas in styled callout boxes
    - Section 3: 3 Most Repeated CBSE Board Solved Questions (with detailed marking steps)
    - Section 4: Quick Summary Mind-Map points
    
    Output ONLY the HTML for the inside of <main id="main"> ... </main>. DO NOT include <!DOCTYPE>, <html>, <head>, or <footer>.
    """

    raw_content = call_gemini_with_fallback(prompt)
    main_content = clean_code(raw_content)

    # Complete document assembly matching Shorveer Notes exact design
    full_html = f"""<!DOCTYPE html>
<html lang="en" data-theme="sunset">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{chapter_name} | Shorveer Notes</title>
  
  {MATHJAX_HEADER}

  <!-- Fonts matching Index -->
  <link rel="preconnect" href="[https://fonts.googleapis.com](https://fonts.googleapis.com)">
  <link rel="preconnect" href="[https://fonts.gstatic.com](https://fonts.gstatic.com)" crossorigin>
  <link href="[https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700;1,9..144,400&family=JetBrains+Mono:wght@400;500;700&family=Karla:wght@400;500;600;700&display=swap](https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700;1,9..144,400&family=JetBrains+Mono:wght@400;500;700&family=Karla:wght@400;500;600;700&display=swap)" rel="stylesheet">

  <!-- Master Global Stylesheet -->
  <link rel="stylesheet" href="{css_rel_path}">

  <style>
    /* In-page polish for chapter reading */
    body {{
      background: var(--bg, #241226);
      color: var(--ink, #ffe9d6);
      font-family: var(--font-body, 'Karla', sans-serif);
      margin: 0;
      padding-top: 80px;
    }}
    .container {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 0 24px;
    }}
    .chapter-hero {{
      padding: 40px 0 20px;
      border-bottom: 1px dashed var(--line, rgba(255,255,255,0.15));
      margin-bottom: 35px;
    }}
    .chapter-hero h1 {{
      font-family: var(--font-heading, 'Fraunces', serif);
      font-size: 2.6rem;
      color: var(--ink, #fff);
      margin-bottom: 10px;
    }}
    .content-card {{
      background: var(--card, rgba(255, 255, 255, 0.04));
      border: 1px solid var(--line, rgba(255, 255, 255, 0.12));
      border-radius: 14px;
      padding: 28px;
      margin-bottom: 28px;
      backdrop-filter: blur(10px);
    }}
    .content-card h2, .content-card h3 {{
      font-family: var(--font-heading, 'Fraunces', serif);
      color: var(--gold, #ff8a5b);
      margin-bottom: 14px;
    }}
    .formula-highlight {{
      background: rgba(0,0,0,0.3);
      border-left: 3px solid var(--gold, #ff8a5b);
      padding: 16px 20px;
      border-radius: 8px;
      margin: 16px 0;
      overflow-x: auto;
    }}
    a.back-nav {{
      display: inline-block;
      margin-bottom: 20px;
      color: var(--gold, #ff8a5b);
      text-decoration: none;
      font-weight: 700;
    }}
  </style>
</head>
<body>
  {header_html}

  <main id="main">
    <div class="container">
      <div class="chapter-hero">
        <a class="back-nav" href="index.html">← Back to Mathematics Hub</a>
        <h1>{chapter_name}</h1>
        <p style="color:var(--muted, #a090a0);">Curated for CBSE Class 12 · High-Yield Revision</p>
      </div>

      {main_content}
    </div>
  </main>

  {footer_html}
</body>
</html>"""

    parent_dir = os.path.dirname(target_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Generated & aligned with theme: {target_path}")

def main():
    pending_list = scan_website_links()
    if not pending_list:
        print("Koi missing chapter nahi mila.")
        return

    target = pending_list[0]
    print(f"Generating single page: {target['chapter_name']} -> {target['target_path']}")
    build_chapter_page(target)

if __name__ == "__main__":
    main()
