"""阶段四：论坛转载前规范化（默认 dry-run，--apply 才落盘）

1. 头部改造：删除 YAML frontmatter，将 H1 下的「作者/发布时间/原文链接」
   三行引用块替换为标准授权声明块；正文不动。
2. 文件名统一为 YYYY年MM月DD日_NNNN_标题（补零、去空格、`__`归一、补「日」）：
   同步重命名 md / html / articles/images 子目录，改写文内
   `../images/<旧目录>/` 引用（html 仅动路径字符串），
   并更新 data/articles_index.json 与 data/download_status.json。
"""
import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MARKDOWN_DIR = BASE_DIR / "articles" / "markdown"
HTML_DIR = BASE_DIR / "articles" / "html"
IMAGES_DIR = BASE_DIR / "articles" / "images"
INDEX_JSON = BASE_DIR / "data" / "articles_index.json"
STATUS_JSON = BASE_DIR / "data" / "download_status.json"

DEFAULT_AUTHOR = "不同的角落"

# 统一头部结构：frontmatter + H1 + 三行引用块 + 分隔线（parser.py 生成格式）
HEADER_RE = re.compile(
    r"\A---\n"
    r"(?P<fm>.*?)"
    r"^---\n\n"
    r"# (?P<h1>[^\n]+)\n\n"
    r"> \*\*作者\*\*：[^\n]*\n"
    r"> \*\*发布时间\*\*：[^\n]*\n"
    r"> \*\*原文链接\*\*：[^\n]*\n\n"
    r"---\n\n",
    re.M | re.S,
)
FM_FIELD_RE = re.compile(r'^(\w+): "(.*)"$', re.M)

# 容忍命名瑕疵：__、缺「日」、日期与序号间空格、月/日不补零
NAME_RE = re.compile(
    r"^(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日?[ ]?_{1,2}(?P<idx>\d{4})_(?P<title>.+)$"
)


def normalize_stem(stem: str):
    m = NAME_RE.match(stem)
    if not m:
        return None
    return (
        f"{m.group('y')}年{int(m.group('m')):02d}月{int(m.group('d')):02d}日"
        f"_{m.group('idx')}_{m.group('title').strip()}"
    )


def transform_header(text: str):
    m = HEADER_RE.match(text)
    if not m:
        return text, False
    fm = dict(FM_FIELD_RE.findall(m.group("fm")))
    title = fm.get("title") or m.group("h1").strip()
    author = fm.get("author") or DEFAULT_AUTHOR
    new_head = (
        f"# {title}\n\n"
        f"> 本文转载自微信公众号 **{author}**，已获作者授权。  \n"
        f"> 原文发布于 {fm.get('date', '')}  \n"
        f"> 原文链接：[mp.weixin.qq.com]({fm.get('original_url', '')})\n\n"
        f"---\n\n"
    )
    return new_head + text[m.end():], True


def read_md(path: Path):
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode("utf-8")
    return text.replace("\r\n", "\n"), "\r\n" in text


def write_md(path: Path, text: str, crlf: bool):
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def rewrite_image_paths(text: str, img_map: dict) -> str:
    for old, new in img_map.items():
        text = text.replace(f"../images/{old}/", f"../images/{new}/")
    return text


def build_rename_map(paths, label):
    mapping, unparsable = {}, []
    for p in paths:
        target = normalize_stem(p.stem)
        if target is None:
            unparsable.append(p.name)
        elif target != p.stem:
            mapping[p.stem] = target
    return mapping, unparsable


def check_collisions(paths, mapping, label):
    final = [mapping.get(p.stem, p.stem) for p in paths]
    dupes = sorted({s for s in final if final.count(s) > 1})
    if dupes:
        print(f"[!] {label} 改名后存在重名冲突，中止：")
        for d in dupes:
            print(f"    {d}")
        return False
    return True


