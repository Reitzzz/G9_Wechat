"""全库体检：对 121 篇文章的 md / html / 图片 / 索引做一致性检查。

检查项：
  A. 配对与命名      md/html/图片目录三方 stem 一致、命名规范、序号唯一
  B. Markdown       编码、头部格式、H1 与文件名一致、日期一致、无残留
  C. HTML           编码、img 引用全部本地化、无 data-src 残留
  D. 图片           引用可解析（同 check_images）、孤儿文件
  E. 索引与目录     articles_index / download_status / README / CATALOG 与磁盘一致
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MD = BASE / "articles" / "markdown"
HTML = BASE / "articles" / "html"
IMG = BASE / "articles" / "images"
INDEX = BASE / "data" / "articles_index.json"
STATUS = BASE / "data" / "download_status.json"

NAME_RE = re.compile(r"^(\d{4})年(\d{2})月(\d{2})日_(\d{4})_(.+)$")
HEAD_RE = re.compile(
    r"^# (?P<title>[^\n]+)\n\n"
    r"> 本文转载自微信公众号 \*\*(?P<author>[^*]+)\*\*，已获作者授权。  \n"
    r"> 原文发布于 (?P<date>\d{4}年\d{1,2}月\d{1,2}日 \d{1,2}:\d{2})  \n"
    r"> 原文链接：\[mp\.weixin\.qq\.com\]\((?P<url>https?://[^)]+)\)\n\n"
    r"---\n\n"
)

fails, warns = [], []


def fail(check, detail):
    fails.append((check, detail))


def warn(check, detail):
    warns.append((check, detail))


def read(p: Path):
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    if bom:
        raw = raw[3:]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return None, bom, e
    return text.replace("\r\n", "\n"), bom, None


def md_image_refs(text):
    return re.findall(r"!\[.*?\]\(([^)]+)\)", text) + re.findall(
        r"<img[^>]+(?<![-\w])src=[\"']([^\"']+)[\"']", text
    )


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    md_files = sorted(MD.glob("*.md"))
    html_files = sorted(HTML.glob("*.html"))
    img_dirs = sorted(d for d in IMG.iterdir() if d.is_dir())

    # ---- A. 配对与命名 ----
    md_stems = [p.stem for p in md_files]
    html_stems = [p.stem for p in html_files]
    dir_stems = [d.name for d in img_dirs]
    if md_stems != html_stems:
        fail("A1 md/html 配对", f"集合差异: {set(md_stems) ^ set(html_stems)}")
    if md_stems != dir_stems:
        fail("A1 md/图片目录 配对", f"集合差异: {set(md_stems) ^ set(dir_stems)}")

    bad_names = [s for s in md_stems if not NAME_RE.match(s)]
    if bad_names:
        fail("A2 命名规范", f"{len(bad_names)} 个不符合 YYYY年MM月DD日_NNNN_标题: {bad_names[:5]}")

    idx_dup = [k for k, v in Counter(NAME_RE.match(s).group(4) for s in md_stems if NAME_RE.match(s)).items() if v > 1]
    if idx_dup:
        fail("A3 序号唯一", f"重复序号: {idx_dup}")

    # ---- B. Markdown ----
    orphan_imgs = Counter()
    md_refs_by_stem = {}
    for p in md_files:
        stem = p.stem
        text, bom, err = read(p)
        if err is not None:
            fail("B1 md 编码", f"{stem[:40]}: {err}")
            continue
        if "\ufffd" in text:
            fail("B1 md 乱码字符", f"{stem[:40]}: 含 U+FFFD")
        if bom:
            warn("B1 md BOM", stem[:40])

        m = HEAD_RE.match(text)
        if not m:
            fail("B2 md 头部格式", f"{stem[:40]}: 声明块不匹配标准格式")
            continue

        nm = NAME_RE.match(stem)
        h1_norm = re.sub(r'[\\/*?:"<>|]', "_", m.group("title").strip())
        if h1_norm != nm.group(5).strip():
            warn("B3 H1 与文件名", f"{stem[:36]}: H1={m.group('title').strip()[:24]!r}")
        if not m.group("url").rstrip("/").startswith(("http://mp.weixin.qq.com", "https://mp.weixin.qq.com")):
            fail("B4 原文链接域名", f"{stem[:40]}: {m.group('url')[:60]}")
        d = m.group("date")
        if (d[:4], re.search(r"(\d{1,2})月", d).group(1), re.search(r"月(\d{1,2})日", d).group(1)) != (
            nm.group(1), str(int(nm.group(2))), str(int(nm.group(3)))
        ):
            fail("B5 日期与文件名", f"{stem[:36]}: 声明块 {d} vs 文件 {nm.group(1)}年{nm.group(2)}月{nm.group(3)}日")

        if text.lstrip("\ufeff").startswith("---") or "original_url:" in text or "\ndigest:" in text:
            fail("B6 frontmatter 残留", stem[:40])
        if re.search(r"<script", text, re.I):
            fail("B7 md 含 script", stem[:40])

        body = text[m.end():]
        if len(body.strip()) < 50:
            fail("B8 md 正文过短", f"{stem[:40]}: {len(body.strip())} 字符")

        # 4 空格缩进行（论坛会渲染成代码块）
        indented = [l for l in body.split("\n") if re.match(r"^ {4}\S", l)]
        if indented:
            warn("B9 md 4空格缩进行", f"{stem[:36]}: {len(indented)} 行，如 {indented[0][:40]!r}")

        md_ref_names = set()
        for ref in md_image_refs(text):
            if ref.startswith("http"):
                fail("B10 md 远程图片", f"{stem[:36]}: {ref[:60]}")
            elif ref.startswith("../images/"):
                if not (p.parent / ref).resolve().exists():
                    fail("B10 md 图片缺失", f"{stem[:36]}: {ref}")
                md_ref_names.add(Path(ref).name)
                orphan_imgs[(Path(ref).parent.name, Path(ref).name)] += 1
            else:
                fail("B10 md 异常图片路径", f"{stem[:36]}: {ref[:60]}")
        md_refs_by_stem[stem] = md_ref_names

    # ---- C. HTML ----
    html_refs_by_stem = {}
    html_has_video = {}
    for p in html_files:
        stem = p.stem
        text, bom, err = read(p)
        if err is not None:
            fail("C1 html 编码", f"{stem[:40]}: {err}")
            continue
        if "\ufffd" in text:
            fail("C1 html 乱码字符", f"{stem[:40]}: 含 U+FFFD")
        if p.stat().st_size < 200:
            fail("C2 html 过小", f"{stem[:40]}: {p.stat().st_size}B")
        html_ref_names = set()
        for tag in re.finditer(r"<img[^>]*>", text):
            tag = tag.group(0)
            src = re.search(r'''(?<![-\w])src=["\']([^"\']*)["\']''', tag)
            val = src.group(1) if src else ""
            if val == "":
                fail("C3 空 src 图片标签", f"{stem[:36]}: {tag[:100]}")
            elif val.startswith("http"):
                fail("C3 远程图片", f"{stem[:36]}: {val[:60]}")
            elif val.startswith("data:"):
                fail("C3 data-uri 图片", stem[:36])
            elif val.startswith("../images/"):
                if not (p.parent / val).resolve().exists():
                    fail("C3 图片缺失", f"{stem[:36]}: {val}")
                html_ref_names.add(Path(val).name)
                orphan_imgs[(Path(val).parent.name, Path(val).name)] += 1
            else:
                fail("C3 异常图片路径", f"{stem[:36]}: {val[:60]}")
            if re.search(r'''data-src=["\']https?:''', tag):
                fail("C3 img 残留 http data-src", f"{stem[:36]}: {tag[:100]}")
        html_refs_by_stem[stem] = html_ref_names
        html_has_video[stem] = "video_iframe" in text
        # 视频/音频播放器等非 img 元素的 data-src 属惰性残留，不算问题

    # B/C 图片引用集合一致性；仅 md 多出的视频封面属预期差异（html 保留
    # 微信播放器结构，本地不可播），降为 WARN
    for stem in md_refs_by_stem:
        a, b = md_refs_by_stem[stem], html_refs_by_stem.get(stem, set())
        if a == b:
            continue
        if a - b and not (b - a) and html_has_video.get(stem):
            warn("C4 视频封面仅md有", f"{stem[:36]}: {sorted(a - b)[:3]}")
        else:
            fail("C4 md/html 图片引用不一致",
                 f"{stem[:36]}: 仅md有 {sorted(a - b)[:3]} / 仅html有 {sorted(b - a)[:3]}")

    # ---- D. 孤儿图片 ----
    orphans = []
    for d in img_dirs:
        for f in d.iterdir():
            if orphan_imgs[(d.name, f.name)] == 0:
                orphans.append(str(f.relative_to(BASE)))
    if orphans:
        warn("D1 未被引用的孤儿图片", f"{len(orphans)} 个: {orphans[:8]}")

    # ---- E. 索引与目录 ----
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    disk_set = set(md_stems)
    for it in index:
        fn = it.get("file_name", "")
        if Path(fn).stem not in disk_set:
            fail("E1 索引 file_name 失配", f"#{it.get('index')} {fn[:50]}")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    n_status_bad = 0
    for link, v in status.items():
        if not isinstance(v, dict) or v.get("status") != "success":
            continue
        for key in ("md_file", "html_file"):
            rel = v.get(key, "")
            if rel and not (BASE / "articles" / rel).exists():
                n_status_bad += 1
                if n_status_bad <= 3:
                    fail("E2 download_status 路径失效", f"{rel[:60]}")
    if n_status_bad > 3:
        fail("E2 download_status 路径失效", f"…共 {n_status_bad} 处")

    readme = (BASE / "README.md").read_text(encoding="utf-8")
    for cat in ("README.md", "articles/CATALOG.md"):
        t = readme if cat == "README.md" else (BASE / "articles" / "CATALOG.md").read_text(encoding="utf-8")
        bad_links = [l for l in re.findall(r"\]\(markdown/([^)]+)\)", t) if Path(BASE, "articles", "markdown", l).stem not in disk_set]
        if bad_links:
            fail("E3 目录链接失效", f"{cat}: {bad_links[:5]}")

    # ---- 汇总 ----
    print("=" * 62)
    print(f"检查范围: md {len(md_files)} / html {len(html_files)} / 图片目录 {len(img_dirs)}")
    print(f"FAIL {len(fails)} 项, WARN {len(warns)} 项")
    print("=" * 62)
    by_check = {}
    for c, d in fails:
        by_check.setdefault(c, []).append(d)
    for c in sorted(by_check):
        print(f"\n[FAIL] {c} ({len(by_check[c])})")
        for d in by_check[c][:10]:
            print(f"   {d}")
    by_check_w = {}
    for c, d in warns:
        by_check_w.setdefault(c, []).append(d)
    for c in sorted(by_check_w):
        print(f"\n[WARN] {c} ({len(by_check_w[c])})")
        for d in by_check_w[c][:6]:
            print(f"   {d}")
    if not fails and not warns:
        print("\n全部检查通过 ✓")


if __name__ == "__main__":
    main()
