"""Text-to-Speech Service — browser fallback only (no external API)."""
import logging
import re
import asyncio
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TTSService:
    """
    TTS service — delegates to the browser Web Speech API.
    External TTS APIs (OpenAI) have been removed.
    """

    def __init__(self):
        logger.info("TTS Service initialized (browser fallback only)")

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        format: str = "mp3",
    ) -> Dict[str, Any]:
        if not text or not text.strip():
            return {"success": False, "error": "Empty text provided"}
        return {
            "success": True,
            "use_browser_tts": True,
            "text": text,
            "voice": voice or "default",
            "speed": speed,
        }

    async def stream_text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        chunk_size: int = 100,
    ):
        for sentence in self._split_into_sentences(text):
            if sentence.strip():
                result = await self.text_to_speech(sentence, voice=voice, speed=speed)
                if result.get("success"):
                    yield result
                await asyncio.sleep(0.1)

    def _split_into_sentences(self, text: str) -> list:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        grouped, current = [], ""
        for s in sentences:
            if len(current) + len(s) < 100:
                current += (" " + s) if current else s
            else:
                if current:
                    grouped.append(current)
                current = s
        if current:
            grouped.append(current)
        return grouped

    def get_available_voices(self) -> Dict[str, Any]:
        return {"browser_voices": "Available via Web Speech API (client-side)"}
