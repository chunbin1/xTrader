import json
import logging
import re

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是专业的政治新闻翻译兼金融市场分析师。
用户给你一条社交媒体帖子，请完成以下任务：
1. 翻译成简体中文（保留原文语气，人名保留英文）
2. 如果原文超过100个英文单词，额外提供一句话中文概要（30字以内）；否则 summary 填 null
3. 分析对以下三类资产的影响：美股、原油、利率（美债）

严格输出以下 JSON，不要有任何多余文字：
{
  "summary": "一句话概要（长帖才填，否则为null）",
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


def _extract_json(raw: str) -> dict:
    """从模型输出中提取 JSON，兼容输出前后有多余文字的情况。"""
    # 先找 ```json ... ``` 代码块
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # 再找第一个 { ... }
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("输出中找不到 JSON")
    return json.loads(raw[start:end])


def analyze(client, text: str, model: str = "", market_context: str = "") -> dict:
    """依次尝试 MODEL_FALLBACK 中的模型，失败自动降级。全部失败则 raise RuntimeError。"""
    models = MODEL_FALLBACK if not model or model not in MODEL_FALLBACK else \
             MODEL_FALLBACK[MODEL_FALLBACK.index(model):]

    system_content = f"{market_context}\n\n{SYSTEM_PROMPT}" if market_context else SYSTEM_PROMPT

    last_err = None
    for m in models:
        try:
            resp = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": text},
                ],
                temperature=0.3,
            )
            raw = resp.choices[0].message.content.strip()
            result = _extract_json(raw)
            if m != models[0]:
                logger.info("降级使用模型: %s", m)
            result["_model"] = m
            return result
        except Exception as e:
            logger.warning("模型 %s 分析失败: %s", m, e)
            last_err = e

    raise RuntimeError("所有模型均失败，智谱服务不可用")
