/**
 * HeroSection — full-viewport hero landing page with gradient background.
 *
 * Extracted from ProfessionalDashboard. Shows logo, title, subtitle, CTA buttons,
 * and feature cards.
 *
 * Used by ProfessionalDashboard.
 */
import { Flame } from 'lucide-react';

const DEFAULT_GRADIENT = "#8DE971";

const DEFAULT_FEATURES = [
  { icon: "🎤", title: "Voice Recognition", desc: "Speak naturally, we understand" },
  { icon: "⚡", title: "Instant Analysis", desc: "Real-time risk assessment" },
  { icon: "🤖", title: "AI Agent Assistant", desc: "Intelligent guidance system" },
  { icon: "🔒", title: "Secure & Private", desc: "Enterprise-grade security" },
];

export default function HeroSection({
  logoIcon = <Flame size={28} color="#f97316" />,
  logoText = "Gas Intelligence",
  title = "AI-Powered Gas\nIncident Response",
  subtitle = "Report incidents instantly with voice or text. Our intelligent system analyzes and responds in real-time.",
  features = DEFAULT_FEATURES,
  primaryGradient = DEFAULT_GRADIENT,
  textColor = "#102842",
  onStartChat,
  reportsLink = "/my-reports",
}) {
  const styles = getStyles(primaryGradient, textColor);

  return (
    <div style={styles.container}>
      <div style={styles.mainPanel}>
        <div style={styles.backgroundPattern} />
        <div style={styles.content}>
          {/* Logo */}
          <div style={styles.logo}>
            <div style={styles.logoIcon}>
              {typeof logoIcon === "string" ? logoIcon : logoIcon}
            </div>
            <span style={styles.logoText}>{logoText}</span>
          </div>

          {/* Title */}
          <h1 style={styles.title}>
            {title.split("\n").map((line, i) => (
              <span key={i}>
                {i > 0 && <br />}
                {line}
              </span>
            ))}
          </h1>

          {/* Subtitle */}
          <p style={styles.subtitle}>{subtitle}</p>

          {/* CTA Buttons */}
          <div style={styles.buttonsRow}>
            <button
              style={styles.startButton}
              onClick={onStartChat}
              onMouseEnter={(e) => {
                e.target.style.transform = "translateY(-1px)";
                e.target.style.boxShadow = "0 20px 28px -22px rgba(3, 3, 4, 0.95)";
              }}
              onMouseLeave={(e) => {
                e.target.style.transform = "translateY(0)";
                e.target.style.boxShadow = "0 18px 26px -22px rgba(3, 3, 4, 0.9)";
              }}
            >
              <span>Start Incident Report</span>
            </button>

            <a
              href={reportsLink}
              style={styles.reportsButton}
              onMouseEnter={(e) => {
                e.target.style.transform = "translateY(-1px)";
                e.target.style.backgroundColor = "#edf5fc";
              }}
              onMouseLeave={(e) => {
                e.target.style.transform = "translateY(0)";
                e.target.style.backgroundColor = "transparent";
              }}
            >
              <span>View My Reports</span>
            </a>
          </div>

          {/* Feature Cards */}
          <div style={styles.features}>
            {features.map((f) => (
              <div key={f.title} style={styles.feature}>
                <div style={styles.featureIcon}>{f.icon}</div>
                <div style={styles.featureText}>
                  <div style={styles.featureTitle}>{f.title}</div>
                  <div style={styles.featureDesc}>{f.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function getStyles(gradient, textColor) {
  return {
    container: {
      height: "100vh",
      backgroundColor: "#eaf2f9",
      overflow: "hidden",
      position: "relative",
    },
    mainPanel: {
      height: "100%",
      display: "flex",
      flexDirection: "column",
      justifyContent: "center",
      padding: "clamp(1.2rem, 4vw, 4rem)",
      background:
        "radial-gradient(circle at 10% 10%, rgba(3, 3, 4, 0.16), transparent 34%), radial-gradient(circle at 100% 100%, rgba(141, 233, 113, 0.12), transparent 38%), linear-gradient(160deg, #f8fbff 0%, #eef4fa 54%, #e8f1f8 100%)",
      position: "relative",
      overflow: "hidden",
    },
    backgroundPattern: {
      position: "absolute",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      opacity: 0.24,
      backgroundImage:
        "linear-gradient(to right, rgba(130, 149, 171, 0.08) 1px, transparent 1px), linear-gradient(to bottom, rgba(130, 149, 171, 0.08) 1px, transparent 1px)",
      backgroundSize: "42px 42px",
    },
    content: {
      position: "relative",
      zIndex: 1,
      maxWidth: "860px",
      marginLeft: "clamp(0rem, 5vw, 6rem)",
    },
    logo: {
      display: "flex",
      alignItems: "center",
      gap: "1rem",
      marginBottom: "2.5rem",
    },
    logoIcon: {
      width: "3rem",
      height: "3rem",
      background: gradient,
      borderRadius: "0.75rem",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: "1.3rem",
      boxShadow: "0 14px 24px -18px rgba(3, 3, 4, 0.75)",
      overflow: "hidden",
    },
    logoText: {
      fontSize: "1.5rem",
      fontWeight: "700",
      color: textColor,
      letterSpacing: "-0.02em",
      fontFamily: "Playfair Display, Times New Roman, serif",
    },
    title: {
      fontSize: "clamp(2.2rem, 5vw, 4rem)",
      fontWeight: "800",
      color: textColor,
      marginBottom: "1rem",
      lineHeight: "1.08",
      letterSpacing: "-0.03em",
      fontFamily: "Playfair Display, Times New Roman, serif",
    },
    subtitle: {
      fontSize: "1.12rem",
      color: "#4d6178",
      marginBottom: "2rem",
      lineHeight: "1.6",
      maxWidth: "58ch",
    },
    buttonsRow: {
      display: "flex",
      gap: "1rem",
      alignItems: "center",
      flexWrap: "wrap",
    },
    startButton: {
      display: "inline-flex",
      alignItems: "center",
      gap: "0.75rem",
      padding: "0.95rem 1.8rem",
      background: gradient,
      color: "#030304",
      border: "1px solid rgba(255,255,255,0.16)",
      borderRadius: "0.8rem",
      fontSize: "1rem",
      fontWeight: "700",
      cursor: "pointer",
      transition: "all 0.3s",
      boxShadow: "0 18px 26px -22px rgba(3, 3, 4, 0.9)",
    },
    reportsButton: {
      display: "inline-flex",
      alignItems: "center",
      gap: "0.75rem",
      padding: "0.95rem 1.8rem",
      background: "transparent",
      color: textColor,
      border: `2px solid ${textColor}`,
      borderRadius: "0.8rem",
      fontSize: "1rem",
      fontWeight: "700",
      cursor: "pointer",
      transition: "all 0.3s",
      textDecoration: "none",
      boxShadow: "none",
    },
    features: {
      marginTop: "2.6rem",
      display: "grid",
      gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
      gap: "0.95rem",
    },
    feature: {
      display: "flex",
      alignItems: "start",
      gap: "0.75rem",
      border: "1px solid #d3e0eb",
      background: "rgba(255,255,255,0.78)",
      backdropFilter: "blur(4px)",
      borderRadius: "12px",
      padding: "0.8rem",
    },
    featureIcon: {
      width: "2.2rem",
      height: "2.2rem",
      background: gradient,
      borderRadius: "0.5rem",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: "1rem",
      flexShrink: 0,
      boxShadow: "0 8px 12px -10px rgba(3, 3, 4, 0.7)",
    },
    featureText: { flex: 1 },
    featureTitle: {
      color: "#123050",
      fontWeight: "700",
      marginBottom: "0.25rem",
      fontSize: "0.85rem",
    },
    featureDesc: {
      color: "#668198",
      fontSize: "0.74rem",
      lineHeight: "1.4",
    },
  };
}
