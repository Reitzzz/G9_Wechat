"""
阶段一：从微信公众平台后台拉取目标公众号的全量文章元数据列表
"""
import json
import time
import random
import csv
import sys
from datetime import datetime
import requests

from config import (
    TARGET_ACCOUNT,
    WECHAT_CONFIG,
    ARTICLES_INDEX_JSON,
    ARTICLES_INDEX_CSV,
    REQUEST_SETTINGS,
    DEFAULT_HEADERS,
)


def get_credentials():
    """获取公众平台 token 和 cookie"""
    token = WECHAT_CONFIG.get("token", "").strip()
    cookie = WECHAT_CONFIG.get("cookie", "").strip()

    if not token or not cookie:
        print("=" * 60)
        print("【微信公众平台凭证输入】")
        print("提示：请在已登录 mp.weixin.qq.com 后台的浏览器中获取：")
        print("1. token: 浏览器地址栏中形如 token=123456789 的数字")
        print("2. Cookie: 按 F12 -> Network 刷新，复制任意请求头中的完整 Cookie")
        print("=" * 60)
        if not token:
            token = input("请输入 token: ").strip()
        if not cookie:
            cookie = input("请输入 Cookie: ").strip()
    
    return token, cookie


def fetch_articles_index(token: str, cookie: str):
    """通过公众平台 appmsg 接口分页拉取全部历史文章"""
    fakeid = TARGET_ACCOUNT["fakeid"]
    account_name = TARGET_ACCOUNT["name"]
    
    print(f"\n[+] 开始抓取公众号【{account_name}】的历史文章列表...")
    print(f"[+] 目标 fakeid (__biz): {fakeid}")
    
    headers = DEFAULT_HEADERS.copy()
    headers.update({
        "Cookie": cookie,
        "Referer": f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token={token}&lang=zh_CN",
        "X-Requested-With": "XMLHttpRequest",
    })
    
    session = requests.Session()
    session.headers.update(headers)
    
    # 读取已存在的本地进度（支持断点续拉）
    all_articles = []
    seen_links = set()
    if ARTICLES_INDEX_JSON.exists():
        try:
            with open(ARTICLES_INDEX_JSON, "r", encoding="utf-8") as f:
                all_articles = json.load(f)
                seen_links = {item.get("link") for item in all_articles if item.get("link")}
            print(f"[*] 检测到本地已有数据，已加载 {len(all_articles)} 篇历史文章。")
        except Exception as e:
            print(f"[!] 读取本地索引失败，将重新开始: {e}")
            all_articles = []

    begin = 0
    # 如果断点续拉，从最后一个整倍数开始
    if all_articles:
        begin = (len(all_articles) // 5) * 5
        print(f"[*] 断点续跑将从第 {begin} 篇开始请求...")

    count_per_page = 5
    total_count = None
    page = begin // count_per_page + 1

    api_url = "https://mp.weixin.qq.com/cgi-bin/appmsg"
    
    while True:
        params = {
            "action": "list_ex",
            "begin": str(begin),
            "count": str(count_per_page),
            "fakeid": fakeid,
            "type": "9",
            "query": "",
            "token": token,
            "lang": "zh_CN",
            "f": "json",
            "ajax": "1",
        }
        
        try:
            resp = session.get(api_url, params=params, timeout=REQUEST_SETTINGS["timeout"])
            data = resp.json()
        except Exception as e:
            print(f"[-] 请求异常: {e}，将在 5 秒后重试...")
            time.sleep(5)
            continue

        base_resp = data.get("base_resp", {})
        ret = base_resp.get("ret", 0)
        
        if ret == 200013:
            # 遭遇频控
            sleep_time = REQUEST_SETTINGS["freq_control_sleep"]
            print(f"\n[!] 触发微信公众平台频控限制 (ret=200013)，自动进入休眠冷却 {sleep_time} 秒...")
            time.sleep(sleep_time)
            continue
        elif ret == 200003:
            print("\n[x] 凭据已失效或未登录 (ret=200003)，请重新获取 token 和 Cookie 后重试！")
            sys.exit(1)
        elif ret != 0:
            err_msg = base_resp.get("err_msg", "未知错误")
            print(f"\n[x] 接口返回异常: ret={ret}, err_msg={err_msg}")
            break

        if total_count is None:
            total_count = data.get("app_msg_cnt", 0)
            print(f"[+] 接口返回官方统计总文章数: {total_count} 篇\n")

        msg_list = data.get("app_msg_list", [])
        if not msg_list:
            print(f"[+] 已无更多文章，本次列表拉取结束。")
            break

        new_count = 0
        for item in msg_list:
            link = item.get("link", "")
            if link and link not in seen_links:
                create_timestamp = item.get("create_time", 0)
                update_timestamp = item.get("update_time", 0)
                pub_date = datetime.fromtimestamp(update_timestamp or create_timestamp).strftime("%Y-%m-%d %H:%M:%S")
                
                article_data = {
                    "index": len(all_articles) + 1,
                    "aid": item.get("aid", ""),
                    "appmsgid": item.get("appmsgid", ""),
                    "title": item.get("title", ""),
                    "digest": item.get("digest", ""),
                    "link": link,
                    "cover": item.get("cover", ""),
                    "create_time": create_timestamp,
                    "update_time": update_timestamp,
                    "publish_date": pub_date,
                }
                all_articles.append(article_data)
                seen_links.add(link)
                new_count += 1

        print(f"[{page:03d}页] 已抓取 offset={begin:04d} -> 新增 {new_count} 篇 (当前累计: {len(all_articles)}/{total_count or '未知'}) - 最新: {msg_list[0].get('title', '')[:25]}")

        # 实时保存到本地，防止意外中断数据丢失
        with open(ARTICLES_INDEX_JSON, "w", encoding="utf-8") as f:
            json.dump(all_articles, f, ensure_ascii=False, indent=2)

        begin += count_per_page
        page += 1
        
        if total_count and begin >= total_count:
            print(f"[+] 已达到官方总数 ({len(all_articles)}/{total_count})，抓取完成！")
            break

        # 随机休眠防风控
        sleep_interval = random.uniform(REQUEST_SETTINGS["index_delay_min"], REQUEST_SETTINGS["index_delay_max"])
        time.sleep(sleep_interval)

    # 导出 CSV 表格
    if all_articles:
        with open(ARTICLES_INDEX_CSV, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "index", "title", "publish_date", "link", "digest", "cover", "aid", "appmsgid", "create_time", "update_time"
            ])
            writer.writeheader()
            writer.writerows(all_articles)
        print(f"\n[√] 全量索引已成功保存:")
        print(f"    - JSON: {ARTICLES_INDEX_JSON}")
        print(f"    - CSV:  {ARTICLES_INDEX_CSV}")
        print(f"    - 总计: {len(all_articles)} 篇文章")

    return all_articles


if __name__ == "__main__":
    token, cookie = get_credentials()
    if token and cookie:
        fetch_articles_index(token, cookie)
    else:
        print("[x] 缺少必要的 token 或 cookie 凭据。")
