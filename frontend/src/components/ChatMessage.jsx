import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { formatIncidentId, formatReferenceId } from "../utils/incidentIds";
import {
  getWorkflowOptionVisual,
  hasWorkflowOptionVisuals,
} from "../utils/workflowOptionImages";

const WorkflowOptionButton = ({
  option,
  visual,
  showVisualOptions,
  onOptionClick,
  onPreviewImage,
  disabled = false,
}) => {
  const [imageFailed, setImageFailed] = useState(false);
  const [showHoverLabel, setShowHoverLabel] = useState(false);
  const hoverTimerRef = useRef(null);
  const hideBrandText =
    visual?.kind === "manufacturer" && visual?.imageUrl && !imageFailed;
  const isLogoOnlyBrandCard = visual?.kind === "manufacturer" && hideBrandText;
  const canPreviewImage = visual?.kind === "model" && !!visual?.imageUrl && !imageFailed;
  const hasModelVisual = visual?.kind === "model" && !!visual?.imageUrl;
  const showImageHoverCaption =
    !!visual?.imageUrl && !imageFailed && showHoverLabel;
  const showInlineLabel = !hideBrandText;

  useEffect(() => {
    return () => {
      if (hoverTimerRef.current) {
        clearTimeout(hoverTimerRef.current);
      }
    };
  }, []);

  const handleMouseEnter = (e) => {
    if (disabled) return;
    e.currentTarget.style.borderColor = "#76a0c4";
    e.currentTarget.style.backgroundColor = "#edf5fc";
    e.currentTarget.style.transform = "translateY(-2px) scale(1.02)";
    e.currentTarget.style.boxShadow =
      "0 16px 22px -20px rgba(3, 3, 4, 0.95)";

    if (visual?.imageUrl && !imageFailed) {
      hoverTimerRef.current = setTimeout(() => {
        setShowHoverLabel(true);
      }, 650);
    }
  };

  const handleMouseLeave = (e) => {
    if (disabled) return;
    e.currentTarget.style.borderColor = "#d4e1ed";
    e.currentTarget.style.backgroundColor = "#f8fbff";
    e.currentTarget.style.transform = "translateY(0) scale(1)";
    e.currentTarget.style.boxShadow =
      "0 8px 14px -14px rgba(15, 31, 51, 0.5)";

    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    setShowHoverLabel(false);
  };

  return (
    <button
      onClick={() => {
        if (disabled) return;
        if (hasModelVisual) {
          onPreviewImage &&
            onPreviewImage({
              imageUrl: visual.imageUrl,
              label: option.label,
            });
          return;
        }
        onOptionClick(option.label);
      }}
      disabled={disabled}
      style={{
        padding: showVisualOptions ? "12px" : "10px 12px",
        backgroundColor: "#f8fbff",
        border: "1px solid #d4e1ed",
        borderRadius: "11px",
        fontSize: "13px",
        fontWeight: "600",
        color: "#19314a",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "all 0.2s ease",
        textAlign: "left",
        boxShadow: "0 8px 14px -14px rgba(15, 31, 51, 0.5)",
        minHeight: showVisualOptions
          ? isLogoOnlyBrandCard
            ? "118px"
            : "156px"
          : "auto",
        display: "flex",
        flexDirection: "column",
        alignItems: showVisualOptions ? "stretch" : "flex-start",
        justifyContent: isLogoOnlyBrandCard ? "center" : "flex-start",
        gap: showVisualOptions ? (hideBrandText ? "0" : "10px") : "0",
      }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {visual?.imageUrl && !imageFailed && (
        <div
          onClick={(e) => {
            if (canPreviewImage) {
              e.stopPropagation();
              onPreviewImage &&
                onPreviewImage({
                  imageUrl: visual.imageUrl,
                  label: option.label,
                });
            }
          }}
          style={{
            height: "82px",
            borderRadius: "9px",
            background: "linear-gradient(180deg, #ffffff 0%, #eef5fb 100%)",
            border: "1px solid #dde8f2",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
            padding: "8px",
            position: "relative",
            cursor: canPreviewImage ? "zoom-in" : "default",
          }}
        >
          <img
            src={visual.imageUrl}
            alt={option.label}
            onError={() => setImageFailed(true)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "contain",
              display: "block",
            }}
          />
          {showImageHoverCaption && (
            <div
              style={{
                position: "absolute",
                left: "8px",
                right: "8px",
                bottom: "8px",
                background: "rgba(3, 3, 4, 0.78)",
                color: "#ffffff",
                borderRadius: "7px",
                padding: "5px 7px",
                fontSize: "11px",
                lineHeight: "1.25",
                textAlign: "center",
              }}
            >
              {option.label}
            </div>
          )}
        </div>
      )}
      {showInlineLabel && (
        <span
          style={{
            display: "block",
            lineHeight: "1.35",
          }}
        >
          {option.label}
        </span>
      )}
    </button>
  );
};

