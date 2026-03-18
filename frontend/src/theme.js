/**
 * NxZen "Future Foresight" Theme Constants
 * Central theme file for inline styles across the application.
 */

/* ── Core Brand Colors ── */
export const colors = {
  deepSpaceBlack: '#030304',
  lumenGreen: '#8DE971',
  iridescentPearl: '#F6F2F4',
  neonViolet: '#AD96DC',

  /* Extended */
  brandBlue: '#6B9BFF',
  brandYellow: '#FFD93D',
  brandRed: '#FF6B6B',
  brandCyan: '#74D1EA',
  brandCoral: '#FF7276',
  chartYellow: '#ECF166',

  /* Derived */
  textPrimary: '#030304',
  textSecondary: 'rgba(3, 3, 4, 0.7)',
  textFaint: 'rgba(3, 3, 4, 0.5)',
  surface: '#FFFFFF',
  surfaceMuted: '#F6F2F4',
  bgBase: '#F6F2F4',
  bgSoft: '#FAF8F9',
  borderSoft: 'rgba(3, 3, 4, 0.1)',
  borderStrong: 'rgba(3, 3, 4, 0.2)',

  /* Success / Warning / Danger */
  ok: '#8DE971',
  warn: '#FFD93D',
  danger: '#FF6B6B',
  info: '#6B9BFF',
};

/* ── Transparency Levels ── */
export const transparency = {
  10: 'rgba(246, 242, 244, 0.1)',
  20: 'rgba(246, 242, 244, 0.2)',
  30: 'rgba(246, 242, 244, 0.3)',
  40: 'rgba(246, 242, 244, 0.4)',
  50: 'rgba(246, 242, 244, 0.5)',
  60: 'rgba(246, 242, 244, 0.6)',
  70: 'rgba(246, 242, 244, 0.7)',
  80: 'rgba(246, 242, 244, 0.8)',
  90: 'rgba(246, 242, 244, 0.9)',
};

/* ── Gradients ── */
export const gradients = {
  primary: 'linear-gradient(135deg, #8DE971 0%, #7AC75E 100%)',
  secondary: 'linear-gradient(135deg, #AD96DC 0%, #9B86C7 100%)',
  accent: 'linear-gradient(135deg, #F6F2F4 0%, #E6E2E4 100%)',
  primaryButton: 'linear-gradient(135deg, #8DE971 0%, #7AC75E 100%)',
  darkSection: 'linear-gradient(135deg, #030304 0%, #1a1a2e 100%)',
  hero: 'linear-gradient(135deg, #030304 0%, #0d0d1a 50%, #1a1a2e 100%)',
  chart1: 'linear-gradient(135deg, #ECF166 0%, #DBE056 100%)',
  chart2: 'linear-gradient(135deg, #74D1EA 0%, #63C0D9 100%)',
  chart3: 'linear-gradient(135deg, #FF7276 0%, #EE6165 100%)',
};

/* ── Shadows ── */
export const shadows = {
  card: '0 8px 32px rgba(0, 0, 0, 0.08)',
  cardHover: '0 8px 32px rgba(141, 233, 113, 0.12)',
  soft: '0 20px 45px -30px rgba(3, 3, 4, 0.15)',
  button: '0 0 20px rgba(141, 233, 113, 0.3)',
  buttonHover: '0 0 25px rgba(141, 233, 113, 0.4)',
  glow: '0 0 20px rgba(141, 233, 113, 0.3)',
  violetGlow: '0 0 20px rgba(173, 150, 220, 0.3)',
};

/* ── Typography ── */
export const fonts = {
  heading: "'Canela', 'Times New Roman', serif",
  subheading: "'Corporative Sans Rounded', 'Arial Rounded MT Bold', 'Arial', sans-serif",
  body: "'Corporative Sans Rounded', 'Calibri', 'Arial', sans-serif",
  highlight: "'Testimonia', 'Brush Script MT', cursive",
  /* Web-safe fallbacks */
  headingSafe: "'Times New Roman', serif",
  subheadingSafe: "'Arial Rounded MT Bold', 'Arial', sans-serif",
  bodySafe: "'Calibri', 'Arial', sans-serif",
};

