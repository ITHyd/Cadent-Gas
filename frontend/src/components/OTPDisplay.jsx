import { useState, useEffect } from 'react';

const OTPDisplay = ({ otp, phone }) => {
  const [visible, setVisible] = useState(true);
  const [timeLeft, setTimeLeft] = useState(300);

  useEffect(() => {
    setVisible(true);
    setTimeLeft(300);
    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          setVisible(false);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [otp]);

  if (!visible) return null;

  const minutes = Math.floor(timeLeft / 60);
  const seconds = timeLeft % 60;

  return (
    <div style={{
      position: 'fixed',
      bottom: '1.5rem',
      left: '1.5rem',
      backgroundColor: '#1e293b',
      color: 'white',
      padding: '1rem 1.5rem',
      borderRadius: '0.75rem',
      boxShadow: '0 10px 40px rgba(0,0,0,0.3)',
      zIndex: 9999,
      minWidth: '220px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <span style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Dev Mode - OTP
        </span>
        <button
          onClick={() => setVisible(false)}
          style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '1rem', padding: '0 0.25rem' }}
        >
          x
        </button>
      </div>
      <div style={{ fontSize: '2rem', fontWeight: 'bold', letterSpacing: '0.5rem', fontFamily: 'monospace' }}>
        {otp}
      </div>
      <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '0.25rem' }}>
        For: {phone}
      </div>
      <div style={{ fontSize: '0.75rem', color: timeLeft < 60 ? '#ef4444' : '#94a3b8', marginTop: '0.25rem' }}>
        Expires in: {minutes}:{seconds.toString().padStart(2, '0')}
      </div>
    </div>
  );
};

export default OTPDisplay;
