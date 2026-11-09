import os
import re
import glob
import time
from bs4 import BeautifulSoup
from google import genai
from google.genai.errors import ServerError, APIError

BATCH_SIZE = 1
API_COOLDOWN = 20  # Rate-limit safety cooldown in seconds
MIN_FILE_SIZE = 250 * 1024  # 250 KB minimum target

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable is missing.")

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

# Subject signatures to catch mismatches across folders
SUBJECT_SIGNATURES = {
    "mathematics": {
        "forbidden": ["arrhenius", "chemical kinetics", "activation energy", "reaction rate", "reactant", "haloalkane", "sn1", "sn2", "alcohols phenols", "aldehyde", "ketone"]
    },
    "physics": {
        "forbidden": ["reaction mechanism", "organic chemistry", "haloalkanes", "aldol condensation", "coordination compounds"]
    },
    "chemistry": {
        "forbidden": ["direction cosines", "shortest distance between skew lines", "matrix adjoint", "integration by parts dx"]
    }
}

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
                print(f"Demand spike on {model_name} (Attempt {attempt+1}). Retrying in 10s...")
                time.sleep(10)
            except Exception as e:
                print(f"Error calling {model_name}: {e}")
                time.sleep(5)
                break
    raise RuntimeError("All Gemini API models failed after retries.")

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

def is_content_mismatched(file_path, subject):
    sub_key = subject.lower()
    if sub_key not in SUBJECT_SIGNATURES:
        return False
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read().lower()
        forbidden = SUBJECT_SIGNATURES[sub_key]["forbidden"]
        violations = [w for w in forbidden if w in text]
        if len(violations) >= 2:
            return True
    except Exception:
        pass
    return False

