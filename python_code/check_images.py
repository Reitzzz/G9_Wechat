import sys
import re

from config import MARKDOWN_DIR, HTML_DIR

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

files = sorted(list(MARKDOWN_DIR.glob("*.md"))) + sorted(list(HTML_DIR.glob("*.html")))

total_tags = 0
found = 0
missing = 0
broken_list = []

for f in files:
    text = f.read_text(encoding="utf-8")
    md_imgs = re.findall(r'!\[.*?\]\((.*?)\)', text)
    html_imgs = re.findall(r'<img[^>]+src=["\'](.*?)["\']', text)
    all_imgs = md_imgs + html_imgs
    total_tags += len(all_imgs)

    for img in all_imgs:
        img_clean = img.split("?")[0].split("#")[0].strip()
        if img_clean.startswith("http"):
            missing += 1
            broken_list.append((f.name, img, "HTTP link"))
        elif img_clean.startswith("../"):
            # relative to the file's own dir (markdown/ 或 html/)
            target = (f.parent / img_clean).resolve()
            if target.exists():
                found += 1
            else:
                missing += 1
                broken_list.append((f.name, img, "Target file does not exist"))
        else:
            missing += 1
            broken_list.append((f.name, img, "Non-relative path"))

print(f"Total Markdown files: {len(files)}")
print(f"Total image references: {total_tags}")
print(f"Valid local files found: {found}")
print(f"Broken references: {missing}")

if broken_list:
    print("\nFirst 10 broken references:")
    for fn, img, reason in broken_list[:10]:
        print(f"[{fn}] -> {img} ({reason})")
