import { useRef, useState } from 'react';

const VideoRecorder = ({ onRecordingComplete, isRecording, setIsRecording, disabled = false }) => {
  const mediaRecorderRef = useRef(null);
  const videoChunksRef = useRef([]);
  const streamRef = useRef(null);

  const startRecording = async () => {
    if (disabled) return;

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      alert('Video recording is not supported in your browser.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: true, 
        audio: true 
      });
      
      streamRef.current = stream;
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      videoChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          videoChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const videoBlob = new Blob(videoChunksRef.current, { type: 'video/webm' });
        onRecordingComplete(videoBlob);

        // Release camera and microphone
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch {
      alert('Could not access camera/microphone. Please check permissions.');
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
    backgroundColor: isRecording ? '#dc2626' : 'white',
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
        title={isRecording ? 'Stop video recording' : 'Start video recording'}
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
            <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
        )}
      </button>
    </>
  );
};

export default VideoRecorder;
