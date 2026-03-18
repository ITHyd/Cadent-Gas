"""Image Analysis & OCR Service — local fallback only (no external API)."""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class OCRService:
    """
    Image Analysis & OCR Service for gas safety incidents.
    External vision APIs (Mistral/OpenAI) have been removed.
    Returns a placeholder result so the rest of the pipeline continues.
    """

    def __init__(self):
        logger.info("OCR Service initialized (local stub — no external vision API)")

    async def analyze_image(
        self,
        image_data: str,
        image_format: str = "jpeg",
        analysis_type: str = "general",
    ) -> Dict[str, Any]:
        """Return a safe placeholder — image is accepted but not analysed externally."""
        return {
            "success": True,
            "analysis_type": analysis_type,
            "description": "Image received. Automated visual analysis is not available.",
            "hazard_detected": False,
            "confidence": 0.0,
            "raw_text": "",
        }

    async def extract_meter_reading(
        self,
        image_data: str,
        image_format: str = "jpeg",
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "error": "Meter reading extraction requires a vision API key.",
            "reading": None,
        }
