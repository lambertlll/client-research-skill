#!/usr/bin/env python3
"""
Tempo 链上新 Token 监控脚本
功能：监控新发行的 ERC-20 token，筛选交易量和 holder 数量增长的项目
运行频率：建议每 30 分钟一次（crontab）
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone

# === 配置 ===
RPC_URL = "https://rpc.tempo.xyz"
WORKSPACE = "/root/.openclaw/workspace"
DATA_DIR = f"{WORKSPACE}/monitor-data/tempo"
STATE_FILE = f"{DATA_DIR}/state.json"
TOKENS_FILE = f"{DATA_DIR}/tokens.json"
NEW_TOKENS_FILE = f"{DATA_DIR}/new-tokens.json"
HOT_TOKENS_FILE = f"{DATA_DIR}/hot-tokens.json"
LOG_FILE = f"{DATA_DIR}/monitor.log"

# ERC-20 Transfer event topic
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# 筛选阈值
MIN_TX_COUNT = 5         # 最少交易次数
MIN_UNIQUE_ADDRS = 3     # 最少独立参与地址数（近似 holder 增长）
SCAN_BLOCKS = 1000       # 每次扫描块数
HOT_GROWTH_RATE = 2.0    # 交易量增长倍数阈值（判断为热门）

# 已知的系统/桥接合约（过滤掉）
KNOWN_SYSTEM_CONTRACTS = {
    "0x20c0000000000000000000000000000000000000",  # USDC native
    "0x20c000000000000000000000b9537d11c60e8b50",  # USDC mainnet
}

os.makedirs(DATA_DIR, exist_ok=True)

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def rpc(method, params=None):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params or [],
        "id": 1
    }).encode()
    req = urllib.request.Request(
        RPC_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Origin": "https://explore.tempo.xyz",
            "Referer": "https://explore.tempo.xyz/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log(f"RPC error ({method}): {e}")
        return None

def get_token_name(address):
    """尝试获取 token 名称和符号"""
    # name() selector: 0x06fdde03
    # symbol() selector: 0x95d89b41
    # decimals() selector: 0x313ce567
    # totalSupply() selector: 0x18160ddd
    results = {}
    for fname, selector in [("name", "0x06fdde03"), ("symbol", "0x95d89b41"), ("decimals", "0x313ce567")]:
        resp = rpc("eth_call", [{"to": address, "data": selector}, "latest"])
        if resp and resp.get("result") and resp["result"] != "0x":
            raw = resp["result"][2:]  # remove 0x
            try:
                if fname == "decimals":
                    results[fname] = int(raw, 16) if len(raw) <= 64 else int(raw[-2:], 16)
                else:
                    # ABI decode string
                    if len(raw) >= 128:
                        offset = int(raw[:64], 16) * 2
                        length = int(raw[offset:offset+64], 16) * 2
                        text = bytes.fromhex(raw[offset+64:offset+64+length]).decode("utf-8", errors="ignore")
                        results[fname] = text.strip()
                    else:
                        results[fname] = bytes.fromhex(raw).decode("utf-8", errors="ignore").strip().rstrip('\x00')
            except:
                results[fname] = "?"
    return results

def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except:
            pass
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    log("=== Tempo Token 监控开始 ===")

    # 1. 获取最新块高
    resp = rpc("eth_blockNumber")
    if not resp or "result" not in resp:
        log("ERROR: 无法获取最新块高")
        sys.exit(1)
    latest_hex = resp["result"]
    latest = int(latest_hex, 16)
    log(f"最新块高: {latest} ({latest_hex})")

    # 2. 读取上次扫描状态
    state = load_json(STATE_FILE, {})
    last_block = state.get("last_block", latest - SCAN_BLOCKS)
    from_block = max(last_block + 1, latest - SCAN_BLOCKS)
    from_hex = hex(from_block)
    log(f"扫描范围: {from_block} -> {latest}")

    # 3. 获取 Transfer 事件
    resp = rpc("eth_getLogs", [{
        "fromBlock": from_hex,
        "toBlock": latest_hex,
        "topics": [TRANSFER_TOPIC]
    }])
    if not resp or "result" not in resp:
        log("ERROR: 无法获取 logs")
        sys.exit(1)

    logs = resp["result"]
    log(f"共获取 {len(logs)} 条 Transfer 事件")

    # 4. 按合约地址统计交易量和参与地址
    contract_stats = defaultdict(lambda: {"tx_count": 0, "addrs": set(), "blocks": set()})
    for log_entry in logs:
        addr = log_entry["address"].lower()
        if addr in KNOWN_SYSTEM_CONTRACTS:
            continue
        # 获取 from/to（topics[1], topics[2]）
        topics = log_entry.get("topics", [])
        if len(topics) >= 3:
            sender = "0x" + topics[1][-40:]
            receiver = "0x" + topics[2][-40:]
            contract_stats[addr]["addrs"].add(sender)
            contract_stats[addr]["addrs"].add(receiver)
        contract_stats[addr]["tx_count"] += 1
        contract_stats[addr]["blocks"].add(log_entry.get("blockNumber", "0x0"))

    log(f"发现 {len(contract_stats)} 个活跃 token 合约")

    # 5. 加载历史数据
    tokens_db = load_json(TOKENS_FILE, {})
    now_ts = int(time.time())

    # 6. 筛选有意义的 token
    new_tokens = []
    hot_tokens = []

    for addr, stats in contract_stats.items():
        tx_count = stats["tx_count"]
        unique_addrs = len(stats["addrs"])

        if tx_count < MIN_TX_COUNT or unique_addrs < MIN_UNIQUE_ADDRS:
            continue

        # 获取 token 元数据（仅对新发现的合约）
        is_new = addr not in tokens_db
        if is_new:
            log(f"新发现合约 {addr}，获取元数据...")
            meta = get_token_name(addr)
            token_info = {
                "address": addr,
                "name": meta.get("name", "?"),
                "symbol": meta.get("symbol", "?"),
                "decimals": meta.get("decimals", 18),
                "first_seen_block": from_block,
                "first_seen_ts": now_ts,
                "tx_count_history": [],
                "unique_addrs_history": [],
            }
            tokens_db[addr] = token_info
            new_tokens.append({**token_info, "tx_count": tx_count, "unique_addrs": unique_addrs})
        else:
            token_info = tokens_db[addr]

        # 更新历史
        token_info["tx_count_history"] = token_info.get("tx_count_history", [])[-9:] + [tx_count]
        token_info["unique_addrs_history"] = token_info.get("unique_addrs_history", [])[-9:] + [unique_addrs]
        token_info["last_seen_block"] = latest
        token_info["last_seen_ts"] = now_ts

        # 判断是否热门（交易量增长）
        history = token_info["tx_count_history"]
        if len(history) >= 2:
            growth = history[-1] / max(history[-2], 1)
            if growth >= HOT_GROWTH_RATE or tx_count >= 20:
                hot_tokens.append({
                    "address": addr,
                    "name": token_info.get("name", "?"),
                    "symbol": token_info.get("symbol", "?"),
                    "tx_count": tx_count,
                    "unique_addrs": unique_addrs,
                    "growth_rate": round(growth, 2),
                    "explorer": f"https://explore.tempo.xyz/token/{addr}",
                })

    # 7. 保存数据
    save_json(TOKENS_FILE, tokens_db)

    # new/hot tokens 累积追加（analyze.py 读完后负责清空，避免时序竞争）
    existing_new = load_json(NEW_TOKENS_FILE, [])
    existing_hot = load_json(HOT_TOKENS_FILE, [])
    existing_new_addrs = {t["address"] for t in existing_new}
    existing_hot_addrs = {t["address"] for t in existing_hot}
    merged_new = existing_new + [t for t in new_tokens if t["address"] not in existing_new_addrs]
    merged_hot = existing_hot + [t for t in hot_tokens if t["address"] not in existing_hot_addrs]
    save_json(NEW_TOKENS_FILE, merged_new)
    save_json(HOT_TOKENS_FILE, merged_hot)

    # 8. 更新状态
    state["last_block"] = latest
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["total_tokens_tracked"] = len(tokens_db)
    save_json(STATE_FILE, state)

    log(f"新发现 token: {len(new_tokens)} 个")
    log(f"热门 token: {len(hot_tokens)} 个")
    if new_tokens:
        for t in new_tokens:
            log(f"  NEW: {t['symbol']} ({t['name']}) @ {t['address']} | tx:{t['tx_count']} addrs:{t['unique_addrs']}")
    if hot_tokens:
        for t in hot_tokens:
            log(f"  HOT: {t['symbol']} ({t['name']}) @ {t['address']} | tx:{t['tx_count']} addrs:{t['unique_addrs']} growth:{t['growth_rate']}x")

    log(f"=== 监控完成，追踪 {len(tokens_db)} 个 token ===")
    return new_tokens, hot_tokens

if __name__ == "__main__":
    main()
