#!/bin/bash
# Twitter 关键词监控脚本 v2（独立运行，不消耗 AI token）
# 使用 bird CLI 搜索，结果写入文件，AI 只在有新发现时读取

# === 环境（crontab 需要）===
export PATH="/root/.nvm/versions/node/v22.22.0/bin:$PATH"
export HOME="/root"

# === 文件锁（防止并发运行）===
LOCKFILE="/tmp/twitter-monitor.lock"
exec 200>"$LOCKFILE"
if ! flock -xn 200; then
  echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] 另一个实例正在运行，跳过" >> /root/.openclaw/workspace/monitor-data/monitor.log
  exit 0
fi

set -uo pipefail

# === 配置 ===
AUTH_TOKEN="8e3a4193d54d3d7d1ab5960af3ba8007c56c89c4"
CT0="a1f6b42a213278048407134eb4bf653d9c67e974f67d79c0deff9717fe48b4ce50954714b4b91d4845b4ef7f44bddc36b7116a4f76b09f5a61ca90325dfd005c4c0d3080d4266fb31deea4636fe373c6"
RESULTS_PER_KEYWORD=5
DELAY_BETWEEN_SEARCHES=30
BIRD_PATH="/root/.nvm/versions/node/v22.22.0/bin/bird"

# === 路径 ===
WORKSPACE="/root/.openclaw/workspace"
DATA_DIR="$WORKSPACE/monitor-data"
CURRENT_FILE="$DATA_DIR/current-tweets.json"
PREVIOUS_FILE="$DATA_DIR/previous-tweets.json"
NEW_FILE="$DATA_DIR/new-tweets.json"
LOG_FILE="$DATA_DIR/monitor.log"
STATUS_FILE="$DATA_DIR/status.json"
RAW_DIR="$DATA_DIR/raw"

mkdir -p "$DATA_DIR" "$RAW_DIR"

# === 关键词列表 ===
KEYWORDS=(
  '"agent NFT" mint OR launch OR drop'
  '"BAP-578" OR "NFA" OR "Non-Fungible Agent"'
  '"MBC-20" OR "agent inscription" OR "agent token"'
  '"AI agent" NFT crypto solana ethereum'
  '"agent-only" NFT OR mint OR platform'
  '"ERC-404" agent OR AI'
  '"claws NFT" OR "clawsnft" OR "moltbook"'
  '"AI agent" DeFi OR DEX OR trading autonomous'
  '"agent" token launch crypto'
  '"agent-only" platform OR social OR game OR network'
  '"AI agent" social network OR platform "only for agents"'
  '"AI agent" game OR gaming autonomous'
  '"AI agent" DAO OR governance autonomous'
  '"agent economy" OR "agent marketplace" OR "agent-to-agent"'
  '"machine-only" OR "bot-only" OR "AI-only" platform OR network'
  '"autonomous agent" competition OR arena OR battle'
  '"AI agent" protocol OR infrastructure web3'
  '"P00KS" NFT agent'
  '"whoAmI" bitcoin agent NFT'
  '"$CLAW" moltbook OR mbc20'
  '"$BORT" BAP-578 agent'
  '"shellborn" agent NFT'
  '"BAP.Market" OR "bap market" agent'
  '"AI Agent" launch 2026'
  '"autonomous AI agent" new project'
  '"multi-agent" framework launch'
  '"agentic AI" platform release'
  '"AI agent" Base OR Solana mint 2026'
  '"x402" payment OR agent OR protocol'
  '"x402" OR "HTTP 402" site OR launch OR ecosystem'
  '"tempo.xyz" OR "tempoxyz" blockchain OR payment OR agent'
  '"tempo chain" OR "tempo blockchain" airdrop OR launch OR mainnet'
  '"MCP" "model context protocol" token OR coin OR crypto'
  '"MCP" agent AI web3 OR solana OR ethereum'
  '"MPP" OR "Machine Payments Protocol" agent OR stripe OR tempo'
  '"machine payments" AI agent autonomous OR protocol'
  '"TIP-20" OR "tip20" tempo stablecoin OR agent'
  '"tempo mainnet" OR "tempo chain" ecosystem OR deploy OR build'
  '"RedStone" tempo oracle OR integration OR mainnet'
  '"mpp.dev" OR "machine payments protocol" launch OR project OR agent'
  '"ERC-8004" OR "erc8004" agent OR AI'
  '"conway.tech" OR "Conway Terminal" OR "Conway Cloud" agent'
  '"Sigil Wen" conway OR agent OR web4'
  '"automaton" conway OR "self-replicating" agent'
)

