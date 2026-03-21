# MEMORY.md - 长期记忆

## Lanya
- 偏好中文交流
- Telegram: @haixppp
- 时区: GMT+8
- 对 Solana/NFT 有兴趣
- 大模型使用优先级：1. Claude Code (claude-yunyi) 2. Kimi (kimi-coding/k2p5) 3. Qwen (qwen-portal/coder-model)

## 资产
- Solana 钱包: H69oouC8oL1cfRs5DEKxV9uxLkXbwojmWwxV9kBymgNH
- 私钥位置: .secrets/solana-wallet.json
- 签名工具: /tmp/solana-wallet/

## Moltbook 矿场（已停止）
- $CLAW 已铸满（21M/21M），矿场停止运作
- 曾运营 10 个 Agent（LanyaClaw 等）
- 最终余额待确认（安全事件后团队重新计算）
- ⚠️ 2026-02-14: MBC-20 被 Moltbook 封禁，帖子全删，参与 Agent 被禁言，Moltbook 视 MBC-20 为攻击行为

## 关注项目
- clawsnft.com — Agent-Only NFT, 暂时观望中
- mbc20.xyz — MBC-20 铭文代币标准（Agent 版 BRC-20），$CLAW 代币铸造中 ⭐
- BAP-578 (BNB Chain) — Non-Fungible Agent (NFA) 官方标准，重点关注 ⭐
- opusnft.xyz — Claws NFT 仿盘，暂时放一放
- Agentis — BAP-578 仿盘，Casper Network
- Conway (conway.tech) — AI Agent 自主基础设施（VM/算力/域名/支付），Thiel Fellow Sigil Wen 创建，x402+USDC 支付，MCP 协议，开源 Automaton（自我复制 Agent），重点关注生态进展 ⭐

## 监控偏好
- 创新项目优先，仿盘也推送但标注
- 重点关注 BAP-578/NFA 生态及跨链扩展
- 不只 NFT，覆盖所有 Agent-Only 项目（游戏/社交/DeFi/DAO/基础设施等）
- 所有新项目必须附推特地址
- 重点标注"首个/创新"标签
- 关键词结合项目情况逐步优化
- Bird 搜索每个关键词间隔 30 秒防封
- 2026-03-20 新增关键词：x402 生态、tempo.xyz/tempo chain、MCP token/agent
- 2026-03-21 新增关键词：TIP-20、tempo mainnet 生态、RedStone+tempo、mpp.dev（主网上线后补充）

## 监控架构（v2 - 脚本化）
- Shell 脚本 `scripts/twitter-monitor.sh`：crontab 每 4 小时运行，28 关键词全量搜索，0 AI token
- 每个关键词结果存独立文件（raw/），最后 jq 一次性合并去重
- flock 文件锁防并发
- AI 分析 cron job：每 12 小时读取 new-tweets.json（ID: 3990c0fa）
- Brave Search：已停用
- 项目分析文件：agent-project-analysis.md（首个/创新标签体系）
- 数据目录：monitor-data/（status.json, new-tweets.json, current-tweets.json, monitor.log）

## 工具
- bird CLI 已安装，Twitter cookie 已配置（auth_token + ct0）
- Brave Search API 已配置（2000次/月限额）
- Tor 已安装（用于换 IP 绕过注册限制）
- Kimi API Key 过期/无效，Moonshot 余额不足（待 Lanya 处理）

## 财报数据获取问题与解决方案

### 遇到的问题
- Yahoo Finance: 429 Too Many Requests（限流）
- Investing.com: 403 Forbidden（反爬虫）
- 直接web_fetch财经网站通常会被拦截

### 有效的数据源
✅ **中文财经媒体**（通过web_search）:
- 新浪财经、每经网、21经济网、证券时报
- 腾讯官网投资者关系页面
- 中华网科技、澎湃新闻

✅ **搜索策略**:
- 使用具体关键词：`[公司名] 2025年报 全年 财报 2026年3月`
- 包含发布时间：`2026年3月18日`
- 指定来源：`site:sina.com.cn` 或 `site:nbd.com.cn`

❌ **不推荐**:
- 直接访问Yahoo Finance、Investing.com（会被拦截）
- 使用browser工具访问需要登录的页面

### 改进建议
1. 优先使用web_search获取财报新闻报道
2. 从腾讯官网投资者关系页面获取PDF财报
3. 如需实时数据，考虑使用API（需配置）

## 工作场景与技能调用规则

### 银行业务场景
**当 Lanya 说"准备上会材料"时：**
- ✅ 含义：准备上审贷会的材料（授信审批会）
- ✅ 调用技能：`credit-committee-assistant`
- ✅ 输出格式：**Word文档（.docx）** 并通过Telegram发送
- ✅ 输出内容：
  - 最新财务变化分析（重点）
  - 审贷会提问预测（重点）
  - 三年财务数据对比
  - 行业深度分析
  - 客户战略分析
  - 建议回答要点
- ❌ 不要调用：`tech-earnings-deepdive`（那是投资分析用的）

**当 Lanya 说"财报分析"或"投资分析"时：**
- ✅ 调用技能：`tech-earnings-deepdive`
- ✅ 输出内容：16大模块+6大投资哲学视角+估值矩阵

### 技能区别
| 场景 | 技能 | 目的 | 输出重点 |
|------|------|------|---------|
| 审贷会准备 | credit-committee-assistant | 授信审批 | 风险点、提问预测、回答建议 |
| 投资决策 | tech-earnings-deepdive | 买卖判断 | 估值、增长、竞争力 |
| 拜访准备 | client-research | 客户背景调查 | 基本信息、最新动态、风险提示、访前建议 |

**当 Lanya 说「准备拜访 XX」或「拜访前材料」时：**
- ✅ 自动调用技能：`client-research`
- ✅ 输出内容：客户背景、最新动态、风险提示、访前建议
- ❌ 不需要用户额外说明
