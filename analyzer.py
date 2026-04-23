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


MODEL_FALLBACK = [
    "glm-4.7",
    "glm-4.6v-flashx",
    "glm-4.6v",
    "glm-4.5-air",
]


def analyze(client, text: str, model: str = "") -> dict:
    """依次尝试 MODEL_FALLBACK 中的模型，失败自动降级。"""
    models = MODEL_FALLBACK if not model or model not in MODEL_FALLBACK else \
             MODEL_FALLBACK[MODEL_FALLBACK.index(model):]

    last_err = None
    for m in models:
        try:
            resp = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                temperature=0.3,
            )
            raw = resp.choices[0].message.content.strip()
            start, end = raw.find("{"), raw.rfind("}") + 1
            result = json.loads(raw[start:end])
            if m != models[0]:
                logger.info("降级使用模型: %s", m)
            return result
        except Exception as e:
            logger.warning("模型 %s 失败: %s，尝试下一个...", m, e)
            last_err = e

    raise RuntimeError(f"所有模型均失败，最后错误: {last_err}")
