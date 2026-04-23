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

TRANSLATE_ONLY_PROMPT = "将以下英文翻译成简体中文，只输出译文，不加任何解释："

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


def _translate_only(client, text: str, model: str) -> str:
    """单独做一次纯翻译，作为最终兜底。"""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": TRANSLATE_ONLY_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def analyze(client, text: str, model: str = "") -> dict:
    """依次尝试 MODEL_FALLBACK 中的模型，失败自动降级。
    全部失败时至少保证有中文翻译，不会把英文原文当译文推出去。
    """
    models = MODEL_FALLBACK if not model or model not in MODEL_FALLBACK else \
             MODEL_FALLBACK[MODEL_FALLBACK.index(model):]

    # 第一轮：尝试完整分析（翻译 + 市场）
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
            result = _extract_json(raw)
            if m != models[0]:
                logger.info("降级使用模型: %s", m)
            return result
        except Exception as e:
            logger.warning("模型 %s 分析失败: %s", m, e)
            last_err = e

    # 第二轮：所有模型完整分析均失败，至少做纯翻译
    logger.error("完整分析全部失败，尝试纯翻译兜底... 最后错误: %s", last_err)
    for m in models:
        try:
            translation = _translate_only(client, text, m)
            logger.info("纯翻译兜底成功，模型: %s", m)
            return {
                "translation": translation,
                "market": {
                    "stocks": {"signal": "中性", "reason": "分析失败，无法判断"},
                    "oil":    {"signal": "中性", "reason": "分析失败，无法判断"},
                    "rates":  {"signal": "中性", "reason": "分析失败，无法判断"},
                },
                "irrelevant": True,
            }
        except Exception as e:
            logger.warning("纯翻译模型 %s 也失败: %s", m, e)

    raise RuntimeError("翻译和分析全部失败")
