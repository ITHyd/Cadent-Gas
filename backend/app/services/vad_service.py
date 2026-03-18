"""
Voice Activity Detection Service
Detects when user is speaking vs silence
"""
import logging
import numpy as np
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class VADService:
    """
    Voice Activity Detection for continuous listening
    
    Detects:
    - Speech start
    - Speech end
    - Silence periods
    - Background noise levels
    """
    
    def __init__(self):
        self.silence_threshold = 0.01  # Energy threshold for silence
        self.speech_threshold = 0.03  # Energy threshold for speech
        self.min_speech_duration = 0.3  # Minimum speech duration (seconds)
        self.max_silence_duration = 1.5  # Max silence before considering speech ended
        self.sample_rate = 16000  # Audio sample rate
    
    def detect_voice_activity(
        self,
        audio_data: bytes,
        sample_rate: int = 16000
    ) -> Dict[str, Any]:
        """
        Detect voice activity in audio data
        
        Args:
            audio_data: Raw audio bytes
            sample_rate: Audio sample rate
        
        Returns:
            {
                "has_speech": bool,
                "energy_level": float,
                "is_silence": bool,
                "confidence": float
            }
        """
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Normalize
            audio_normalized = audio_array.astype(np.float32) / 32768.0
            
            # Calculate energy
            energy = np.sqrt(np.mean(audio_normalized ** 2))
            
            # Determine if speech or silence
            has_speech = energy > self.speech_threshold
            is_silence = energy < self.silence_threshold
            
            # Calculate confidence
            if has_speech:
                confidence = min(1.0, energy / self.speech_threshold)
            else:
                confidence = 1.0 - (energy / self.silence_threshold)
            
            return {
                "has_speech": has_speech,
                "energy_level": float(energy),
                "is_silence": is_silence,
                "confidence": float(confidence)
            }
        
        except Exception as e:
            logger.error(f"VAD error: {e}")
            return {
                "has_speech": False,
                "energy_level": 0.0,
                "is_silence": True,
                "confidence": 0.0,
                "error": str(e)
            }
    
    def should_process_audio(
        self,
        speech_segments: list,
        current_time: float
    ) -> bool:
        """
        Determine if accumulated audio should be processed
        
        Logic:
        - User has been speaking for min duration
        - Followed by silence for max duration
        """
        if not speech_segments:
            return False
        
        # Check if we have enough speech
        total_speech_duration = sum(seg["duration"] for seg in speech_segments if seg["has_speech"])
        
        if total_speech_duration < self.min_speech_duration:
            return False
        
        # Check if recent silence
        recent_segments = [seg for seg in speech_segments if current_time - seg["timestamp"] < self.max_silence_duration]
        recent_silence = all(seg["is_silence"] for seg in recent_segments[-3:]) if len(recent_segments) >= 3 else False
        
        return recent_silence
    
    def calculate_noise_level(
        self,
        audio_data: bytes
    ) -> float:
        """
        Calculate background noise level
        """
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_normalized = audio_array.astype(np.float32) / 32768.0
            
            # Use lower percentile as noise floor
            noise_level = np.percentile(np.abs(audio_normalized), 10)
            
            return float(noise_level)
        
        except Exception as e:
            logger.error(f"Noise calculation error: {e}")
            return 0.0
    
    def adjust_thresholds(
        self,
        noise_level: float
    ):
        """
        Dynamically adjust thresholds based on noise level
        """
        # Increase thresholds in noisy environments
        self.silence_threshold = max(0.01, noise_level * 1.5)
        self.speech_threshold = max(0.03, noise_level * 3.0)
        
        logger.info(f"Adjusted VAD thresholds - Silence: {self.silence_threshold:.3f}, Speech: {self.speech_threshold:.3f}")