const ChatMessage = ({
  message,
  onOptionClick,
  onStartNewIncident,
  onOpenIncident,
  onPreviewImage,
}) => {
  const navigate = useNavigate();
  const isAgent = message.role === "agent";
  const [isVisible, setIsVisible] = useState(false);

  // Fade-in animation on mount
  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), 50);
    return () => clearTimeout(timer);
  }, []);

  // Get options from workflow data
  // Normalize scored option objects {"label": "...", "score": N} to plain label strings
  const rawOptions =
    message.data?.options || message.data?.common_incidents || [];
  const normalizedDataOptions = rawOptions.map((opt) => ({
    raw: opt,
    label: typeof opt === "object" && opt !== null && opt.label ? opt.label : opt,
  }));
  const messageOptions = normalizedDataOptions;
  const showVisualOptions = hasWorkflowOptionVisuals(
    message.data,
    rawOptions,
  );

  // Format timestamp
  const formatTime = (timestamp) => {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
  };

  // Linkify incident IDs into clickable links
  const linkifyIncidentIds = (text, lineKey) => {
    if (!isAgent) return text;

    const incidentRefRegex = /\b(?:INC|REF)[-_][A-Z0-9]+\b/g;
    if (!incidentRefRegex.test(text)) return text;

    const parts = [];
    let lastIndex = 0;
    let match;
    incidentRefRegex.lastIndex = 0;
    while ((match = incidentRefRegex.exec(text)) !== null) {
      if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
      const rawId = match[0].toUpperCase();
      const routeIncidentId = formatIncidentId(rawId);
      const displayId = rawId.startsWith("REF")
        ? formatReferenceId(rawId)
        : formatIncidentId(rawId);
      parts.push(
        <span
          key={`${lineKey}-inc-${match.index}`}
          onClick={() => navigate(`/my-reports/${routeIncidentId}`)}
          style={{
            color: "#2563eb",
            fontWeight: "700",
            cursor: "pointer",
            textDecoration: "underline",
            textUnderlineOffset: "2px",
          }}
        >
          {displayId}
        </span>
      );
      lastIndex = incidentRefRegex.lastIndex;
    }
    if (lastIndex < text.length) parts.push(text.slice(lastIndex));
    return parts;
  };

  // Format the message content
  const formatContent = (text) => {
    if (!text) return "";

    const lines = text.split("\n");
    const formattedLines = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.trim() === "") {
        formattedLines.push(<br key={`br-${i}`} />);
        continue;
      }

      // Handle bullet points
      if (line.trim().startsWith("•")) {
        const bulletText = line.replace(/^[•]\s*/, "");
        formattedLines.push(
          <div
            key={i}
            style={{
              display: "flex",
              gap: "0.5rem",
              marginLeft: "1rem",
              marginTop: "0.25rem",
            }}
          >
            <span
              style={{
                color: isAgent ? "#3b82f6" : "rgba(255,255,255,0.9)",
                fontWeight: "bold",
              }}
            >
              •
            </span>
            <span>{linkifyIncidentIds(bulletText, `bullet-${i}`)}</span>
          </div>,
        );
        continue;
      }

      // Handle numbered lists
      const numberedMatch = line.match(/^(\d+)\.\s+(.+)$/);
      if (numberedMatch) {
        formattedLines.push(
          <div
            key={i}
            style={{
              display: "flex",
              gap: "0.5rem",
              marginLeft: "1rem",
              marginTop: "0.25rem",
            }}
          >
            <span
              style={{
                color: isAgent ? "#3b82f6" : "rgba(255,255,255,0.9)",
                fontWeight: "bold",
              }}
            >
              {numberedMatch[1]}.
            </span>
            <span>{linkifyIncidentIds(numberedMatch[2], `num-${i}`)}</span>
          </div>,
        );
        continue;
      }

      // Check for **bold** text (workflow question from AI enhancement)
      const boldMatch = line.match(/^(.*?)\*\*(.+?)\*\*(.*)$/);
      if (boldMatch) {
        const [, before, boldText, after] = boldMatch;
        formattedLines.push(
          <div key={i} style={{ marginTop: "0.25rem" }}>
            {before.trim() && <span>{linkifyIncidentIds(before.trim(), `bold-b-${i}`)}</span>}
            <div style={{ fontWeight: "bold", marginTop: "0.25rem" }}>
              {linkifyIncidentIds(boldText, `bold-${i}`)}
              {after.trim() && <span style={{ fontWeight: "normal" }}>{linkifyIncidentIds(after, `bold-a-${i}`)}</span>}
            </div>
          </div>,
        );
        continue;
      }

      // Regular line
      formattedLines.push(
        <div key={i} style={{ marginTop: "0.25rem" }}>
          <span>{linkifyIncidentIds(line, `line-${i}`)}</span>
        </div>,
      );
    }

    return formattedLines;
  };

  const bubbleStyles = {
    opacity: isVisible ? 1 : 0,
    transform: isVisible ? "translateY(0)" : "translateY(10px)",
    transition: "opacity 0.28s ease, transform 0.28s ease",
    marginBottom: "14px",
    display: "flex",
    justifyContent: isAgent ? "flex-start" : "flex-end",
  };

  const contentStyles = {
    maxWidth: "82%",
    position: "relative",
  };

  const messageBubbleStyles = isAgent
    ? {
      padding: "13px 14px",
      borderRadius: "14px",
      border: "1px solid #d8e3ee",
      background: "#ffffff",
      boxShadow: "0 12px 24px -22px rgba(15, 31, 51, 0.45)",
      fontSize: "15px",
      lineHeight: "1.55",
      color: "#162338",
      position: "relative",
      transition: "all 0.2s ease",
    }
    : {
      padding: "13px 14px",
      borderRadius: "14px",
      border: "1px solid rgba(3, 3, 4, 0.16)",
      background: "#030304",
      boxShadow: "0 16px 24px -20px rgba(3, 3, 4, 0.85)",
      fontSize: "15px",
      lineHeight: "1.55",
      color: "#ffffff",
      transition: "all 0.2s ease",
    };

  const timestampStyles = {
    fontSize: "11px",
    color: "#7890a9",
    marginTop: "5px",
    textAlign: isAgent ? "left" : "right",
    fontWeight: 500,
  };

  return (
    <div style={bubbleStyles}>
      <div style={contentStyles}>
        <div
          style={messageBubbleStyles}
          onMouseEnter={(e) => {
            if (isAgent) {
              e.currentTarget.style.boxShadow =
                "0 18px 28px -22px rgba(15, 31, 51, 0.55)";
              e.currentTarget.style.transform = "translateY(-1px)";
            }
          }}
          onMouseLeave={(e) => {
            if (isAgent) {
              e.currentTarget.style.boxShadow =
                "0 12px 24px -22px rgba(15, 31, 51, 0.45)";
              e.currentTarget.style.transform = "translateY(0)";
            }
          }}
        >
          {message.imageUrl && (
            <div style={{ marginBottom: message.content ? "8px" : 0 }}>
              <img
                src={message.imageUrl}
                alt="Uploaded"
                style={{
                  maxWidth: "100%",
                  maxHeight: "200px",
                  borderRadius: "8px",
                  display: "block",
                  objectFit: "cover",
                }}
              />
            </div>
          )}
          {formatContent(message.content)}
        </div>

        {message.timestamp && (
          <div style={timestampStyles}>{formatTime(message.timestamp)}</div>
        )}

        {/* Render option buttons if available */}
        {isAgent &&
          messageOptions &&
          messageOptions.length > 0 &&
          onOptionClick && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(2, 1fr)",
                gap: "8px",
                marginTop: "12px",
              }}
            >
              {messageOptions.map((option, index) => {
                const visual = getWorkflowOptionVisual(message.data, option.raw);

                return (
                  <WorkflowOptionButton
                    key={index}
                    option={option}
                    visual={visual}
                    showVisualOptions={showVisualOptions}
                    onOptionClick={onOptionClick}
                    onPreviewImage={onPreviewImage}
                    disabled={message.completed}
                  />
                );
              })}
            </div>
          )}

        {isAgent &&
          message.completed &&
          (message.data?.incident_id || message.incident_id) && (
            <div
              style={{
                display: "flex",
                gap: "8px",
                flexWrap: "wrap",
                marginTop: "12px",
              }}
            >
              <button
                onClick={() =>
                  onStartNewIncident && onStartNewIncident()
                }
                style={{
                  padding: "10px 14px",
                  backgroundColor: "#030304",
                  border: "1px solid #030304",
                  borderRadius: "11px",
                  fontSize: "13px",
                  fontWeight: "700",
                  color: "#ffffff",
                  cursor: "pointer",
                }}
              >
                Start New Incident
              </button>
              <button
                onClick={() =>
                  onOpenIncident &&
                  onOpenIncident(message.data?.incident_id || message.incident_id)
                }
                style={{
                  padding: "10px 14px",
                  backgroundColor: "#f8fbff",
                  border: "1px solid #d4e1ed",
                  borderRadius: "11px",
                  fontSize: "13px",
                  fontWeight: "700",
                  color: "#19314a",
                  cursor: "pointer",
                }}
              >
                Open {formatIncidentId(message.data?.incident_id || message.incident_id)}
              </button>
            </div>
          )}
      </div>
    </div>
  );
};

export default ChatMessage;
