"""
微信公众号文章正文解析器与 Markdown 转换模块
"""
import os
import re
import hashlib
from pathlib import Path
import io
import requests
from PIL import Image
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from config import IMAGES_DIR, DEFAULT_HEADERS


def sanitize_filename(name: str, max_length: int = 80) -> str:
    """清理 Windows 文件名中的非法字符并截断长度"""
    # 替换 Windows 禁用字符 \ / : * ? " < > |
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", name)
    sanitized = re.sub(r'\s+', " ", sanitized).strip()
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip(" ._")
    return sanitized or "untitled"


def download_image(img_url: str, save_dir: Path, session: requests.Session = None) -> str:
    """
    下载单张微信防盗链图片并保存到本地
    返回相对路径（相对于 markdown 目录）
    """
    if not img_url or not img_url.startswith("http"):
        return ""
    
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # 根据 URL 生成稳定哈希文件名
    url_hash = hashlib.md5(img_url.encode("utf-8")).hexdigest()[:16]
    
    # 尝试推断扩展名
    ext = ".jpg"
    if "wx_fmt=png" in img_url or "format=png" in img_url:
        ext = ".png"
    elif "wx_fmt=gif" in img_url or "format=gif" in img_url:
        ext = ".gif"
    elif "wx_fmt=webp" in img_url or "format=webp" in img_url:
        ext = ".webp"
    
    img_filename = f"{url_hash}{ext}"
    local_path = save_dir / img_filename
    
    # 如果已存在则直接返回
    if local_path.exists() and local_path.stat().st_size > 0:
        return f"../images/{save_dir.name}/{img_filename}"
    
    headers = DEFAULT_HEADERS.copy()
    headers["Referer"] = "https://mp.weixin.qq.com/"
    
    s = session or requests.Session()
    try:
        resp = s.get(img_url, headers=headers, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 0:
            try:
                with Image.open(io.BytesIO(resp.content)) as im:
                    fmt = im.format.lower() if im.format else ""
                    if fmt == "webp":
                        if im.mode in ("RGBA", "P"):
                            ext = ".png"
                            img_filename = f"{url_hash}{ext}"
                            local_path = save_dir / img_filename
                            im.save(local_path, "PNG")
                        else:
                            ext = ".jpg"
                            img_filename = f"{url_hash}{ext}"
                            local_path = save_dir / img_filename
                            im.convert("RGB").save(local_path, "JPEG", quality=95)
                        return f"../images/{save_dir.name}/{img_filename}"
            except Exception:
                pass
            local_path.write_bytes(resp.content)
            return f"../images/{save_dir.name}/{img_filename}"
    except Exception as e:
        print(f"  [!] 图片下载失败: {img_url[:60]}... ({e})")
    
    # 下载失败时保留原链接
    return img_url


def parse_and_convert_article(
    html_content: str,
    article_info: dict,
    session: requests.Session = None
) -> tuple[str, str, str]:
    """
    解析微信图文 HTML，完成图片下载与重写，输出 Markdown 与清洗后的 HTML
    返回: (markdown_text, clean_html, title)
    """
    soup = BeautifulSoup(html_content, "lxml")
    
    # 1. 提取标题
    title = ""
    title_el = soup.find("h1", id="activity-name") or soup.find("h1", class_="rich_media_title")
    if title_el:
        title = title_el.get_text(strip=True)
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
    if not title:
        title = article_info.get("title", "未命名文章")
    
    # 2. 提取作者/公众号名称
    author = "不同的角落"
    nickname_el = soup.find("strong", class_="profile_nickname") or soup.find("a", id="js_name")
    if nickname_el:
        author = nickname_el.get_text(strip=True)
    
    # 3. 提取发布时间
    publish_time = article_info.get("publish_date", "")
    if not publish_time:
        # 尝试从页面中的 script 标签或 em 标签匹配
        time_match = re.search(r'var publish_time = "([^"]+)"', html_content)
        if time_match:
            publish_time = time_match.group(1)
        else:
            time_el = soup.find(id="publish_time")
            if time_el and time_el.get_text(strip=True):
                publish_time = time_el.get_text(strip=True)
    
    # 4. 获取正文主体
    content_div = soup.find("div", id="js_content")
    if not content_div:
        content_div = soup.find("div", class_="rich_media_content")
    
    if not content_div:
        # 若页面没有正文容器，可能已被删除或要求在客户端中打开
        return "", "", title
    
    # 创建该文章专属的图片存放子目录 (与 HTML/Markdown 文件名严格保持一致)
    folder_name = article_info.get("folder_name")
    if not folder_name:
        safe_t = sanitize_filename(title)
        folder_name = f"{publish_time[:10]}_{article_info.get('index', 1):04d}_{safe_t}"
    img_save_dir = IMAGES_DIR / folder_name
    
    # 5. 处理正文内的图片（替换 data-src 并本地化下载）
    for img in content_div.find_all("img"):
        real_src = img.get("data-src") or img.get("src")
        if real_src and not real_src.startswith("data:"):
            local_rel_path = download_image(real_src, img_save_dir, session)
            if local_rel_path:
                img["src"] = local_rel_path
            if "data-src" in img.attrs:
                del img["data-src"]
    
    # 移除不可见或干扰元素
    for tag in content_div.find_all(["script", "style"]):
        tag.decompose()
    
    raw_content_html = str(content_div)
    
    # 6. 转 Markdown
    markdown_body = md(
        raw_content_html,
        heading_style="ATX",
        bullets="-",
        strip=["script", "style"]
    )
    
    # 清理多余空行
    markdown_body = re.sub(r'\n{3,}', '\n\n', markdown_body).strip()
    
    # 7. 构建标准头部（论坛转载格式：标题 + 授权声明块，不再写 frontmatter）
    header = [
        f"# {title}",
        "",
        f"> 本文转载自微信公众号 **{author}**，已获作者授权。  ",
        f"> 原文发布于 {publish_time}  ",
        f"> 原文链接：[mp.weixin.qq.com]({article_info.get('link', '')})",
        "",
        "---",
        "",
        markdown_body
    ]

    full_markdown = "\n".join(header)
    return full_markdown, raw_content_html, title
