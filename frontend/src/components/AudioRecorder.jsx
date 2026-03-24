import { useRef } from 'react';

const AudioRecorder = ({ onRecordingComplete, isRecording, setIsRecording, disabled = false }) => {
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const startRecording = async () => {
    if (disabled) return;

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        onRecordingComplete(audioBlob);

        // Release microphone as soon as recording ends.
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch {
      setIsRecording(false);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const toggleRecording = () => {
    if (disabled) return;

    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const buttonStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '2.5rem',
    height: '2.5rem',
    borderRadius: '0.75rem',
    border: isRecording ? 'none' : '1px solid #cbd5e1',
    backgroundColor: isRecording ? '#e11d48' : 'white',
    color: isRecording ? 'white' : '#475569',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    transition: 'all 0.2s',
    animation: isRecording ? 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' : 'none',
  };

  const iconStyle = {
    width: isRecording ? '1rem' : '1.25rem',
    height: isRecording ? '1rem' : '1.25rem',
  };

  return (
    <>
      <style>
        {`
          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
          }
        `}
      </style>
      <button
        type="button"
        onClick={toggleRecording}
        disabled={disabled}
        title={isRecording ? 'Stop recording' : 'Start voice recording'}
        style={buttonStyle}
        onMouseEnter={(e) => {
          if (!disabled && !isRecording) {
            e.target.style.borderColor = '#8DE971';
            e.target.style.color = '#8DE971';
          }
        }}
        onMouseLeave={(e) => {
          if (!disabled && !isRecording) {
            e.target.style.borderColor = '#cbd5e1';
            e.target.style.color = '#475569';
          }
        }}
      >
        {isRecording ? (
          <svg viewBox="0 0 24 24" fill="currentColor" style={iconStyle} aria-hidden="true">
            <rect x="7" y="7" width="10" height="10" rx="1.5" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" style={iconStyle} aria-hidden="true">
            <path d="M12 15a3 3 0 0 0 3-3V7a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Z" />
            <path d="M5 11v1a7 7 0 0 0 14 0v-1" />
            <path d="M12 19v3" />
          </svg>
        )}
      </button>
    </>
  );
};

export default AudioRecorder;
