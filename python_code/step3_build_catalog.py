"""
阶段三：生成按年份/月份折叠归类的 Markdown 索引目录与报表
"""
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from config import (
    ARTICLES_INDEX_JSON,
    DOWNLOAD_STATUS_JSON,
    CATALOG_MD,
    README_MD,
    MARKDOWN_DIR,
    HTML_DIR,
    IMAGES_DIR,
    TARGET_ACCOUNT,
)


def build_catalog():
    if not ARTICLES_INDEX_JSON.exists():
        print(f"[x] 未找到文章索引: {ARTICLES_INDEX_JSON}")
        return

    with open(ARTICLES_INDEX_JSON, "r", encoding="utf-8") as f:
        articles = json.load(f)

    status_map = {}
    if DOWNLOAD_STATUS_JSON.exists():
        try:
            with open(DOWNLOAD_STATUS_JSON, "r", encoding="utf-8") as f:
                status_map = json.load(f)
        except Exception:
            status_map = {}

    total_articles = len(articles)
    downloaded_md_files = list(MARKDOWN_DIR.glob("*.md"))
    downloaded_count = len(downloaded_md_files)
    
    # 统计本地图片总数与总体积
    img_files = list(IMAGES_DIR.rglob("*.*"))
    img_total_count = len(img_files)
    img_total_size_mb = sum(f.stat().st_size for f in img_files) / (1024 * 1024)

    # 按年份、月份组织文章
    tree = defaultdict(lambda: defaultdict(list))
    for item in articles:
        pub_date = item.get("publish_date", "")
        year = "其他年份"
        month = "未分类"
        if pub_date:
            m = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})", pub_date)
            if m:
                year = f"{m.group(1)}年"
                month = f"{int(m.group(2)):02d}月"
            else:
                try:
                    dt = datetime.strptime(pub_date[:19], "%Y-%m-%d %H:%M:%S")
                    year = f"{dt.year}年"
                    month = f"{dt.month:02d}月"
                except Exception:
                    pass
        
        link = item.get("link", "")
        st = status_map.get(link, {})
        item["local_md"] = st.get("md_file", "")
        item["local_html"] = st.get("html_file", "")
        
        tree[year][month].append(item)

    # 构建 Markdown 目录内容
    lines = [
        f"# 微信公众号【{TARGET_ACCOUNT['name']}】文章离线知识库",
        "",
        "> 本离线知识库包含文章正文排版解析、微信防盗链图片本地镜像存储，支持任意 Markdown 阅读器（如 Obsidian、Typora、VS Code）离线阅读。",
        "",
        "## 统计看板",
        "",
        f"- **公众号**：{TARGET_ACCOUNT['name']} (辽宁 沈阳)",
        f"- **总文章收录**：{total_articles} 篇",
        f"- **本地 Markdown 成功下载**：{downloaded_count} 篇",
        f"- **本地防盗链配图**：{img_total_count} 张 (约 {img_total_size_mb:.1f} MB)",
        f"- **数据更新时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
        "## 目录导航 (按时间倒序)",
        "",
    ]

    # 按年份倒序
    sorted_years = sorted(tree.keys(), reverse=True)
    for year in sorted_years:
        year_articles_count = sum(len(items) for items in tree[year].values())
        lines.append(f"### {year} (共 {year_articles_count} 篇)")
        lines.append("")
        
        # 按月份倒序
        sorted_months = sorted(tree[year].keys(), reverse=True)
        for month in sorted_months:
            month_articles = tree[year][month]
            lines.append(f"<details>")
            lines.append(f"<summary><b>📅 {month} ({len(month_articles)} 篇)</b></summary>")
            lines.append("")
            
            for item in month_articles:
                title = item.get("title", "未命名").replace("|", "-")
                pub_date = item.get("publish_date", "").split(" ")[0]
                link = item.get("link", "")
                local_md = item.get("local_md", "")
                
                if local_md:
                    # 相对于 CATALOG.md 的相对路径
                    rel_link = f"markdown/{Path(local_md).name}"
                    title_part = f"[{title}]({rel_link})"
                else:
                    title_part = f"{title} *(待下载)*"

                lines.append(f"- `{pub_date}` {title_part} | [微信原文]({link})")
            
            lines.append("")
            lines.append("</details>")
            lines.append("")

    content = "\n".join(lines)
    CATALOG_MD.write_text(content, encoding="utf-8")
    README_MD.write_text(content, encoding="utf-8")
    
    print(f"\n[√] 聚合离线目录已生成:")
    print(f"    - {CATALOG_MD}")
    print(f"    - {README_MD}")


if __name__ == "__main__":
    build_catalog()
