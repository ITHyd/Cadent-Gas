import { useState, useRef } from 'react';
import { createPortal } from 'react-dom';

const ImageUploader = ({ onImageCapture, disabled = false }) => {
  const [isCapturing, setIsCapturing] = useState(false);
  const [preview, setPreview] = useState(null);
  const fileInputRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  const styles = {
    button: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: '2.5rem',
      height: '2.5rem',
      borderRadius: '0.75rem',
      border: '1px solid #cbd5e1',
      backgroundColor: 'white',
      color: '#475569',
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.5 : 1,
      transition: 'all 0.2s',
    },
    modal: {
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.3)',
      backdropFilter: 'blur(6px)',
      WebkitBackdropFilter: 'blur(6px)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: '2rem',
    },
    modalContent: {
      backgroundColor: 'white',
      borderRadius: '1rem',
      padding: '1.5rem',
      maxWidth: '420px',
      width: '100%',
      maxHeight: '80vh',
      overflow: 'auto',
      boxShadow: '0 8px 32px rgba(0,0,0,0.12)',
    },
    title: {
      fontSize: '1rem',
      fontWeight: '700',
      color: '#030304',
      marginBottom: '1rem',
      textAlign: 'center',
    },
    optionsGrid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(2, 1fr)',
      gap: '0.75rem',
      marginBottom: '1rem',
    },
    optionButton: {
      padding: '1.25rem 1rem',
      borderRadius: '0.75rem',
      border: '1.5px solid #e2e8f0',
      backgroundColor: 'white',
      cursor: 'pointer',
      transition: 'all 0.2s',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '0.5rem',
    },
    optionIcon: {
      width: '2.5rem',
      height: '2.5rem',
      borderRadius: '0.75rem',
      background: 'linear-gradient(135deg, #8DE971 0%, #7AC75E 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    },
    optionText: {
      fontSize: '0.8125rem',
      fontWeight: '600',
      color: '#030304',
    },
    video: {
      width: '100%',
      borderRadius: '0.75rem',
      marginBottom: '0.75rem',
    },
    preview: {
      width: '100%',
      borderRadius: '0.75rem',
      marginBottom: '0.75rem',
    },
    actions: {
      display: 'flex',
      gap: '0.5rem',
      justifyContent: 'center',
    },
    actionButton: {
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
    canvas: {
      display: 'none',
    }
  };

  const handleButtonClick = () => {
    if (disabled) return;
    setIsCapturing(true);
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (event) => {
    const file = event.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64 = reader.result;
        setPreview(base64);
      };
      reader.readAsDataURL(file);
    }
  };

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' }
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch {
      alert('Could not access camera. Please upload a file instead.');
    }
  };

  const capturePhoto = () => {
    if (videoRef.current && canvasRef.current) {
      const video = videoRef.current;
      const canvas = canvasRef.current;

      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;

      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0);

      const base64 = canvas.toDataURL('image/jpeg');
      setPreview(base64);

      // Stop camera
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
    }
  };

  const handleSend = () => {
    if (preview) {
      // Extract base64 data without prefix
      const base64Data = preview.split(',')[1];
      onImageCapture(base64Data, 'jpeg');
      handleClose();
    }
  };

  const handleClose = () => {
    setIsCapturing(false);
    setPreview(null);
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
  };

  return (
    <>
      <button
        style={styles.button}
        onClick={handleButtonClick}
        disabled={disabled}
        title="Upload image"
        onMouseEnter={(e) => {
          if (!disabled) {
            e.currentTarget.style.borderColor = '#8DE971';
            e.currentTarget.style.color = '#8DE971';
          }
        }}
        onMouseLeave={(e) => {
          if (!disabled) {
            e.currentTarget.style.borderColor = '#cbd5e1';
            e.currentTarget.style.color = '#475569';
          }
        }}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" style={{ width: '1.25rem', height: '1.25rem' }} aria-hidden="true">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
          <circle cx="12" cy="13" r="4" />
        </svg>
      </button>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />

      {isCapturing && createPortal(
        <div style={styles.modal} onClick={handleClose}>
          <div style={styles.modalContent} onClick={(e) => e.stopPropagation()}>
            <div style={styles.title}>Upload Image</div>

            {!preview && !videoRef.current?.srcObject && (
              <div style={styles.optionsGrid}>
                <button
                  style={styles.optionButton}
                  onClick={handleFileSelect}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#8DE971';
                    e.currentTarget.style.backgroundColor = '#F6F2F4';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = '#e2e8f0';
                    e.currentTarget.style.backgroundColor = 'white';
                  }}
                >
                  <div style={styles.optionIcon}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '1.25rem', height: '1.25rem' }}>
                      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                    </svg>
                  </div>
                  <div style={styles.optionText}>Choose File</div>
                </button>

                <button
                  style={styles.optionButton}
                  onClick={startCamera}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = '#8DE971';
                    e.currentTarget.style.backgroundColor = '#F6F2F4';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = '#e2e8f0';
                    e.currentTarget.style.backgroundColor = 'white';
                  }}
                >
                  <div style={styles.optionIcon}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '1.25rem', height: '1.25rem' }}>
                      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                      <circle cx="12" cy="13" r="4" />
                    </svg>
                  </div>
                  <div style={styles.optionText}>Take Photo</div>
                </button>
              </div>
            )}

            {videoRef.current?.srcObject && !preview && (
              <>
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  style={styles.video}
                />
                <div style={styles.actions}>
                  <button
                    style={{...styles.actionButton, ...styles.primaryButton}}
                    onClick={capturePhoto}
                  >
                    Capture
                  </button>
                  <button
                    style={{...styles.actionButton, ...styles.secondaryButton}}
                    onClick={handleClose}
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}

            {preview && (
              <>
                <img src={preview} alt="Preview" style={styles.preview} />
                <div style={styles.actions}>
                  <button
                    style={{...styles.actionButton, ...styles.primaryButton}}
                    onClick={handleSend}
                  >
                    Send Image
                  </button>
                  <button
                    style={{...styles.actionButton, ...styles.secondaryButton}}
                    onClick={() => setPreview(null)}
                  >
                    Retake
                  </button>
                  <button
                    style={{...styles.actionButton, ...styles.secondaryButton}}
                    onClick={handleClose}
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}

            <canvas ref={canvasRef} style={styles.canvas} />
          </div>
        </div>,
        document.body
      )}
    </>
  );
};

export default ImageUploader;
