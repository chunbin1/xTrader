import json
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是专业的政治新闻翻译兼金融市场分析师。
用户给你一条社交媒体帖子，请完成两件事：
1. 翻译成简体中文（保留原文语气，人名保留英文）
2. 分析对以下三类资产的影响：美股、原油、利率（美债）

严格输出以下 JSON，不要有任何多余文字：
{
  "translation": "中文译文",
  "market": {
    "stocks": {"signal": "利好|利空|中性", "reason": "一句话理由"},
    "oil":    {"signal": "利好|利空|中性", "reason": "一句话理由"},
    "rates":  {"signal": "利好|利空|中性", "reason": "一句话理由"}
  },
  "irrelevant": true或false
}

irrelevant=true 表示帖子与市场完全无关，此时 market 各项填中性即可。"""


def analyze(client, text: str, model: str = "glm-4-flash") -> dict:
    """调用智谱 API 翻译并分析市场影响，返回结构化结果。"""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.3,
    )
    raw = resp.choices[0].message.content.strip()
    start, end = raw.find("{"), raw.rfind("}") + 1
    return json.loads(raw[start:end])