log() {
  echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $1" >> "$LOG_FILE"
}

log "=== 监控开始 (${#KEYWORDS[@]} 个关键词) ==="

# 备份上次结果
if [ -f "$CURRENT_FILE" ]; then
  cp "$CURRENT_FILE" "$PREVIOUS_FILE"
fi

# 清空 raw 目录
rm -f "$RAW_DIR"/*.json

# 搜索所有关键词，每个结果存独立文件
SEARCH_COUNT=0
ERROR_COUNT=0

for keyword in "${KEYWORDS[@]}"; do
  SEARCH_COUNT=$((SEARCH_COUNT + 1))
  log "[$SEARCH_COUNT/${#KEYWORDS[@]}] 搜索: $keyword"
  
  RAW_FILE="$RAW_DIR/search_${SEARCH_COUNT}.json"
  
  # 执行搜索，结果直接写文件
  if $BIRD_PATH search "$keyword" -n $RESULTS_PER_KEYWORD --json \
    --auth-token "$AUTH_TOKEN" --ct0 "$CT0" > "$RAW_FILE" 2>/dev/null; then
    
    # 验证 JSON 并计数
    if jq empty "$RAW_FILE" 2>/dev/null; then
      COUNT=$(jq 'length' "$RAW_FILE")
      log "  → 找到 $COUNT 条推文"
    else
      ERROR_COUNT=$((ERROR_COUNT + 1))
      log "  → 无效 JSON"
      echo "[]" > "$RAW_FILE"
    fi
  else
    ERROR_COUNT=$((ERROR_COUNT + 1))
    log "  → 搜索失败"
    echo "[]" > "$RAW_FILE"
  fi
  
  # 防封延迟
  if [ $SEARCH_COUNT -lt ${#KEYWORDS[@]} ]; then
    sleep $DELAY_BETWEEN_SEARCHES
  fi
done

# 合并所有结果（用 jq 一次性合并所有文件）
log "合并结果..."
jq -s 'add | unique_by(.id)' "$RAW_DIR"/search_*.json > "$CURRENT_FILE" 2>/dev/null || echo "[]" > "$CURRENT_FILE"
TOTAL=$(jq 'length' "$CURRENT_FILE")

# 找出新推文
if [ -f "$PREVIOUS_FILE" ] && [ "$(jq 'length' "$PREVIOUS_FILE" 2>/dev/null || echo 0)" -gt 0 ]; then
  # 提取上次的 ID 列表
  jq -r '.[].id' "$PREVIOUS_FILE" > "$DATA_DIR/prev_ids.txt" 2>/dev/null || true
  
  # 筛选不在上次结果中的推文
  jq --slurpfile prev <(jq -R -s 'split("\n") | map(select(length > 0))' "$DATA_DIR/prev_ids.txt") \
    '[.[] | select(.id as $id | $prev[0] | index($id) | not)]' "$CURRENT_FILE" > "$NEW_FILE" 2>/dev/null || echo "[]" > "$NEW_FILE"
  
  rm -f "$DATA_DIR/prev_ids.txt"
else
  # 首次运行
  cp "$CURRENT_FILE" "$NEW_FILE"
fi

NEW_COUNT=$(jq 'length' "$NEW_FILE" 2>/dev/null || echo 0)

# 写入状态文件
cat > "$STATUS_FILE" << EOF
{
  "last_run": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "keywords_count": ${#KEYWORDS[@]},
  "total_tweets": $TOTAL,
  "new_tweets": $NEW_COUNT,
  "errors": $ERROR_COUNT,
  "search_duration_est": "$((${#KEYWORDS[@]} * DELAY_BETWEEN_SEARCHES / 60)) min"
}
EOF

log "=== 监控完成: 总计 $TOTAL 条, 新增 $NEW_COUNT 条, 错误 $ERROR_COUNT ==="

# 清理 raw 文件
rm -rf "$RAW_DIR"

echo "Done: $TOTAL tweets total, $NEW_COUNT new, $ERROR_COUNT errors"
