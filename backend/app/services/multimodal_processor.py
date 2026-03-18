"""
Multimodal Input Processor
Handles text, audio, and video inputs and converts them to text for processing.

Transcription priority:
  1. SpeechRecognition    (free Google Web Speech API, no key needed)
  2. Placeholder          (informs the user transcription is unavailable)
"""
import asyncio
import logging
import os
import base64
import tempfile
import subprocess
from typing import Dict, Any
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class MultimodalProcessor:
    """
    Processes multiple input types:
    1. Text  - Direct processing
    2. Audio - Transcription to text
    3. Video - Extract audio and transcribe to text
    4. Image - OCR extraction
    """

    def __init__(self):
        self.ocr_service = None
        self._sr_available = False
        self._initialize_transcription()
        self._initialize_ocr()

    def _initialize_transcription(self):
        """Probe which transcription backends are available."""
        try:
            import speech_recognition  # noqa: F401
            self._sr_available = True
            logger.info("Transcription backend: SpeechRecognition available")
        except ImportError:
            logger.warning("SpeechRecognition not installed — pip install SpeechRecognition")

        if not self._sr_available:
            logger.error("NO transcription backend available! Install SpeechRecognition for voice support.")

    def _initialize_ocr(self):
        """Initialize OCR service"""
        try:
            from app.services.ocr_service import OCRService
            self.ocr_service = OCRService()
            logger.info("OCR service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize OCR: {e}")

    # ── Public API ──────────────────────────────────────────────────────

    async def process_input(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process any type of input and convert to text.

        Args:
            input_data: {"type": "text"|"audio"|"video"|"image", "content": ..., "metadata": {}}

        Returns:
            {"text": str, "original_type": str, "confidence": float, "metadata": dict}
        """
        input_type = input_data.get("type", "text")

        if input_type == "text":
            return await self._process_text(input_data)
        elif input_type == "audio":
            return await self._process_audio(input_data)
        elif input_type == "video":
            return await self._process_video(input_data)
        elif input_type == "image":
            return await self._process_image(input_data)
        else:
            raise ValueError(f"Unsupported input type: {input_type}")

    def get_supported_formats(self) -> Dict[str, list]:
        return {
            "audio": ["mp3", "wav", "m4a", "webm", "ogg", "flac"],
            "video": ["mp4", "webm", "mov", "avi", "mkv"],
            "image": ["jpeg", "jpg", "png", "webp"],
            "text": ["plain"],
        }

    # ── Text ────────────────────────────────────────────────────────────

    async def _process_text(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "text": input_data.get("content", ""),
            "original_type": "text",
            "confidence": 1.0,
            "metadata": input_data.get("metadata", {}),
        }

    # ── Audio ───────────────────────────────────────────────────────────

    async def _process_audio(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Decode base64 audio → temp file → transcribe → return text."""
        audio_content = input_data.get("content")
        audio_format = input_data.get("format", "webm")

        try:
            if isinstance(audio_content, str):
                audio_bytes = base64.b64decode(audio_content)
            elif isinstance(audio_content, bytes):
                audio_bytes = audio_content
            else:
                raise ValueError("Audio content must be base64 string or bytes")

            with tempfile.NamedTemporaryFile(
                suffix=f".{audio_format}", delete=False
            ) as tmp:
                tmp.write(audio_bytes)
                temp_path = tmp.name

            try:
                transcription = await self._transcribe_audio(temp_path, audio_format)
                return {
                    "text": transcription["text"],
                    "original_type": "audio",
                    "confidence": transcription.get("confidence", 0.9),
                    "metadata": {
                        **input_data.get("metadata", {}),
                        "audio_format": audio_format,
                        "duration": transcription.get("duration"),
                        "engine": transcription.get("engine", "unknown"),
                    },
                }
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        except Exception as e:
            logger.error(f"Audio processing error: {e}")
            return {
                "text": "[Audio could not be understood]",
                "original_type": "audio",
                "confidence": 0.0,
                "metadata": {
                    **input_data.get("metadata", {}),
                    "error": "Voice could not be recognized. Please try again.",
                },
            }

    # ── Video ───────────────────────────────────────────────────────────

    async def _process_video(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract audio track from video, then transcribe."""
        video_content = input_data.get("content")
        video_format = input_data.get("format", "webm")

        try:
            if isinstance(video_content, str):
                video_bytes = base64.b64decode(video_content)
            elif isinstance(video_content, bytes):
                video_bytes = video_content
            else:
                raise ValueError("Video content must be base64 string or bytes")

            with tempfile.NamedTemporaryFile(
                suffix=f".{video_format}", delete=False
            ) as tmp:
                tmp.write(video_bytes)
                video_path = tmp.name

            audio_path = None
            try:
                audio_path = await self._extract_audio_from_video(video_path)
                transcription = await self._transcribe_audio(audio_path, "wav")
                return {
                    "text": transcription["text"],
                    "original_type": "video",
                    "confidence": transcription.get("confidence", 0.85),
                    "metadata": {
                        **input_data.get("metadata", {}),
                        "video_format": video_format,
                        "duration": transcription.get("duration"),
                        "engine": transcription.get("engine", "unknown"),
                    },
                }
            finally:
                if os.path.exists(video_path):
                    os.unlink(video_path)
                if audio_path and os.path.exists(audio_path):
                    os.unlink(audio_path)

        except Exception as e:
            logger.error(f"Video processing error: {e}")
            return {
                "text": "[Video could not be processed]",
                "original_type": "video",
                "confidence": 0.0,
                "metadata": {
                    **input_data.get("metadata", {}),
                    "error": "Video audio could not be recognized. Please try again.",
                },
            }

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  TRANSCRIPTION ENGINE (audio file → text)                           ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    async def _transcribe_audio(
        self, audio_path: str, audio_format: str = "webm"
    ) -> Dict[str, Any]:
        """
        Transcribe audio using SpeechRecognition (Google Web Speech — free).
        """
        errors: list[str] = []

        # ── SpeechRecognition (Google Web Speech — free) ─────────────
        if self._sr_available:
            try:
                result = await self._transcribe_speech_recognition(audio_path, audio_format)
                if result["text"] and result["text"].strip():
                    logger.info(f"Transcription (SpeechRecognition): '{result['text'][:80]}'")
                    return result
                else:
                    errors.append("SpeechRecognition returned empty text")
            except Exception as e:
                errors.append(f"SpeechRecognition: {e}")
                logger.warning(f"SpeechRecognition failed: {e}")

        all_errors = "; ".join(errors) if errors else "no transcription backend available"
        logger.error(f"Transcription failed: {all_errors}")
        raise RuntimeError(f"Transcription failed: {all_errors}")

    async def _transcribe_speech_recognition(
        self, audio_path: str, audio_format: str = "webm"
    ) -> Dict[str, Any]:
        """
        Free transcription via Google Web Speech API.
        SpeechRecognition needs WAV input, so we convert from webm/mp3/etc.
        """
        import speech_recognition as sr

        wav_path = await self._convert_to_wav(audio_path, audio_format)
        try:
            # Run the blocking recognizer in a thread so we don't block the event loop
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._sr_recognize_sync, wav_path
            )
            return result
        finally:
            if wav_path != audio_path and os.path.exists(wav_path):
                os.unlink(wav_path)

    def _sr_recognize_sync(self, wav_path: str) -> Dict[str, Any]:
        """Blocking call to SpeechRecognition — run in executor."""
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True

        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)

        # Try Google Web Speech (free, no key needed)
        text = recognizer.recognize_google(audio_data)
        return {
            "text": text.strip(),
            "confidence": 0.85,
            "duration": None,
            "language": "en",
            "engine": "google_web_speech",
        }

    # ── Audio format conversion ─────────────────────────────────────────

    async def _convert_to_wav(self, audio_path: str, audio_format: str) -> str:
        """Convert any audio format to WAV 16kHz mono for speech recognition."""
        if audio_format == "wav":
            return audio_path

        wav_path = audio_path.rsplit(".", 1)[0] + ".wav"

        # Try pydub first (pure Python, handles most formats)
        try:
            from pydub import AudioSegment

            loop = asyncio.get_event_loop()
            audio_seg = await loop.run_in_executor(
                None,
                lambda: AudioSegment.from_file(audio_path, format=audio_format),
            )
            # Convert to 16kHz mono WAV
            audio_seg = audio_seg.set_frame_rate(16000).set_channels(1)
            await loop.run_in_executor(
                None,
                lambda: audio_seg.export(wav_path, format="wav"),
            )
            logger.debug(f"Converted {audio_format} → WAV via pydub")
            return wav_path
        except Exception as e:
            logger.debug(f"pydub conversion failed ({e}), trying ffmpeg")

        # Fallback to ffmpeg CLI
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", audio_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                wav_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            if proc.returncode == 0:
                logger.debug(f"Converted {audio_format} → WAV via ffmpeg")
                return wav_path
            raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")
        except FileNotFoundError:
            raise RuntimeError(
                f"Cannot convert {audio_format} to WAV: "
                "install ffmpeg or pip install pydub"
            )

    # ── Video → Audio extraction ────────────────────────────────────────

    async def _extract_audio_from_video(self, video_path: str) -> str:
        """Extract audio track from video file using ffmpeg."""
        audio_path = video_path.rsplit(".", 1)[0] + ".wav"

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                audio_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")
            return audio_path
        except FileNotFoundError:
            raise RuntimeError(
                "ffmpeg not found — install ffmpeg for video processing"
            )

    # ── Image / OCR ─────────────────────────────────────────────────────

    async def _process_image(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process image input using general-purpose analysis.
        Handles: gas leaks, pipe damage, fire, meter readings, equipment, and more.
        """
        if not self.ocr_service:
            return self._fallback_image_processing(input_data)

        try:
            image_content = input_data.get("content")
            image_format = input_data.get("format", "jpeg")
            context = input_data.get("metadata", {}).get("context", "")

            if isinstance(image_content, str):
                image_data = image_content
            elif isinstance(image_content, bytes):
                image_data = base64.b64encode(image_content).decode("utf-8")
            else:
                raise ValueError("Image content must be base64 string or bytes")

            logger.info(f"Processing image for analysis (format: {image_format})")

            # Use general-purpose image analysis (handles ALL image types)
            analysis = await self.ocr_service.analyze_image(
                image_data=image_data,
                image_format=image_format,
                context=context,
            )

            if analysis.get("success"):
                image_type = analysis.get("image_type", "other")
                description = analysis.get("description", "Image analyzed")
                severity = analysis.get("severity", "medium")
                hazards = analysis.get("hazards_detected", [])
                recommendations = analysis.get("recommendations", [])
                confidence = analysis.get("confidence", 0.0)
                meter_reading_info = analysis.get("meter_reading")

                # Build human-readable summary
                parts = [f"Image Analysis ({image_type.replace('_', ' ').title()}): {description}"]

                if hazards:
                    parts.append(f"Hazards: {', '.join(hazards)}")
                parts.append(f"Severity: {severity.upper()}")
                if recommendations:
                    parts.append(f"Recommendations: {', '.join(recommendations)}")

                # If meter was detected and reading extracted, include it
                if meter_reading_info and meter_reading_info.get("reading"):
                    reading = meter_reading_info["reading"]
                    meter_type = meter_reading_info.get("meter_type", "unknown")
                    parts.append(f"Meter Reading: {reading} (Type: {meter_type})")

                text = " | ".join(parts)

                metadata = {
                    **input_data.get("metadata", {}),
                    "image_format": image_format,
                    "image_type": image_type,
                    "image_analysis": analysis,
                    "severity": severity,
                    "hazards_detected": hazards,
                    "visual_damage_confidence": analysis.get("visual_damage_confidence", 0.0),
                }

                # Add meter-specific fields if present
                if meter_reading_info:
                    metadata["ocr_result"] = meter_reading_info
                    metadata["meter_reading"] = meter_reading_info.get("reading")
                    metadata["meter_type"] = meter_reading_info.get("meter_type")

                return {
                    "text": text,
                    "original_type": "image",
                    "confidence": confidence,
                    "metadata": metadata,
                }
            else:
                error_msg = analysis.get("error", "Image analysis failed")
                logger.error(f"Image analysis failed: {error_msg}")
                return {
                    "text": f"[Image received — analysis failed: {error_msg}]",
                    "original_type": "image",
                    "confidence": 0.0,
                    "metadata": {
                        **input_data.get("metadata", {}),
                        "error": error_msg,
                    },
                }

        except Exception as e:
            logger.error(f"Image processing error: {e}")
            return self._fallback_image_processing(input_data)

    def _fallback_image_processing(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "text": "[Image received — image analysis service unavailable]",
            "original_type": "image",
            "confidence": 0.0,
            "metadata": {
                **input_data.get("metadata", {}),
                "error": "Image analysis service unavailable",
            },
        }
