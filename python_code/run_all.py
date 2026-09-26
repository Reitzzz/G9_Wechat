"""
一键全流程执行微信公众号全量文章抓取与归档
"""
import sys
from pathlib import Path

from config import ARTICLES_INDEX_JSON, WECHAT_CONFIG
from step1_fetch_index import get_credentials, fetch_articles_index
from step2_download_articles import download_all_articles
from step3_build_catalog import build_catalog


def main():
    print("=" * 60)
    print("  微信公众号【不同的角落】全量文章离线采集工具")
    print("=" * 60)

    # 1. 检查或拉取文章索引
    if not ARTICLES_INDEX_JSON.exists():
        print("\n>>> 步骤 1/3: 尚未检测到文章元数据索引，开始抓取文章列表...")
        token, cookie = get_credentials()
        if not token or not cookie:
            print("[x] 缺少公众号平台 token 或 Cookie，无法拉取文章列表！")
            sys.exit(1)
        fetch_articles_index(token, cookie)
    else:
        print("\n>>> 步骤 1/3: 检测到本地已有 articles_index.json 索引文件。")
        choice = input("是否跳过列表抓取，直接继续下载正文？(Y/n): ").strip().lower()
        if choice == "n":
            token, cookie = get_credentials()
            fetch_articles_index(token, cookie)

    # 2. 下载正文与图片
    print("\n>>> 步骤 2/3: 开始下载正文与防盗链图片本地化...")
    download_all_articles()

    # 3. 生成聚合目录
    print("\n>>> 步骤 3/3: 正在生成分类索引目录与报表...")
    build_catalog()

    print("\n" + "=" * 60)
    print("  全部流程处理完毕！可打开 articles/CATALOG.md 或 README.md 开始离线阅读。")
    print("=" * 60)


if __name__ == "__main__":
    main()
