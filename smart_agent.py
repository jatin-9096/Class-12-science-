import os
import re
import glob
from bs4 import BeautifulSoup
from google import genai

# Ek run me kitne missing chapters process karne hain
BATCH_SIZE = 3

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

# In non-educational links ko skip karega taaki tokens aur files waste na hon
IGNORE_KEYWORDS = ["privacy", "terms", "cookie", "disclaimer", "about", "contact"]

def extract_site_template():
    existing_files = glob.glob("**/*.html", recursive=True)
    css_block = ""
    navbar_block = ""
    footer_block = ""

    for file_path in existing_files:
        if os.path.getsize(file_path) > 400:
            with open(file_path, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
                
                style_tag = soup.find("style")
                if style_tag and not css_block:
                    css_block = str(style_tag)
                
                nav_tag = soup.find("nav") or soup.find(class_=re.compile(r"nav|header", re.I))
                if nav_tag and not navbar_block:
                    navbar_block = str(nav_tag)
                
                foot_tag = soup.find("footer")
                if foot_tag and not footer_block:
                    footer_block = str(foot_tag)
                
                if css_block and navbar_block:
                    break
                    
    return css_block, navbar_block, footer_block

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

            # Skip policy/legal pages
            if any(k in clean_href.lower() or k in chapter_name.lower() for k in IGNORE_KEYWORDS):
                continue

            # Leading slash remove karna zaroori hai taaki root folder error na de
            normalized_href = clean_href.lstrip("/\\")

            # Hamesha repository ke base dir ke relative path banayega
            target_path = os.path.normpath(os.path.join(base_dir, normalized_href))

            if not os.path.exists(target_path) and target_path not in seen_paths:
                seen_paths.add(target_path)
                pending_targets.append({
                    "target_path": target_path,
                    "chapter_name": chapter_name if chapter_name else os.path.splitext(os.path.basename(normalized_href))[0],
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

def patch_file_errors(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    unclosed_tags = []
    for tag in ["html", "head", "body", "main", "style", "script"]:
        open_count = len(re.findall(rf"<{tag}\b", content, re.I))
        close_count = len(re.findall(rf"</{tag}>", content, re.I))
        if open_count > close_count:
            unclosed_tags.append(tag)

    if unclosed_tags:
        error_segment = content[-1500:]
        prompt = f"""
        Fix only the truncated or broken end section of this HTML.
        Unclosed tags detected: {unclosed_tags}.
        Do not recreate the whole document. Return ONLY the closing patch code needed to properly close all open elements and finalize the document.
        Snippet:
        {error_segment}
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        patch = clean_code(response.text)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("\n" + patch)

def build_missing_chapter(target, css_block, navbar_block, footer_block):
    target_path = target["target_path"]
    chapter_name = target["chapter_name"]
    
    parent_dir = os.path.dirname(target_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    prompt = f"""
    Build a complete, responsive HTML chapter page for: '{chapter_name}'.
    Target file path: '{target_path}'.
    
    Use this exact styling block:
    {css_block}
    
    Navbar structure to include:
    {navbar_block}
    
    Footer structure to include:
    {footer_block}
    
    MathJax & Content Requirements:
    1. Include full LaTeX/MathJax expressions using $...$ for inline and $$...$$ for display formulas.
    2. Chapter Overview and Key Definitions.
    3. Essential Formulas, Reactions, or Theorems.
    4. Important CBSE Board Exam Standard Questions with step-by-step solutions.
    5. Quick Revision summary block.
    
    Return ONLY valid, complete HTML.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    generated_html = clean_code(response.text)

    if "MathJax-script" not in generated_html:
        if "<head>" in generated_html:
            generated_html = generated_html.replace("<head>", f"<head>\n{MATHJAX_HEADER}")
        else:
            generated_html = MATHJAX_HEADER + "\n" + generated_html

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(generated_html)

    patch_file_errors(target_path)

def main():
    pending_list = scan_website_links()
    if not pending_list:
        print("Koi missing chapter nahi mila.")
        return

    targets_to_process = pending_list[:BATCH_SIZE]
    css_block, navbar_block, footer_block = extract_site_template()

    print(f"Total missing: {len(pending_list)} | Is run me process ho rahe hain: {len(targets_to_process)}")

    for idx, target in enumerate(targets_to_process, 1):
        print(f"[{idx}/{len(targets_to_process)}] Generating: {target['chapter_name']} -> {target['target_path']}")
        build_missing_chapter(target, css_block, navbar_block, footer_block)

if __name__ == "__main__":
    main()