def target_in_place_patch(file_path):
    """In-place localized patcher: fixes unclosed tags without rewriting 250KB content"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        unclosed = []
        for tag in ["html", "head", "body", "main", "article", "section", "div"]:
            open_c = len(re.findall(rf"<{tag}\b", content, re.I))
            close_c = len(re.findall(rf"</{tag}>", content, re.I))
            if open_c > close_c:
                unclosed.append(tag)

        if unclosed:
            print(f"Applying in-place tag patch in {file_path}: {unclosed}")
            patch_str = "\n" + "\n".join([f"</{tag}>" for tag in reversed(unclosed)]) + "\n"
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(patch_str)
    except Exception as e:
        print(f"Error in tag patching: {e}")

def scan_and_audit_website():
    """Scans whole website: detects missing files, small files, or mismatched content"""
    seen_paths = set()
    html_files = glob.glob("**/*.html", recursive=True)

    for source_file in html_files:
        base_dir = os.path.dirname(source_file)
        try:
            with open(source_file, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
        except Exception:
            continue

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
            filename = os.path.basename(target_path).lower()

            if filename in ["index.html", "about.html", "about-notes.html", "exam-info.html"]:
                continue

            if target_path in seen_paths:
                continue

            seen_paths.add(target_path)
            subject = detect_subject(target_path)

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

            is_part_2 = "part2" in filename or "pyq" in filename
            clean_title = re.sub(r"\s*\(?(Part\s*[12]|PYQs?)\)?", "", title_text, flags=re.I).strip()

            # 1. Condition: Missing File
            if not os.path.exists(target_path):
                return {
                    "action": "create",
                    "target_path": target_path,
                    "chapter_name": clean_title,
                    "subject": subject,
                    "is_part_2": is_part_2,
                    "reason": "Missing File"
                }

            # 2. Condition: Content Mismatch (e.g., Chemistry in Maths)
            if is_content_mismatched(target_path, subject):
                return {
                    "action": "fix_mismatch",
                    "target_path": target_path,
                    "chapter_name": clean_title,
                    "subject": subject,
                    "is_part_2": is_part_2,
                    "reason": "Subject Mismatch Detected (Replacing inner content)"
                }

            # 3. Condition: File too small (Under size target)
            file_size = os.path.getsize(target_path)
            if file_size < MIN_FILE_SIZE:
                return {
                    "action": "create",
                    "target_path": target_path,
                    "chapter_name": clean_title,
                    "subject": subject,
                    "is_part_2": is_part_2,
                    "reason": f"File size too small ({file_size // 1024} KB < 250 KB target)"
                }

    return None

def generate_part1_content(subject, chapter_name):
    """Generates 250KB+ Deep Academic Theory, Complete Derivations, and Comprehensive Laws"""
    print(f"--> [Chunk 1/2] Drafting In-depth Theory for {chapter_name} ({subject})...")
    p1 = f"""
    Act as a Senior CBSE Board Examiner and Textbook Author in Class 12 {subject}.
    Write a massive, mathematically and scientifically rigorous conceptual breakdown for: '{chapter_name}'.
    
    Requirements:
    1. Provide extensive introductory context, definitions, core laws, conditions, and graphical variations for Class 12 {subject}.
    2. Write minimum 3500+ words of granular explanations. Avoid any placeholder text or short summaries.
    
    Structure:
    <section class="section container" id="theory">
      <div class="section-head">
        <span class="section-eyebrow">Comprehensive Theory</span>
        <h2>1. Complete Conceptual Framework & Definitions</h2>
      </div>
      <div class="real-life">
        <article class="rl-card" style="--rl-color: #bf5a3c">
          <div class="rl-body">
            <div class="rl-title">Fundamental Theoretical Principles</div>
            <p class="rl-text"><!-- Massive theoretical body --></p>
          </div>
        </article>
      </div>
    </section>
    Return ONLY this valid HTML section.
    """
    chunk1 = clean_code(call_gemini_with_fallback(p1))
    print(f"Waiting {API_COOLDOWN}s for API cooldown...")
    time.sleep(API_COOLDOWN)

    print(f"--> [Chunk 2/2] Drafting Complete Derivation Bank & Exhaustive Formula Tables...")
    p2 = f"""
    Continue Class 12 {subject} notes for Chapter: '{chapter_name}'.
    Provide the exhaustive Derivation Bank and Formula/Equation Repository.
    
    Requirements:
    1. Full multi-step mathematical proofs for all CBSE standard derivations using MathJax ($...$ for inline, $$...$$ for display equations).
    2. A comprehensive formula table listing variables, SI units, and conditions.
    
    Structure:
    <section class="section container" id="derivations">
      <div class="section-head">
        <span class="section-eyebrow">Formula Repository</span>
        <h2>2. Master Equation Bank & Step-by-Step Derivations</h2>
      </div>
      <div class="resource-grid">
        <article class="resource">
          <h3>Exhaustive Formula Table</h3>
          <!-- Comprehensive list of all formulas & derivations -->
        </article>
      </div>
    </section>
    Return ONLY this valid HTML section.
    """
    chunk2 = clean_code(call_gemini_with_fallback(p2))

    return f"{chunk1}\n\n{chunk2}"

def generate_part2_content(subject, chapter_name):
    """Generates 250KB+ Solved Board PYQs, Competency Case Studies, and Mind-Maps"""
    print(f"--> [Chunk 1/2] Drafting Solved CBSE Board PYQs for {chapter_name} ({subject})...")
    p1 = f"""
    Act as a CBSE Chief Head Evaluator in Class 12 {subject}.
    Write a comprehensive Solved Board Question Bank for: '{chapter_name}'.
    
    Requirements:
    1. Exactly 8 full-length solved CBSE Board Past 10-Year Questions:
       - 2 Long Answer Questions (5-Markers) with step-by-step marking scheme allocations.
       - 3 Medium Application Questions (3-Markers).
       - 3 Conceptual & Numerical Traps (2-Markers).
    2. Write every mathematical equation with MathJax.
    
    Structure:
    <section class="section container" id="pyqs">
      <div class="section-head">
        <span class="section-eyebrow">Board Examination Archive</span>
        <h2>1. Solved CBSE Board Past Year Questions (Marking Scheme Aligned)</h2>
      </div>
      <div class="resource-grid">
        <!-- 8 solved question articles with .resource-icon and .qa-box -->
      </div>
    </section>
    Return ONLY this valid HTML section.
    """
    chunk1 = clean_code(call_gemini_with_fallback(p1))
    print(f"Waiting {API_COOLDOWN}s for API cooldown...")
    time.sleep(API_COOLDOWN)

    print(f"--> [Chunk 2/2] Drafting Competency-Based Case Studies & Visual Mind-Map...")
    p2 = f"""
    Continue Part 2 of Class 12 {subject} notes for: '{chapter_name}'.
    
    Requirements:
    1. 2 Competency-Based Case-Study Questions with paragraph passages, multiple sub-parts, and detailed solutions.
    2. High-Yield Visual Mind-Map and Fast Revision Checklist.
    3. Common student blunders and examiner traps warning box.
    
    Structure:
    <section class="section container" id="case-studies">
      <div class="section-head">
        <span class="section-eyebrow">Competency Assessment</span>
        <h2>2. Case-Study Scenarios & Application Problems</h2>
      </div>
      <div class="resource-grid">
        <!-- 2 extensive case study articles -->
      </div>
    </section>

    <section class="section container" id="mindmap">
      <div class="section-head">
        <span class="section-eyebrow">Revision Framework</span>
        <h2>3. Concept Mind-Map & Examiner Traps Checklist</h2>
      </div>
      <div class="trust">
        <div class="trust-inner container">
          <div class="trust-item"><b>Visual Framework</b>Mindmap steps</div>
          <div class="trust-item"><b>Examiner Traps</b>Common mistakes</div>
          <div class="trust-item"><b>Scoring Strategy</b>Step-marking tips</div>
        </div>
      </div>
    </section>
    Return ONLY these valid HTML sections.
    """
    chunk2 = clean_code(call_gemini_with_fallback(p2))

    return f"{chunk1}\n\n{chunk2}"

def fix_mismatch_in_place(target):
    """Keeps the layout, header, footer intact and replaces ONLY the inner mismatched content"""
    target_path = target["target_path"]
    chapter_name = target["chapter_name"]
    subject = target["subject"]
    is_part_2 = target["is_part_2"]

    print(f"\n[IN-PLACE FIX] Overwriting inner content for: {target_path} -> {subject}: {chapter_name}")
    
    if is_part_2:
        new_content = generate_part2_content(subject, chapter_name)
    else:
        new_content = generate_part1_content(subject, chapter_name)

    with open(target_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    main_tag = soup.find("main")
    if main_tag:
        hero = main_tag.find("section", class_="hero")
        cta = main_tag.find("section", class_="final-cta")
        main_tag.clear()
        if hero: 
            main_tag.append(hero)
        main_tag.append(BeautifulSoup(new_content, "html.parser"))
        if cta: 
            main_tag.append(cta)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(str(soup))
        target_in_place_patch(target_path)
        print(f"Successfully fixed content mismatch in: {target_path}")
    else:
        # Fallback to full page build if main tag was broken
        build_full_page(target)

def build_full_page(target):
    target_path = target["target_path"]
    chapter_name = target["chapter_name"]
    subject = target["subject"]
    is_part_2 = target["is_part_2"]

    depth = len(os.path.normpath(target_path).split(os.sep)) - 1
    css_rel = ("../" * depth) + "style.css" if depth > 0 else "style.css"
    hub_link = "index.html" if depth == 1 else "../index.html"
    root_link = "../index.html" if depth == 1 else "index.html"

    base_name = os.path.splitext(os.path.basename(target_path))[0]
    clean_base = re.sub(r"(_part[12]|\.html)", "", base_name, flags=re.I)
    part1_url = f"{clean_base}.html" if "part" not in base_name else f"{clean_base}_part1.html"
    part2_url = f"{clean_base}_part2.html"

    part_subtitle = "Part 2: Solved Board PYQs & Case Studies" if is_part_2 else "Part 1: In-Depth Theory & Complete Derivations"
    switch_btn = f"""
    <div style="margin: 30px 0; text-align: center;">
      <a class="btn btn-gold" href="{part1_url if is_part_2 else part2_url}" style="padding: 14px 28px; font-size: 1.05rem;">
        {'← Back to Part 1: Theory & Formulas' if is_part_2 else 'Continue to Part 2: Solved CBSE PYQs & Case Studies →'}
      </a>
    </div>
    """

    if is_part_2:
        body_content = generate_part2_content(subject, chapter_name)
    else:
        body_content = generate_part1_content(subject, chapter_name)

    full_html = f"""<!DOCTYPE html>