/* ── Spacing / Radius ── */
export const radius = {
  card: '16px',
  input: '8px',
  button: '8px',
  badge: '9999px',
  panel: '16px',
};

/* ── Common style patterns ── */
export const patterns = {
  card: {
    background: '#FFFFFF',
    borderRadius: '16px',
    padding: '24px',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.08)',
    border: '1px solid rgba(3, 3, 4, 0.1)',
    transition: 'all 0.3s ease',
  },
  cardHover: {
    boxShadow: '0 8px 32px rgba(141, 233, 113, 0.12)',
    borderColor: 'rgba(141, 233, 113, 0.3)',
    transform: 'translateY(-2px)',
  },
  glassCard: {
    background: 'rgba(246, 242, 244, 0.05)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(173, 150, 220, 0.2)',
    boxShadow: '0 8px 32px rgba(3, 3, 4, 0.2)',
    borderRadius: '16px',
  },
  input: {
    width: '100%',
    padding: '0.75rem 1rem',
    background: '#f3f4f6',
    border: '2px solid rgba(3, 3, 4, 0.2)',
    borderRadius: '8px',
    color: '#030304',
    fontSize: '14px',
    transition: 'all 0.3s ease',
    outline: 'none',
  },
  inputFocus: {
    borderColor: '#8DE971',
    boxShadow: '0 0 20px rgba(141, 233, 113, 0.2)',
  },
  primaryButton: {
    background: 'linear-gradient(135deg, #8DE971 0%, #7AC75E 100%)',
    color: '#030304',
    fontWeight: '600',
    padding: '0.75rem 1.5rem',
    borderRadius: '8px',
    border: 'none',
    boxShadow: '0 0 20px rgba(141, 233, 113, 0.3)',
    transition: 'all 0.3s ease',
    cursor: 'pointer',
  },
  primaryButtonHover: {
    background: 'linear-gradient(135deg, #AD96DC 0%, #9B86C7 100%)',
    transform: 'scale(1.05)',
    boxShadow: '0 0 25px rgba(141, 233, 113, 0.4)',
  },
  secondaryButton: {
    background: 'transparent',
    color: '#AD96DC',
    border: '2px solid #AD96DC',
    fontWeight: '600',
    padding: '0.75rem 1.5rem',
    borderRadius: '8px',
    boxShadow: '0 0 15px rgba(173, 150, 220, 0.2)',
    transition: 'all 0.3s ease',
    cursor: 'pointer',
  },
  secondaryButtonHover: {
    background: '#AD96DC',
    color: '#030304',
    transform: 'scale(1.05)',
  },
  badge: {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '0.25rem 0.75rem',
    borderRadius: '9999px',
    fontSize: '0.875rem',
    fontWeight: '600',
    backdropFilter: 'blur(4px)',
  },
  badgeSuccess: {
    background: 'rgba(141, 233, 113, 0.2)',
    color: '#4CAF50',
    border: '1px solid rgba(141, 233, 113, 0.3)',
  },
  badgeWarning: {
    background: 'rgba(255, 217, 61, 0.2)',
    color: '#F59E0B',
    border: '1px solid rgba(255, 217, 61, 0.3)',
  },
  badgeDanger: {
    background: 'rgba(255, 107, 107, 0.2)',
    color: '#EF4444',
    border: '1px solid rgba(255, 107, 107, 0.3)',
  },
  badgeInfo: {
    background: 'rgba(107, 155, 255, 0.2)',
    color: '#3B82F6',
    border: '1px solid rgba(107, 155, 255, 0.3)',
  },
};

export default { colors, transparency, gradients, shadows, fonts, radius, patterns };
