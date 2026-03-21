#!/usr/bin/env python3
"""
Tempo Token 分析脚本
功能：读取 tempo-monitor.py 的结果，分析热门/新发现 token，推送给用户
额外功能：通过 Brave Search 搜索每个 token 的项目简介和推特号
运行频率：每2小时一次（crontab）
"""

import gzip
import html
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

WORKSPACE = "/root/.openclaw/workspace"
DATA_DIR = f"{WORKSPACE}/monitor-data/tempo"
NEW_TOKENS_FILE = f"{DATA_DIR}/new-tokens.json"
HOT_TOKENS_FILE = f"{DATA_DIR}/hot-tokens.json"
TOKENS_FILE = f"{DATA_DIR}/tokens.json"
ANALYZED_FILE = f"{DATA_DIR}/analyzed.json"
LOG_FILE = f"{DATA_DIR}/analyze.log"

# Brave Search API key (从环境变量或配置读取)
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")
OCLAW_CONFIG = "/root/.openclaw/openclaw.json"

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except:
            pass
    return default

def brave_search(query, count=3):
    """使用 Brave Search API 搜索"""
    if not BRAVE_API_KEY:
        return []
    try:
        params = urllib.parse.urlencode({"q": query, "count": count})
        req = urllib.request.Request(
            f"https://api.search.brave.com/res/v1/web/search?{params}",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": BRAVE_API_KEY,
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            # 处理 gzip 压缩
            if raw[:2] == b'\x1f\x8b':
                import gzip
                raw = gzip.decompress(raw)
            data = json.loads(raw)
            return data.get("web", {}).get("results", [])
    except Exception as e:
        log(f"Brave search error: {e}")
        return []
    finally:
        time.sleep(1.2)  # 防限流

def extract_twitter(results):
    """从搜索结果中提取推特账号"""
    for r in results:
        url = r.get("url", "")
        # 直接匹配 twitter.com 或 x.com
        m = re.search(r'(?:twitter\.com|x\.com)/(@?[A-Za-z0-9_]+)', url)
        if m:
            handle = m.group(1)
            if handle.lower() not in ("home", "search", "explore", "i", "intent", "share"):
                return f"@{handle.lstrip('@')}"
        # 从描述文本中提取
        for field in ("description", "title"):
            text = r.get(field, "")
            m = re.search(r'@([A-Za-z0-9_]{3,})', text)
            if m:
                return f"@{m.group(1)}"
    return None

def get_token_info(symbol, name, address):
    """搜索 token 的项目简介和推特"""
    info = {"description": None, "twitter": None}
    if not BRAVE_API_KEY:
        return info

    # 搜索推特账号
    results = brave_search(f"{symbol} {name} token crypto twitter site:x.com OR site:twitter.com", count=3)
    twitter = extract_twitter(results)
    if twitter:
        info["twitter"] = twitter

    # 搜索项目简介
    results2 = brave_search(f"{symbol} {name} token tempo blockchain crypto project", count=3)
    if results2:
        # 取第一条非 twitter 结果的描述
        for r in results2:
            url = r.get("url", "")
            if "twitter.com" not in url and "x.com" not in url:
                desc = r.get("description", "").strip()
                if desc and len(desc) > 20:
                    # 清理 HTML 标签和实体
                    desc = re.sub(r'<[^>]+>', '', desc)
                    desc = html.unescape(desc).strip()
                    info["description"] = desc[:200] + ("..." if len(desc) > 200 else "")
                    break

    # 如果还没找到推特，从简介搜索结果里再找
    if not info["twitter"]:
        twitter = extract_twitter(results2)
        if twitter:
            info["twitter"] = twitter

    return info

def format_token_entry(t, include_research=True):
    """格式化单个 token 的推送内容"""
    symbol = t.get('symbol', '?')
    name = t.get('name', '?')
    addr = t['address']
    tx = t.get('tx_count', 0)
    addrs = t.get('unique_addrs', 0)
    growth = t.get('growth_rate', 0)
    explorer = f"https://explore.tempo.xyz/token/{addr}"

    lines = [
        f"• **{symbol}** ({name})",
        f"  合约: `{addr[:10]}...{addr[-6:]}`",
        f"  交易: {tx}笔 | 地址: {addrs}个" + (f" | 增长: {growth}x" if growth else ""),
    ]

    if include_research:
        research = t.get("research", {})
        if research.get("twitter"):
            lines.append(f"  推特: {research['twitter']}")
        if research.get("description"):
            lines.append(f"  简介: {research['description']}")
        else:
            lines.append(f"  简介: 暂无公开信息")

    lines.append(f"  浏览器: {explorer}")
    return "\n".join(lines)

def main():
    log("=== Tempo Token 分析开始 ===")

    # 读取配置文件获取 Brave API Key
    global BRAVE_API_KEY
    if not BRAVE_API_KEY:
        try:
            cfg = json.load(open(OCLAW_CONFIG))
            BRAVE_API_KEY = cfg.get("tools", {}).get("web", {}).get("search", {}).get("apiKey", "")
            if BRAVE_API_KEY:
                log("Brave API Key 已加载")
        except Exception as e:
            log(f"读取配置失败: {e}")

    new_tokens = load_json(NEW_TOKENS_FILE, [])
    hot_tokens = load_json(HOT_TOKENS_FILE, [])
    tokens_db = load_json(TOKENS_FILE, {})
    analyzed = load_json(ANALYZED_FILE, {"notified_addresses": []})
    notified = set(analyzed.get("notified_addresses", []))

    # 过滤掉已通知的
    new_unreported = [t for t in new_tokens if t["address"] not in notified]
    hot_unreported = [t for t in hot_tokens if t["address"] not in notified]

    if not new_unreported and not hot_unreported:
        log("没有新发现，跳过推送")
        return

    # 对每个 token 搜索项目信息
    all_tokens = hot_unreported + new_unreported
    log(f"开始搜索 {len(all_tokens)} 个 token 的项目信息...")
    for t in all_tokens:
        symbol = t.get('symbol', '?')
        name = t.get('name', '?')
        addr = t['address']
        if symbol == '?' and name == '?':
            continue
        log(f"搜索 {symbol} ({name})...")
        research = get_token_info(symbol, name, addr)
        t["research"] = research
        # 同步写回 tokens_db
        if addr in tokens_db:
            tokens_db[addr]["research"] = research
        log(f"  -> 推特: {research.get('twitter','无')} | 简介: {'有' if research.get('description') else '无'}")

    # 保存更新后的 tokens_db
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens_db, f, indent=2, ensure_ascii=False)

    # 构建推送消息
    lines = ["🔍 **Tempo 链上 Token 监控播报**"]

    if hot_unreported:
        lines.append("\n🔥 **热门 Token（交易量增长）：**")
        for t in hot_unreported:
            lines.append(format_token_entry(t, include_research=True))

    if new_unreported:
        lines.append("\n🆕 **新发现 Token：**")
        for t in new_unreported:
            lines.append(format_token_entry(t, include_research=True))

    message = "\n".join(lines)
    print("\n" + "="*50)
    print(message)
    print("="*50 + "\n")

    # 写入推送内容（备份）
    alert_file = f"{DATA_DIR}/pending-alert.json"
    with open(alert_file, "w") as f:
        json.dump({
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "new_count": len(new_unreported),
            "hot_count": len(hot_unreported),
        }, f, indent=2, ensure_ascii=False)

    # 直接通过 Telegram 推送
    import subprocess
    # 清理消息中的 markdown（Telegram 纯文本模式）
    plain_message = message.replace("**", "").replace("`", "")
    try:
        result = subprocess.run(
            ["openclaw", "message", "send",
             "--channel", "telegram",
             "--target", "5852489810",
             "--message", plain_message],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PATH": "/root/.nvm/versions/node/v22.22.0/bin:" + os.environ.get("PATH", "")}
        )
        if result.returncode == 0:
            log("Telegram 推送成功")
            os.remove(alert_file)  # 推送成功后删除 pending 文件
        else:
            log(f"Telegram 推送失败: {result.stderr[:200]}")
    except Exception as e:
        log(f"Telegram 推送异常: {e}")

    # 更新已通知列表
    all_reported = [t["address"] for t in new_unreported + hot_unreported]
    analyzed["notified_addresses"] = list(notified | set(all_reported))[-200:]
    analyzed["last_run"] = datetime.now(timezone.utc).isoformat()
    with open(ANALYZED_FILE, "w") as f:
        json.dump(analyzed, f, indent=2)

    # 清空累积文件，避免重复推送（monitor 会重新累积）
    with open(NEW_TOKENS_FILE, "w") as f:
        json.dump([], f)
    with open(HOT_TOKENS_FILE, "w") as f:
        json.dump([], f)

    log(f"分析完成，新token:{len(new_unreported)} 热门:{len(hot_unreported)}")

if __name__ == "__main__":
    main()
