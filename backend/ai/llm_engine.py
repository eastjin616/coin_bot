import base64
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """You are an expert cryptocurrency and stock trader analyzing a candlestick chart.

Look at this chart carefully and assess:
1. Recent price trend (uptrend / downtrend / sideways)
2. Candlestick patterns (momentum signals)
3. Volume pattern if visible
4. Support/resistance levels

Based on your analysis, what is the probability (0 to 100) that this asset's price will INCREASE over the next 1-2 hours?

- 100 = Extremely strong buy signal
- 80+ = Strong buy signal
- 50 = Neutral / uncertain
- 20 or less = Strong sell signal
- 0 = Extremely strong sell signal

Respond with ONLY a single integer number between 0 and 100. No explanation, no text, just the number."""


def _read_image_base64(image_path: str) -> tuple[str, str]:
    """이미지를 base64로 인코딩하고 mime type 반환"""
    path = Path(image_path)
    suffix = path.suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    mime_type = mime_map.get(suffix, "image/png")
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return data, mime_type


def _parse_probability(text: str) -> float:
    """LLM 응답에서 확률값(0~100) 파싱"""
    text = text.strip()
    for token in text.split():
        try:
            val = float(token.strip(".,;:!?"))
            if 0 <= val <= 100:
                return val
        except ValueError:
            continue
    # 숫자를 못 찾으면 로그 후 50 반환 (중립)
    logger.warning(f"LLM 응답 파싱 실패, 중립(50) 반환: {text!r}")
    return 50.0


class LLMEngine:
    """OpenAI / Gemini / Claude Vision API로 차트 분석 후 매수 확률 반환"""

    def __init__(self, gemini_api_key: str = "", anthropic_api_key: str = "", openai_api_key: str = ""):
        self.gemini_api_key = gemini_api_key
        self.anthropic_api_key = anthropic_api_key
        self.openai_api_key = openai_api_key
        self._provider = self._detect_provider()

    def _detect_provider(self) -> str:
        if self.openai_api_key:
            logger.info("✅ LLM 엔진: OpenAI GPT-4o Vision 사용")
            return "openai"
        if self.gemini_api_key:
            logger.info("✅ LLM 엔진: Gemini Vision 사용")
            return "gemini"
        if self.anthropic_api_key:
            logger.info("✅ LLM 엔진: Claude Vision 사용")
            return "claude"
        logger.warning("⚠️ LLM API 키 없음 — 랜덤 예측 모드로 동작 중")
        return "random"

    @property
    def is_active(self) -> bool:
        return self._provider != "random"

    def predict(self, image_path: str, indicators: dict | None = None) -> float:
        """차트 이미지를 분석해 매수 확률(0~100) 반환. indicators: 기술적 지표 딕셔너리"""
        if self._provider == "random":
            return random.uniform(0, 100)
        prompt = self._build_prompt(indicators)
        if self._provider == "openai":
            return self._predict_openai(image_path, prompt)
        if self._provider == "gemini":
            return self._predict_gemini(image_path, prompt)
        if self._provider == "claude":
            return self._predict_claude(image_path, prompt)
        return 50.0

    def _build_prompt(self, indicators: dict | None) -> str:
        if not indicators:
            return ANALYSIS_PROMPT
        ind_text = (
            f"\n\n[기술적 지표 데이터]\n"
            f"- 현재가: {indicators.get('current_price', 'N/A'):,.0f}\n"
            f"- MA5: {indicators.get('ma5', 'N/A'):,.0f} / MA20: {indicators.get('ma20', 'N/A'):,.0f}\n"
            f"- MA5 vs MA20: {indicators.get('ma5_signal', 'N/A')}\n"
            f"- 현재가 vs MA20: {indicators.get('price_vs_ma20', 'N/A')}\n"
            f"- RSI(14): {indicators.get('rsi', 'N/A'):.1f}\n"
            f"- 거래량 추세: {indicators.get('volume_trend', 'N/A')}\n"
        )
        return ANALYSIS_PROMPT + ind_text

    def _predict_openai(self, image_path: str, prompt: str) -> float:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.openai_api_key)
            img_data, mime_type = _read_image_base64(image_path)

            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                max_tokens=10,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{img_data}"},
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            text = response.choices[0].message.content
            prob = _parse_probability(text)
            logger.info(f"OpenAI 분석 결과: {prob:.1f}% (원문: {text.strip()!r})")
            return prob
        except Exception as e:
            logger.error(f"OpenAI API 오류: {e}")
            return 50.0

    def _predict_gemini(self, image_path: str, prompt: str = ANALYSIS_PROMPT) -> float:
        try:
            import google.generativeai as genai
            from google.generativeai.types import HarmCategory, HarmBlockThreshold

            genai.configure(api_key=self.gemini_api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")

            img_data, mime_type = _read_image_base64(image_path)
            image_part = {"mime_type": mime_type, "data": img_data}

            safety = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            response = model.generate_content(
                [prompt, image_part],
                safety_settings=safety,
            )
            text = response.text
            prob = _parse_probability(text)
            logger.info(f"Gemini 분석 결과: {prob:.1f}% (원문: {text.strip()!r})")
            return prob
        except Exception as e:
            logger.error(f"Gemini API 오류: {e}")
            return 50.0

    def _predict_claude(self, image_path: str, prompt: str = ANALYSIS_PROMPT) -> float:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.anthropic_api_key)
            img_data, mime_type = _read_image_base64(image_path)

            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": img_data,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            text = message.content[0].text
            prob = _parse_probability(text)
            logger.info(f"Claude 분석 결과: {prob:.1f}% (원문: {text.strip()!r})")
            return prob
        except Exception as e:
            logger.error(f"Claude API 오류: {e}")
            return 50.0