def update_status_json(status: dict, md_map, html_map):
    n = 0
    for v in status.values():
        if not isinstance(v, dict):
            continue
        for key in ("md_file", "html_file"):
            rel = v.get(key, "")
            if not rel:
                continue
            p = Path(rel)
            target = md_map.get(p.stem) if key == "md_file" else html_map.get(p.stem)
            if target is None:
                # 与磁盘名不一致的条目，按统一规则独立规范化
                target = normalize_stem(p.stem)
            if target and target != p.stem:
                v[key] = str(p.parent / f"{target}{p.suffix}")
                n += 1
    return n


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="论坛转载前规范化（头部 + 文件名）")
    ap.add_argument("--apply", action="store_true", help="实际写入，否则仅预演")
    args = ap.parse_args()

    md_files = sorted(MARKDOWN_DIR.glob("*.md"))
    html_files = sorted(HTML_DIR.glob("*.html"))
    img_dirs = sorted(d for d in IMAGES_DIR.iterdir() if d.is_dir())

    md_map, md_bad = build_rename_map(md_files, "md")
    html_map, html_bad = build_rename_map(html_files, "html")
    img_map, img_bad = build_rename_map(img_dirs, "images")

    ok = all([
        check_collisions(md_files, md_map, "markdown"),
        check_collisions(html_files, html_map, "html"),
        check_collisions(img_dirs, img_map, "images"),
    ])
    if not ok:
        sys.exit(1)

    # ---- 头部改造 ----
    done, unchanged, failed = [], [], []
    for p in md_files:
        text, crlf = read_md(p)
        new_text, changed = transform_header(text)
        if changed:
            done.append(p)
        else:
            failed.append(p)

    # ---- 文件名映射报告 ----
    all_renames = [("markdown", k, v) for k, v in md_map.items()]
    all_renames += [("html", k, v) for k, v in html_map.items()]
    all_renames += [("images", k, v) for k, v in img_map.items()]

    print("=" * 60)
    print(f"头部改造：待处理 {len(done)} / {len(md_files)}")
    if failed:
        print(f"  头部模式不匹配（将保持原样）{len(failed)} 个：")
        for p in failed[:20]:
            print(f"    {p.name}")

    print(f"文件名统一：需改名 {len(all_renames)} 处"
          f"（md {len(md_map)} / html {len(html_map)} / 图片目录 {len(img_map)}）")
    for kind, old, new in all_renames:
        print(f"  [{kind}] {old[:46]} -> {new[:46]}")
    if md_bad or html_bad or img_bad:
        print(f"  文件名无法解析：md {len(md_bad)} / html {len(html_bad)} / images {len(img_bad)}")
        for name in (md_bad + html_bad + img_bad)[:20]:
            print(f"    {name}")

    # ---- JSON 同步预演 ----
    with open(INDEX_JSON, encoding="utf-8") as f:
        index = json.load(f)
    with open(STATUS_JSON, encoding="utf-8") as f:
        status = json.load(f)

    md_stems = {p.stem for p in md_files}
    idx_hits, idx_indep, idx_ok, idx_bad = 0, 0, 0, []
    for item in index:
        stem = Path(item.get("file_name", "")).stem
        if stem in md_map:
            idx_hits += 1
        else:
            norm = normalize_stem(stem)
            if norm and norm != stem:
                idx_indep += 1
            elif stem in md_stems:
                idx_ok += 1
            else:
                idx_bad.append(item.get("file_name", ""))
    status_updates = update_status_json(status, md_map, html_map)
    print(f"索引同步：articles_index.json 映射改名 {idx_hits} 条 + 独立规范化 {idx_indep} 条"
          f" + 已规范 {idx_ok} 条 / 共 {len(index)} 条；download_status.json 待更新 {status_updates} 条")
    if idx_bad:
        print(f"  无法解析的索引条目 {len(idx_bad)} 个（保持原样）：")
        for name in idx_bad[:10]:
            print(f"    {name}")
    print("=" * 60)

    if not args.apply:
        print("dry-run 结束，未写入任何文件。确认无误后加 --apply 执行。")
        return

    # ---- 落盘：内容 ----
    for p in md_files:
        text, crlf = read_md(p)
        new_text, changed = transform_header(text)
        if not changed:
            continue
        new_text = rewrite_image_paths(new_text, img_map)
        write_md(p, new_text, crlf)

    for p in html_files:
        raw = p.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        text = raw.decode("utf-8")
        new_text = rewrite_image_paths(text, img_map)
        if new_text != text:
            p.write_bytes(new_text.encode("utf-8"))

    # ---- 落盘：改名 ----
    for old, new in md_map.items():
        (MARKDOWN_DIR / f"{old}.md").rename(MARKDOWN_DIR / f"{new}.md")
    for old, new in html_map.items():
        (HTML_DIR / f"{old}.html").rename(HTML_DIR / f"{new}.html")
    for old, new in img_map.items():
        (IMAGES_DIR / old).rename(IMAGES_DIR / new)

    # ---- 落盘：JSON ----
    for item in index:
        stem = Path(item.get("file_name", "")).stem
        target = md_map.get(stem) or normalize_stem(stem)
        if target and target != stem:
            item["file_name"] = f"{target}.md"
    INDEX_JSON.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    update_status_json(status, md_map, html_map)
    STATUS_JSON.write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[√] 完成：头部改造 {len(done)} 篇，改名 "
          f"md {len(md_map)} / html {len(html_map)} / 图片目录 {len(img_map)}，"
          f"索引已同步。")


if __name__ == "__main__":
    main()
