"""
阶段二：全量文章正文下载、图片防盗链本地化、Markdown / HTML 转换
"""
import json
import time
import random
import re
from pathlib import Path
import requests
from tqdm import tqdm

from config import (
    ARTICLES_INDEX_JSON,
    DOWNLOAD_STATUS_JSON,
    MARKDOWN_DIR,
    HTML_DIR,
    DEFAULT_HEADERS,
    REQUEST_SETTINGS,
)
from utils.parser import parse_and_convert_article, sanitize_filename


def load_download_status() -> dict:
    """加载已下载状态记录表"""
    if DOWNLOAD_STATUS_JSON.exists():
        try:
            with open(DOWNLOAD_STATUS_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_download_status(status: dict):
    """保存状态记录表"""
    with open(DOWNLOAD_STATUS_JSON, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def download_all_articles():
    if not ARTICLES_INDEX_JSON.exists():
        print(f"[x] 未找到文章索引文件: {ARTICLES_INDEX_JSON}")
        print("    请先运行 1_fetch_index.py 获取文章列表！")
        return

    with open(ARTICLES_INDEX_JSON, "r", encoding="utf-8") as f:
        articles = json.load(f)

    if not articles:
        print("[!] 文章列表为空，请检查！")
        return

    status_map = load_download_status()
    total_articles = len(articles)
    
    print(f"\n[+] 加载文章索引成功，共 {total_articles} 篇文章。")
    already_done = sum(1 for item in articles if status_map.get(item.get("link", ""), {}).get("status") == "success")
    print(f"[*] 已完成下载: {already_done} 篇，待处理: {total_articles - already_done} 篇。")

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    pbar = tqdm(articles, desc="下载文章与图片", initial=0)
    
    for item in pbar:
        link = item.get("link", "")
        title = item.get("title", "未命名")
        pub_date = item.get("publish_date", "").split(" ")[0] or "unknown_date"
        m_date = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", pub_date)
        if m_date:
            pub_date = (f"{m_date.group(1)}年{int(m_date.group(2)):02d}"
                        f"月{int(m_date.group(3)):02d}日")
        idx = item.get("index", 0)

        if not link:
            continue

        # 检查是否已成功下载
        if status_map.get(link, {}).get("status") == "success":
            pbar.set_postfix_str(f"跳过已存在: {title[:15]}")
            continue

        pbar.set_postfix_str(f"正在处理: {title[:15]}")

        safe_title = sanitize_filename(title)
        base_name = f"{pub_date}_{idx:04d}_{safe_title}"
        md_file = MARKDOWN_DIR / f"{base_name}.md"
        html_file = HTML_DIR / f"{base_name}.html"

        # 如果本地文件完整存在且大小正常，也视为已完成
        if md_file.exists() and md_file.stat().st_size > 200:
            status_map[link] = {
                "status": "success",
                "title": title,
                "md_file": str(md_file.relative_to(MARKDOWN_DIR.parent)),
                "updated_at": time.time(),
            }
            save_download_status(status_map)
            continue

        retries = 0
        success = False
        while retries < REQUEST_SETTINGS["max_retries"] and not success:
            try:
                resp = session.get(link, timeout=REQUEST_SETTINGS["timeout"])
                if resp.status_code == 200 and "js_content" in resp.text:
                    markdown_content, clean_html, parsed_title = parse_and_convert_article(
                        resp.text, item, session=session
                    )
                    
                    if markdown_content:
                        # 写入 Markdown
                        md_file.write_text(markdown_content, encoding="utf-8")
                        
                        # 写入完整单页离线 HTML (保留基础内联 CSS)
                        wrapped_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{parsed_title or title}</title>
<style>
  body {{ max-width: 720px; margin: 30px auto; padding: 0 16px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.8; color: #222; }}
  h1 {{ font-size: 22px; margin-bottom: 8px; }}
  .meta {{ color: #888; font-size: 14px; margin-bottom: 24px; padding-bottom: 12px; border-bottom: 1px solid #eee; }}
  img {{ max-width: 100%; height: auto; display: block; margin: 16px auto; border-radius: 4px; }}
</style>
</head>
<body>
<h1>{parsed_title or title}</h1>
<div class="meta">作者: 不同的角落 | 发布时间: {pub_date} | 原文链接: <a href="{link}" target="_blank">微信原文</a></div>
<div class="content">{clean_html}</div>
</body>
</html>"""
                        html_file.write_text(wrapped_html, encoding="utf-8")

                        status_map[link] = {
                            "status": "success",
                            "title": parsed_title or title,
                            "md_file": str(md_file.relative_to(MARKDOWN_DIR.parent)),
                            "html_file": str(html_file.relative_to(HTML_DIR.parent)),
                            "updated_at": time.time(),
                        }
                        save_download_status(status_map)
                        success = True
                    else:
                        print(f"\n[!] 文章正文为空或已被删除: {title} ({link})")
                        status_map[link] = {"status": "empty_or_deleted", "title": title}
                        save_download_status(status_map)
                        break
                elif "为了保护你的帐号安全，请在微信客户端访问" in resp.text:
                    print(f"\n[!] 微信触发客户端环境校验，休眠 60 秒...")
                    time.sleep(60)
                    retries += 1
                else:
                    retries += 1
                    time.sleep(3)
            except Exception as e:
                retries += 1
                time.sleep(2)

        if not success and link not in status_map:
            status_map[link] = {"status": "failed", "title": title}
            save_download_status(status_map)

        # 随机温和休眠防频控
        time.sleep(random.uniform(REQUEST_SETTINGS["article_delay_min"], REQUEST_SETTINGS["article_delay_max"]))

    print("\n[√] 所有文章抓取与转换流程已完成！")


if __name__ == "__main__":
    download_all_articles()