<html lang="en" data-theme="sunset">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="CBSE Class 12 {subject} - {chapter_name} ({part_subtitle}). Comprehensive theory, derivations, formulas, and solved board PYQs by Jatin Sandilya at Shorveer Notes.">
  <meta name="author" content="Jatin Sandilya">
  <meta name="robots" content="index, follow">
  <title>{chapter_name} ({'Part 2' if is_part_2 else 'Part 1'}) · Class 12 {subject} | Shorveer Notes</title>

  {MATHJAX_HEADER}

  <!-- Fonts -->
  <link rel="preconnect" href="[https://fonts.googleapis.com](https://fonts.googleapis.com)">
  <link rel="preconnect" href="[https://fonts.gstatic.com](https://fonts.gstatic.com)" crossorigin>
  <link href="[https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700&family=JetBrains+Mono:wght@400;500;700&family=Karla:wght@400;500;600;700&display=swap](https://fonts.googleapis.com/css2?family=Caveat:wght@500;700&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700&family=JetBrains+Mono:wght@400;500;700&family=Karla:wght@400;500;600;700&display=swap)" rel="stylesheet">

  <link rel="stylesheet" href="{css_rel}">

  <style>
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
      background: rgba(23, 22, 19, 0.95);
      backdrop-filter: blur(14px);
      border-bottom: 1px solid var(--line, rgba(255, 255, 255, 0.15));
      z-index: 1000;
      display: flex;
      align-items: center;
    }}
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
    }}
    .toc-bar {{
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--line, rgba(255, 255, 255, 0.12));
      border-radius: 12px;
      padding: 16px 24px;
      margin-bottom: 40px;
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      align-items: center;
    }}
    .toc-title {{
      font-family: var(--font-mono, monospace);
      font-size: 0.85rem;
      color: var(--gold, #ff8a5b);
      text-transform: uppercase;
      font-weight: 700;
    }}
    .toc-link {{
      color: var(--ink, #ffe9d6);
      text-decoration: none;
      font-size: 0.92rem;
      transition: color 0.2s;
    }}
    .toc-link:hover {{
      color: var(--gold, #ff8a5b);
      text-decoration: underline;
    }}
    .sn-cookie-banner {{
      position: fixed;
      bottom: 20px;
      left: 20px;
      right: 20px;
      max-width: 500px;
      background: #1c1b18;
      border: 1px solid var(--line, rgba(255, 255, 255, 0.2));
      border-radius: 12px;
      padding: 18px;
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.6);
      z-index: 9999;
      display: none;
    }}
    .sn-cookie-banner.show {{
      display: block;
    }}
    .sn-cookie-banner p {{
      margin: 0 0 12px;
      font-size: 0.88rem;
      color: var(--muted, #ffb87a);
      line-height: 1.5;
    }}
    .sn-cookie-btn {{
      background: var(--gold, #ff8a5b);
      color: #000;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-weight: 700;
      cursor: pointer;
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
    }}
    .sn-footer {{
      background: #141311 !important;
      border-top: 1px solid var(--line, rgba(255, 255, 255, 0.12));
      padding: 60px 0 35px;
      margin-top: 80px;
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

  <!-- ============ SITE HEADER ============ -->
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
        <button class="nav-icon" id="themeButton" aria-label="Change theme" style="background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.15); border-radius:8px; padding:8px; cursor:pointer;">
          <span style="width:14px; height:14px; border-radius:50%; background:var(--gold, #ff8a5b); display:inline-block;"></span>
        </button>
      </div>
    </nav>
  </header>

  <!-- ============ THEME PICKER ============ -->
  <div class="theme-pop" id="themePop">
    <h4 style="margin:0 0 8px; color:#fff;">Pick a look</h4>
    <div class="theme-grid">
      <button class="theme-opt" data-theme-value="notebook">Notebook</button>
      <button class="theme-opt" data-theme-value="chalkboard">Chalkboard</button>
      <button class="theme-opt" data-theme-value="blueprint">Blueprint</button>
      <button class="theme-opt" data-theme-value="sunset">Sunset</button>
    </div>
  </div>

  <main id="main">
    <section class="hero container">
      <div class="hero-copy">
        <div class="kicker">
          <span class="dot"></span>
          <span>CBSE Class 12 · {subject} Master Guide</span>
        </div>
        <h1>{chapter_name}</h1>
        <p class="hero-description">{part_subtitle} curated for rigorous CBSE Board Preparation.</p>
        <div class="hero-note">
          <span>Authored with Precision by <strong>Jatin Sandilya</strong> · Official 2026-27 Syllabus</span>
        </div>
      </div>
    </section>

    <div class="container">
      <div class="toc-bar">
        <span class="toc-title">Quick Navigation:</span>
        {'<a class="toc-link" href="#theory">1. In-Depth Theory</a><a class="toc-link" href="#derivations">2. Complete Derivations & Formulas</a>' if not is_part_2 else '<a class="toc-link" href="#pyqs">1. Solved CBSE PYQs</a><a class="toc-link" href="#case-studies">2. Competency Case Studies</a><a class="toc-link" href="#mindmap">3. Mind-Map Checklist</a>'}
      </div>
    </div>

    <div class="container">
      {switch_btn}
    </div>

    {body_content}

    <div class="container">
      {switch_btn}
    </div>

    <section class="final-cta container reveal">
      <div class="cta-content">
        <h2>Mastered {chapter_name}? <em>Return to {subject} Hub.</em></h2>
        <a class="btn btn-gold" href="{hub_link}">
          Back to {subject} Hub →
        </a>
      </div>
    </section>
  </main>

  <!-- ============ FOOTER ============ -->
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
          <h3 style="color:#fff; font-size:1rem; margin-bottom:14px;">Subject Hubs</h3>
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
            <li><a href="mailto:support.shorveernotes@gmail.com">Contact Support</a></li>
          </ul>
        </div>
      </div>

      <div style="border-top:1px solid rgba(255,255,255,0.08); padding-top:20px; text-align:center; color:var(--muted); font-size:0.85rem;">
        <p>&copy; 2026 Shorveer Notes · Built with pride in India 🇮🇳</p>
      </div>
    </div>
  </footer>

  <!-- ============ COOKIE BANNER ============ -->
  <aside class="sn-cookie-banner" id="cookieBanner" role="dialog" aria-label="Cookie and Storage Notice">
    <p>
      🍪 <strong>Transparent Storage Notice:</strong> Shorveer Notes uses browser local storage exclusively to preserve your chosen theme settings (Notebook, Sunset, Chalkboard, Blueprint) across study sessions. We do not use intrusive tracking cookies.
    </p>
    <button class="sn-cookie-btn" id="cookieAcceptBtn">Got it, proceed</button>
  </aside>

  <script>
    const themeBtn = document.getElementById("themeButton");
    const themePop = document.getElementById("themePop");
    const themeOpts = document.querySelectorAll(".theme-opt");
    const cookieBanner = document.getElementById("cookieBanner");
    const cookieAcceptBtn = document.getElementById("cookieAcceptBtn");

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

    try {{
      if (!localStorage.getItem("shorveer-cookie-ack")) {{
        cookieBanner.classList.add("show");
      }}
    }} catch(e) {{}}

    cookieAcceptBtn.addEventListener("click", () => {{
      cookieBanner.classList.remove("show");
      try {{ localStorage.setItem("shorveer-cookie-ack", "true"); }} catch(e) {{}}
    }});
  </script>
</body>
</html>"""

    parent_dir = os.path.dirname(target_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    
    target_in_place_patch(target_path)
    print(f"Generated Comprehensive {os.path.getsize(target_path) // 1024} KB Guide: {target_path}")

def main():
    target = scan_and_audit_website()
    if not target:
        print("All chapters across the entire website are 100% healthy, matched, and complete (250KB+ target met).")
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write("has_more=false\n")
        return

    print(f"\n==================================================")
    print(f"[ACTION: {target['action'].upper()}] -> {target['target_path']}")
    print(f"Subject: {target['subject']} | Chapter: {target['chapter_name']}")
    print(f"Health Audit Reason: {target['reason']}")
    print(f"==================================================")

    if target["action"] == "fix_mismatch":
        fix_mismatch_in_place(target)
    else:
        build_full_page(target)

    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write("has_more=true\n")

if __name__ == "__main__":
    main()
