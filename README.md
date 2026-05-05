# xTrader

社交媒体监控 → LLM 翻译分析 → 飞书推送

监控 Truth Social 和 X (Twitter) 账号，自动翻译分析帖子内容，推送市场影响判断到飞书群。

## 功能

- 多平台支持：Truth Social (RSS)、X/Twitter
- 多账号监控：编辑 `accounts.json` 即可，无需改代码
- LLM 翻译分析：自动翻译 + 美股/原油/利率影响判断
- 美股热点推送：涨跌幅榜 + AI 分析，开盘时段自动推送
- 多 LLM Provider：支持 MiMo / 智谱 / OpenAI 动态切换
- 飞书卡片推送：带行情快照、信号颜色标记
- 免打扰时段：可配置静默时间

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key

# 单次运行
python3.11 monitor.py

# 持续监控
python3.11 monitor.py --watch

# 使用 start/stop 脚本
bash start.sh   # 后台启动
bash stop.sh    # 停止
bash status.sh  # 查看状态
```

## 配置

### LLM Provider

在 `.env` 中切换：

```
LLM_PROVIDER=mimo      # MiMo API（默认）
LLM_PROVIDER=zhipu     # 智谱 API
LLM_PROVIDER=openai    # OpenAI API
LLM_MODEL=             # 指定模型，留空用默认
```

| Provider | 默认模型 | 降级模型 |
|----------|----------|----------|
| mimo     | mimo-v2.5 | mimo-v2-flash |
| zhipu    | glm-4.7 | glm-4.6v-flashx, glm-4.6v, glm-4.5-air |
| openai   | gpt-4o | gpt-4o-mini |

### 监控账号

编辑 `accounts.json`：

```json
[
  {"name": "川普", "platform": "truthsocial", "handle": "realDonaldTrump"},
  {"name": "马斯克", "platform": "x", "handle": "elonmusk"}
]
```

### 美股热点

需要 Twelve Data API Key（[twelvedata.com](https://twelvedata.com)），填入 `TWELVEDATA_API_KEY`。

## 项目结构

```
monitor.py      # 主程序入口
analyzer.py     # LLM 分析（翻译 + 市场影响 + 热点分析）
sender.py       # 飞书推送（卡片消息）
fetchers/       # 数据源
  truthsocial.py  # Truth Social RSS
  x.py            # X/Twitter
  market.py       # 实时行情
  movers.py       # 美股涨跌榜
```
