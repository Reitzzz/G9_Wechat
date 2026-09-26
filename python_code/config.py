"""
微信公众号全量文章抓取配置文件
"""
import os
from pathlib import Path

# 项目根目录（config.py 位于 python_code/ 子目录，根目录为其上一级）
BASE_DIR = Path(__file__).resolve().parent.parent

# 目标公众号信息
TARGET_ACCOUNT = {
    "name": "不同的角落",
    "fakeid": "MzU4OTczMzkwNw==",  # 从用户提供的历史页面 URL 提取的唯一业务 ID (__biz)
}

# 优先从 .env 读取凭证
ENV_FILE = BASE_DIR / ".env"
_env_vars = {}
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            _env_vars[k.strip()] = v.strip().strip('"').strip("'")

# 微信公众平台后台凭证（用于抓取全量 1030 篇列表）
WECHAT_CONFIG = {
    "token": os.environ.get("WECHAT_TOKEN", _env_vars.get("WECHAT_TOKEN", "")),
    "cookie": os.environ.get("WECHAT_COOKIE", _env_vars.get("WECHAT_COOKIE", "")),
}

# 数据存储目录
DATA_DIR = BASE_DIR / "data"
ARTICLES_DIR = BASE_DIR / "articles"
MARKDOWN_DIR = ARTICLES_DIR / "markdown"
HTML_DIR = ARTICLES_DIR / "html"
IMAGES_DIR = ARTICLES_DIR / "images"

# 文件路径
ARTICLES_INDEX_JSON = DATA_DIR / "articles_index.json"
ARTICLES_INDEX_CSV = DATA_DIR / "articles_index.csv"
DOWNLOAD_STATUS_JSON = DATA_DIR / "download_status.json"
CATALOG_MD = ARTICLES_DIR / "CATALOG.md"
README_MD = BASE_DIR / "README.md"

# 请求控制与反爬策略
REQUEST_SETTINGS = {
    # 微信公众平台列表接口延迟 (秒)
    "index_delay_min": 2.5,
    "index_delay_max": 4.5,
    
    # 正文下载请求延迟 (秒)
    "article_delay_min": 1.0,
    "article_delay_max": 2.0,
    
    # 遇到频控时的冷却时间 (秒)
    "freq_control_sleep": 90,
    
    # 最大重试次数
    "max_retries": 3,
    
    # 超时时间
    "timeout": 15,
}

# 通用请求头
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 NetType/WIFI "
        "MicroMessenger/7.0.20.1780(0x67001438) WindowsWechat(0x63090a1b) "
        "XWEB/11581 Flue"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 确保所有目录存在
for directory in [DATA_DIR, ARTICLES_DIR, MARKDOWN_DIR, HTML_DIR, IMAGES_DIR]:
    directory.mkdir(parents=True, exist_ok=True)
