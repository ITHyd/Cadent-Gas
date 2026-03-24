import { useState, useRef, useEffect } from 'react';

const LiveVoiceChat = ({ onTranscript, onAudioReady, onAudioResponse, transcribeMode = false, onStop }) => {
  const [isListening, setIsListening] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isSpeakingPaused, setIsSpeakingPaused] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [status, setStatus] = useState('idle'); // idle, listening, paused, processing, speaking

  const mediaRecorderRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const audioChunksRef = useRef([]);
  const silenceTimerRef = useRef(null);
  const currentAudioRef = useRef(null);

  const SILENCE_THRESHOLD = 1500; // ms of silence before sending

  const styles = {
    container: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '1rem',
      padding: '1.5rem 1rem',
    },
    visualizer: {
      position: 'relative',
      width: '120px',
      height: '120px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    },
    circle: {
      position: 'absolute',
      borderRadius: '50%',
      transition: 'all 0.15s ease',
    },
    outerCircle: {
      width: '120px',
      height: '120px',
      background: 'linear-gradient(135deg, #8DE971 0%, #7AC75E 100%)',
      opacity: 0.08,
    },
    middleCircle: {
      width: '96px',
      height: '96px',
      background: 'linear-gradient(135deg, #8DE971 0%, #7AC75E 100%)',
      opacity: 0.15,
    },
    innerCircle: {
      width: '72px',
      height: '72px',
      background: 'linear-gradient(135deg, #8DE971 0%, #7AC75E 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      cursor: 'pointer',
      boxShadow: '0 4px 20px rgba(141, 233, 113, 0.35)',
    },
    statusText: {
      fontSize: '0.8125rem',
      fontWeight: '600',
      color: '#475569',
      textAlign: 'center',
      letterSpacing: '0.02em',
    },
    hint: {
      fontSize: '0.6875rem',
      color: '#94a3b8',
      textAlign: 'center',
    },
    controls: {
      display: 'flex',
      gap: '0.5rem',
    },
    button: {
      padding: '0.5rem 1rem',
      borderRadius: '0.5rem',
      border: 'none',
      fontSize: '0.75rem',
      fontWeight: '600',
      cursor: 'pointer',
      transition: 'all 0.2s',
    },
    primaryButton: {
      background: 'linear-gradient(135deg, #8DE971 0%, #7AC75E 100%)',
      color: 'white',
    },
    secondaryButton: {
      backgroundColor: '#f1f5f9',
      color: '#64748b',
    },
  };

  useEffect(() => {
    return () => {
      stopListening({ notifyParent: false });
      stopSpeaking();
    };
  }, []);

  const startListening = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      // Setup audio context for visualization
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      analyserRef.current = audioContextRef.current.createAnalyser();
      const source = audioContextRef.current.createMediaStreamSource(stream);
      source.connect(analyserRef.current);
      analyserRef.current.fftSize = 256;

      // Start visualization
      visualizeAudio();

      // Setup media recorder
      mediaRecorderRef.current = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });

      audioChunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);

          // Reset silence timer on new audio
          if (silenceTimerRef.current) {
            clearTimeout(silenceTimerRef.current);
          }

          // Set new silence timer
          silenceTimerRef.current = setTimeout(() => {
            if (audioChunksRef.current.length > 0) {
              processAudio();
            }
          }, SILENCE_THRESHOLD);
        }
      };

      mediaRecorderRef.current.onstop = () => {
        if (audioChunksRef.current.length > 0) {
          processAudio();
        }
      };

      mediaRecorderRef.current.start(100); // Collect data every 100ms
      setIsListening(true);
      setIsPaused(false);
      setStatus('listening');

    } catch {
      alert('Could not access microphone. Please check permissions.');
    }
  };

  const stopListening = ({ notifyParent = false } = {}) => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
    }

    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
    }

    setIsListening(false);
    setIsPaused(false);
    setStatus('idle');
    setAudioLevel(0);

    // Notify parent only on explicit close actions.
    if (notifyParent && onStop) {
      onStop();
    }
  };

  const pauseListening = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.pause();
      setIsPaused(true);
      setStatus('paused');
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
      }
    }
  };

  const resumeListening = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'paused') {
      mediaRecorderRef.current.resume();
      setIsPaused(false);
      setStatus('listening');
    }
  };

  const processAudio = async () => {
    if (audioChunksRef.current.length === 0) return;

    setStatus('processing');

    const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
    audioChunksRef.current = [];

    // In transcribe mode, return the blob directly for parent to handle
    if (transcribeMode && onAudioReady) {
      onAudioReady(audioBlob);
      setTimeout(() => {
        if (isListening && !isPaused) setStatus('listening');
        else if (isPaused) setStatus('paused');
        else setStatus('idle');
      }, 500);
      return;
    }

    // Original flow: convert to base64 and send
    const reader = new FileReader();
    reader.onloadend = () => {
      const base64Audio = reader.result.split(',')[1];

      // Send to parent component
      if (onTranscript) {
        onTranscript({
          audio: base64Audio,
          format: 'webm',
          type: 'audio'
        });
      }

      // Reset status after a delay
      setTimeout(() => {
        if (isListening) {
          setStatus('listening');
        } else {
          setStatus('idle');
        }
      }, 1000);
    };
    reader.readAsDataURL(audioBlob);
  };

  const visualizeAudio = () => {
    if (!analyserRef.current) return;

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);

    const animate = () => {
      if (!isListening && status !== 'listening') return;

      analyserRef.current.getByteFrequencyData(dataArray);
      const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
      const normalized = Math.min(100, (average / 255) * 100);

      setAudioLevel(normalized);

      requestAnimationFrame(animate);
    };

    animate();
  };

  const playAudioResponse = async (audioData, format = 'mp3') => {
    try {
      setIsSpeaking(true);
      setIsSpeakingPaused(false);
      setStatus('speaking');

      // Stop listening while speaking
      const wasListening = isListening;
      if (wasListening) {
        stopListening({ notifyParent: false });
      }

      // Decode base64 to audio
      const audioBlob = base64ToBlob(audioData, `audio/${format}`);
      const audioUrl = URL.createObjectURL(audioBlob);

      const audio = new Audio(audioUrl);
      currentAudioRef.current = audio;

      audio.onended = () => {
        setIsSpeaking(false);
        setIsSpeakingPaused(false);
        setStatus('idle');
        URL.revokeObjectURL(audioUrl);
        currentAudioRef.current = null;

        // Resume listening if it was active
        if (wasListening) {
          startListening();
        }
      };

      await audio.play();

    } catch {
      setIsSpeaking(false);
      setIsSpeakingPaused(false);
      setStatus('idle');
    }
  };

  const playTextWithBrowserTTS = (text, speed = 1.0) => {
    if ('speechSynthesis' in window) {
      // Stop any ongoing speech
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = speed;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;

      // Try to use a specific voice
      const voices = window.speechSynthesis.getVoices();
      const selectedVoice = voices.find(v => v.name.includes('Female') || v.name.includes('Google UK English Female'));
      if (selectedVoice) {
        utterance.voice = selectedVoice;
      }

      utterance.onstart = () => {
        setIsSpeaking(true);
        setIsSpeakingPaused(false);
        setStatus('speaking');
      };

      utterance.onend = () => {
        setIsSpeaking(false);
        setIsSpeakingPaused(false);
        setStatus('idle');
      };

      window.speechSynthesis.speak(utterance);
    }
  };

  const toggleSpeakingPause = () => {
    if (currentAudioRef.current) {
      if (currentAudioRef.current.paused) {
        currentAudioRef.current.play();
        setIsSpeakingPaused(false);
      } else {
        currentAudioRef.current.pause();
        setIsSpeakingPaused(true);
      }
    }
    if ('speechSynthesis' in window) {
      if (window.speechSynthesis.paused) {
        window.speechSynthesis.resume();
        setIsSpeakingPaused(false);
      } else if (window.speechSynthesis.speaking) {
        window.speechSynthesis.pause();
        setIsSpeakingPaused(true);
      }
    }
  };

  const stopSpeaking = () => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }

    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }

    setIsSpeaking(false);
    setIsSpeakingPaused(false);
    setStatus('idle');
  };

  const base64ToBlob = (base64, mimeType) => {
    const byteCharacters = atob(base64);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    return new Blob([byteArray], { type: mimeType });
  };

  const toggleListening = () => {
    if (isListening) {
      stopListening({ notifyParent: true });
    } else {
      startListening();
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'listening':
        return 'Listening...';
      case 'paused':
        return 'Paused';
      case 'processing':
        return 'Processing...';
      case 'speaking':
        return isSpeakingPaused ? 'Paused' : 'Speaking...';
      default:
        return 'Tap to speak';
    }
  };

  const getIcon = () => {
    const iconStyle = { width: '1.75rem', height: '1.75rem' };
    switch (status) {
      case 'listening':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={iconStyle}>
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" y1="19" x2="12" y2="23" />
            <line x1="8" y1="23" x2="16" y2="23" />
          </svg>
        );
      case 'paused':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={iconStyle}>
            <rect x="6" y="4" width="4" height="16" />
            <rect x="14" y="4" width="4" height="16" />
          </svg>
        );
      case 'processing':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ ...iconStyle, animation: 'spin 1s linear infinite' }}>
            <path d="M21 12a9 9 0 1 1-6.219-8.56" />
          </svg>
        );
      case 'speaking':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={iconStyle}>
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
          </svg>
        );
      default:
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={iconStyle}>
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" y1="19" x2="12" y2="23" />
            <line x1="8" y1="23" x2="16" y2="23" />
          </svg>
        );
    }
  };

  // Expose methods to parent
  useEffect(() => {
    if (onAudioResponse) {
      window.playVoiceResponse = (audioData, format, useBrowserTTS, text) => {
        if (useBrowserTTS && text) {
          playTextWithBrowserTTS(text);
        } else if (audioData) {
          playAudioResponse(audioData, format);
        }
      };
    }
  }, [onAudioResponse]);

  return (
    <div style={styles.container}>
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes voicePulse { 0%, 100% { opacity: 0.08; } 50% { opacity: 0.2; } }
      `}</style>

      <div style={styles.visualizer}>
        <div
          style={{
            ...styles.circle,
            ...styles.outerCircle,
            transform: `scale(${1 + (audioLevel / 100) * 0.35})`,
            opacity: isListening && !isPaused ? 0.18 : 0.08,
            animation: isListening && !isPaused ? 'voicePulse 2s ease-in-out infinite' : 'none',
          }}
        />
        <div
          style={{
            ...styles.circle,
            ...styles.middleCircle,
            transform: `scale(${1 + (audioLevel / 100) * 0.2})`,
            opacity: isListening && !isPaused ? 0.25 : 0.15,
          }}
        />
        <div
          style={{
            ...styles.circle,
            ...styles.innerCircle,
            transform: `scale(${1 + (audioLevel / 100) * 0.1})`,
            opacity: isListening ? 1 : 0.85,
          }}
          onClick={toggleListening}
        >
          {getIcon()}
        </div>
      </div>

      <div>
        <div style={styles.statusText}>{getStatusText()}</div>
        {status === 'idle' && (
          <div style={styles.hint}>Tap the mic to begin</div>
        )}
      </div>

      {(isSpeaking || isListening) && (
        <div style={styles.controls}>
          {isSpeaking && (
            <>
              <button
                style={{ ...styles.button, ...styles.secondaryButton }}
                onClick={toggleSpeakingPause}
              >
                {isSpeakingPaused ? 'Resume' : 'Pause'}
              </button>
              <button
                style={{ ...styles.button, ...styles.secondaryButton, color: '#b91c1c' }}
                onClick={stopSpeaking}
              >
                Stop
              </button>
            </>
          )}
          {isListening && (
            <>
              <button
                style={{ ...styles.button, ...styles.secondaryButton }}
                onClick={isPaused ? resumeListening : pauseListening}
              >
                {isPaused ? 'Resume' : 'Pause'}
              </button>
              <button
                style={{ ...styles.button, ...styles.secondaryButton, color: '#b91c1c' }}
                onClick={() => stopListening({ notifyParent: true })}
              >
                Stop
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default LiveVoiceChat;
