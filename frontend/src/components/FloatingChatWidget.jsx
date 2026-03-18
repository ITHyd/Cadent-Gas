/**
 * FloatingChatWidget — reusable floating chat FAB + overlay panel.
 *
 * Extracted from ProfessionalDashboard. Contains all WebSocket chat logic,
 * voice/camera/video modes, workflow category selection, and message rendering.
 *
 * Used by ProfessionalDashboard. Props control cosmetic differences.
 */
import React, { useState, useRef, useEffect, forwardRef, useImperativeHandle } from "react";
import { useNavigate } from "react-router-dom";
import { connectWebSocket } from "../services/websocket";
import { getTenantWorkflows, transcribeAudio, lookupCustomerByPhone } from "../services/api";
import ChatMessage from "./ChatMessage";
import VideoRecorder from "./VideoRecorder";
import LiveVoiceChat from "./LiveVoiceChat";
import { formatUseCase } from "../utils/formatters";

const DEFAULT_GRADIENT = "#8DE971";

const formatUseCaseName = formatUseCase;
const REPORTER_TYPE_OPTIONS = [
  { label: "Occupier", value: "occupier" },
  { label: "GSRI", value: "gsri" },
  { label: "Landlord / HA", value: "landlord_ha" },
  { label: "Emergency Services", value: "emergency_services" },
  { label: "Remote Detector", value: "remote_detector" },
];
const HIDDEN_STARTER_USE_CASES = new Set([
  "co_alarm_fireangel",
  "co_alarm_firehawk",
  "co_alarm_aico",
  "co_alarm_kidde",
  "co_alarm_xsense",
  "co_alarm_honeywell",
  "co_alarm_google_nest",
  "co_alarm_netatmo",
  "co_alarm_cavius",
  "co_alarm_other",
]);

const isStarterWorkflow = (useCase) =>
  !!useCase && !HIDDEN_STARTER_USE_CASES.has(useCase);

const FloatingChatWidget = forwardRef(function FloatingChatWidget(
  {
    tenantId,
    userId,
    userDetails = {},
    userRole,
    primaryGradient = DEFAULT_GRADIENT,
    chatbotName = "AI Agent Assistant",
    onNoWorkflow,
  },
  ref
) {
  const navigate = useNavigate();

  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState("");
  const [isVideoRecording, setIsVideoRecording] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [incidentStarted, setIncidentStarted] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [voiceMode, setVoiceMode] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [availableWorkflows, setAvailableWorkflows] = useState([]);
  const [workflowStarted, setWorkflowStarted] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [showAllCategories, setShowAllCategories] = useState(false);
  const [cameraMode, setCameraMode] = useState(false);
  const [cameraPreview, setCameraPreview] = useState(null);
  const [isVoiceTranscribing, setIsVoiceTranscribing] = useState(false);
  const [selectedReporterType, setSelectedReporterType] = useState(null);
  const [isReporterSelectionPending, setIsReporterSelectionPending] = useState(false);

  // On-behalf-of-customer flow (company/call-center role)
  const isCallCenter = userRole === "company";
  const [phoneCollectionPhase, setPhoneCollectionPhase] = useState(false);
  const [customerDetails, setCustomerDetails] = useState(null);

  const messagesEndRef = useRef(null);
  const wsRef = useRef(null);
  const pendingFirstInputRef = useRef(null);
  const pendingVoiceMsgIdRef = useRef(null);
  const pendingImageMsgIdRef = useRef(null);
  const cameraFileInputRef = useRef(null);
  const cameraVideoRef = useRef(null);
  const cameraCanvasRef = useRef(null);
  const cameraStreamRef = useRef(null);

  // Expose open() so parent (hero button) can programmatically open the widget
  useImperativeHandle(ref, () => ({
    open: () => {
      setChatOpen(true);
      if (!incidentStarted) startIncident();
    },
  }));

  const getStyles = (gradient) => ({
    chatFab: {
      position: "fixed",
      bottom: "2rem",
      right: "2rem",
      width: "3.5rem",
      height: "3.5rem",
      borderRadius: "50%",
      background: gradient,
      color: "#030304",
      border: "none",
      cursor: "pointer",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: "1.2rem",
      boxShadow: "0 16px 24px -18px rgba(3, 3, 4, 0.8)",
      zIndex: 10001,
      transition: "all 0.3s ease",
    },
    chatOverlay: {
      position: "fixed",
      bottom: "5.5rem",
      right: "1rem",
      width: "min(440px, calc(100vw - 1.4rem))",
      height: "min(680px, calc(100vh - 6.5rem))",
      maxHeight: "calc(100vh - 6.5rem)",
      background: "rgba(251, 254, 255, 0.96)",
      backdropFilter: "blur(16px)",
      WebkitBackdropFilter: "blur(16px)",
      border: "1px solid #d1deea",
      borderRadius: "1.1rem",
      display: "flex",
      flexDirection: "column",
      boxShadow: "0 30px 45px -28px rgba(15, 31, 51, 0.8)",
      overflow: "hidden",
      zIndex: 10000,
      animation: "chatSlideUp 0.25s ease-out",
    },
    chatHeader: {
      padding: "1rem 1.2rem",
      borderBottom: "1px solid #d9e4ef",
      background: "#fff",
    },
    chatHeaderTop: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      marginBottom: "0.25rem",
    },
    chatTitle: {
      fontSize: "1rem",
      fontWeight: "700",
      color: "#102842",
      letterSpacing: "-0.02em",
      fontFamily: "Playfair Display, Times New Roman, serif",
    },
    chatHeaderRight: {
      display: "flex",
      alignItems: "center",
      gap: "0.5rem",
    },
    statusBadge: {
      display: "inline-flex",
      alignItems: "center",
      gap: "0.375rem",
      padding: "0.25rem 0.625rem",
      borderRadius: "9999px",
      fontSize: "0.6875rem",
      fontWeight: "600",
    },
    statusConnected: { backgroundColor: "#dcfce7", color: "#047857" },
    statusDisconnected: { backgroundColor: "#fee2e2", color: "#b91c1c" },
    statusDot: { width: "0.375rem", height: "0.375rem", borderRadius: "50%" },
    closeBtn: {
      width: "1.75rem",
      height: "1.75rem",
      borderRadius: "0.375rem",
      border: "1px solid #d3e0ec",
      backgroundColor: "#f6fbff",
      color: "#526981",
      cursor: "pointer",
      fontSize: "1rem",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      transition: "background 0.2s",
    },
    chatSubtitle: { color: "#5f738a", fontSize: "0.8rem" },
    messagesContainer: {
      flex: 1,
      overflowY: "auto",
      padding: "1rem",
      background: "#f5f9fd",
    },
    message: { marginBottom: "1rem", display: "flex", gap: "0.75rem" },
    messageAgent: { justifyContent: "flex-start" },
    avatar: {
      width: "2rem",
      height: "2rem",
      borderRadius: "0.5rem",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: "0.9rem",
      flexShrink: 0,
    },
    avatarAgent: { background: "#030304" },
    messageBubble: {
      maxWidth: "75%",
      padding: "0.75rem 1rem",
      borderRadius: "0.875rem",
      fontSize: "0.875rem",
      lineHeight: "1.5",
    },
    bubbleAgent: {
      backgroundColor: "white",
      border: "1px solid #e2e8f0",
      color: "#1e293b",
    },
    bubbleUser: { background: "#030304", color: "white" },
    typingIndicator: {
      display: "flex",
      gap: "0.375rem",
      padding: "0.75rem 1rem",
    },
    typingDot: {
      width: "0.4375rem",
      height: "0.4375rem",
      borderRadius: "50%",
      backgroundColor: "#cbd5e1",
      animation: "typing 1.4s infinite",
    },
    emptyState: {
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      height: "100%",
      textAlign: "center",
      padding: "2rem",
    },
    emptyIcon: {
      width: "4rem",
      height: "4rem",
      background: "#030304",
      borderRadius: "1rem",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: "2rem",
      marginBottom: "1rem",
    },
    emptyTitle: {
      fontSize: "1.05rem",
      fontWeight: "700",
      color: "#102842",
      marginBottom: "0.375rem",
    },
    emptyText: { color: "#5f738a", fontSize: "0.85rem" },
    inputContainer: {
      padding: "0.9rem 1rem",
      borderTop: "1px solid #d7e3ee",
      background: "white",
    },
    inputWrapper: {
      display: "flex",
      gap: "0.5rem",
      alignItems: "center",
      padding: "0.2rem 0.5rem",
      background: "#f4f9fd",
      borderRadius: "0.75rem",
      border: "1px solid #d3e0ec",
      transition: "all 0.2s",
    },
    textInput: {
      flex: 1,
      border: "none",
      backgroundColor: "transparent",
      fontSize: "0.9375rem",
      color: "#102842",
      outline: "none",
    },
    iconButton: {
      width: "2.5rem",
      height: "2.5rem",
      borderRadius: "0.75rem",
      border: "none",
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: "1rem",
      transition: "all 0.2s",
      backgroundColor: "transparent",
    },
    sendButton: { background: gradient, color: "#030304" },
    hint: {
      marginTop: "0.5rem",
      fontSize: "0.6875rem",
      color: "#7f93aa",
      textAlign: "center",
    },
  });

  const styles = getStyles(primaryGradient);

  // Fetch available workflows on mount
  useEffect(() => {
    const fetchWorkflows = async () => {
      try {
        const data = await getTenantWorkflows(tenantId);
        const workflows = Array.isArray(data)
          ? data.filter((wf) => isStarterWorkflow(wf.use_case))
          : [];
        const byUseCase = new Map();
        workflows.forEach((wf) => {
          const existing = byUseCase.get(wf.use_case);
          if (!existing || Number(wf.version) > Number(existing.version)) {
            byUseCase.set(wf.use_case, wf);
          }
        });
        setAvailableWorkflows(Array.from(byUseCase.values()));
      } catch {
        /* ignored */
      }
    };
    if (tenantId) fetchWorkflows();
  }, [tenantId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const addAgentMessage = (content, data = {}) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `msg_${Date.now()}`,
        role: "agent",
        content,
        timestamp: new Date().toISOString(),
        data,
      },
    ]);
  };

  const getReporterTypePrompt = () => {
    if (customerDetails) {
      return "Please choose the reporter type to continue this report.";
    }

    const firstName = userDetails?.name ? userDetails.name.split(" ")[0] : "";
    return firstName
      ? `Hi ${firstName}! Before we begin, please choose the reporter type.`
      : "Hello! Before we begin, please choose the reporter type.";
  };

  const promptForReporterType = ({ replace = false } = {}) => {
    setIsReporterSelectionPending(true);
    const reporterPromptMessage = {
      id: `msg_${Date.now()}`,
      role: "agent",
      content: getReporterTypePrompt(),
      timestamp: new Date().toISOString(),
      data: {
        reporterTypePrompt: true,
        options: REPORTER_TYPE_OPTIONS.map((option) => option.label),
      },
    };

    if (replace) {
      setMessages([reporterPromptMessage]);
      return;
    }

    setMessages((prev) => [...prev, reporterPromptMessage]);
  };

  const handleReporterTypeSelect = (reporterOption) => {
    const reporterType =
      typeof reporterOption === "string"
        ? REPORTER_TYPE_OPTIONS.find((option) => option.label === reporterOption)
        : reporterOption;

    if (!reporterType) return;

    setSelectedReporterType(reporterType);
    setIsReporterSelectionPending(false);
    if (isCallCenter) {
      setPhoneCollectionPhase(true);
      setMessages((prev) => [
        ...prev,
        {
          id: `msg_${Date.now()}`,
          role: "user",
          content: reporterType.label,
          timestamp: new Date().toISOString(),
        },
        {
          id: `msg_${Date.now()}_phone_prompt`,
          role: "agent",
          content: "Thanks. Please enter the customer's registered phone number to look up their details.",
          timestamp: new Date().toISOString(),
          data: { phonePrompt: true },
        },
      ]);
      return;
    }

    setMessages((prev) => [
      ...prev,
      {
        id: `msg_${Date.now()}`,
        role: "user",
        content: reporterType.label,
        timestamp: new Date().toISOString(),
      },
      {
        id: `msg_${Date.now()}_report_type`,
        role: "agent",
        content:
          "Thanks. Now choose the report type to get the right triage flow, or describe the issue in your own words.",
        timestamp: new Date().toISOString(),
        data: { reportTypePrompt: true },
      },
    ]);
  };

  const startIncident = () => {
    setChatOpen(true);
    const newSessionId = `session_${Date.now()}`;
    setSessionId(newSessionId);
    setIncidentStarted(true);
    setWorkflowStarted(false);
    setShowAllCategories(false);
    setSelectedReporterType(null);
    setIsReporterSelectionPending(false);
    setCustomerDetails(null);
    setPhoneCollectionPhase(false);

    const ws = connectWebSocket(newSessionId);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);

      if (isCallCenter) {
        promptForReporterType({ replace: true });
      } else {
        promptForReporterType({ replace: true });
      }
    };

    ws.onmessage = (event) => {
      const response = JSON.parse(event.data);
      handleAgentMessage(response);
    };

    ws.onerror = () => setIsConnected(false);
    ws.onclose = () => setIsConnected(false);
  };


  const handleAgentMessage = (response) => {
    if (response.type === "agent_message") {
      const newSid = response.session_id;
      if (newSid && newSid !== sessionId) {
        setSessionId(newSid);
      }

      if (pendingFirstInputRef.current && newSid) {
        const firstInput = pendingFirstInputRef.current;
        pendingFirstInputRef.current = null;
        setTimeout(() => {
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            const input =
              typeof firstInput === "string"
                ? { message: firstInput }
                : firstInput;
            wsRef.current.send(
              JSON.stringify({
                type: "user_input",
                session_id: newSid,
                input,
              })
            );
          }
        }, 100);
        return;
      }

      // Update voice placeholder
      if (pendingVoiceMsgIdRef.current) {
        const voiceId = pendingVoiceMsgIdRef.current;
        pendingVoiceMsgIdRef.current = null;
        setIsVoiceTranscribing(false);
        if (response.user_transcript) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === voiceId
                ? { ...m, content: `🎤 "${response.user_transcript}"`, isVoicePending: false }
                : m
            )
          );
        } else {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === voiceId
                ? { ...m, content: "🎤 Voice message", isVoicePending: false }
                : m
            )
          );
        }
      }

      // Update image placeholder
      if (pendingImageMsgIdRef.current) {
        const imageId = pendingImageMsgIdRef.current;
        pendingImageMsgIdRef.current = null;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === imageId ? { ...m, content: "", isImagePending: false } : m
          )
        );
      }

      // Handle no-workflow
      if (response.action === "no_workflow") {
        const noWorkflowMsg = {
          id: `msg_${Date.now()}`,
          role: "agent",
          content: response.message,
          timestamp: new Date().toISOString(),
          data: response.data || {},
          completed: true,
        };
        setMessages((prev) => [...prev, noWorkflowMsg]);
        setIsTyping(false);

        if (onNoWorkflow) {
          setTimeout(() => onNoWorkflow(response, messages), 2500);
        } else {
          setTimeout(() => {
            navigate("/report", {
              state: {
                manualReport: true,
                incidentId: response.data?.incident_id || "",
                classifiedUseCase: response.data?.classified_use_case || "",
                description:
                  messages.find((m) => m.role === "user")?.content || "",
              },
            });
          }, 2500);
        }
        return;
      }

      setIsTyping(true);
      setTimeout(() => {
        let messageContent = response.message;
        if (response.action === "question" && response.data?.question) {
          const question = response.data.question;
          if (messageContent.includes(question)) {
            messageContent = messageContent.replace(question, `**${question}**`);
          } else {
            messageContent = `**${question}**\n\n${messageContent}`;
          }
        }

        const agentMessage = {
          id: `msg_${Date.now()}`,
          role: "agent",
          content: messageContent,
          timestamp: new Date().toISOString(),
          data: response.data || {},
          completed: response.completed || false,
        };
        setMessages((prev) => [...prev, agentMessage]);
        setIsTyping(false);

        if (voiceMode && response.message) {
          playTextWithBrowserTTS(response.message);
        }
      }, 800);
    } else if (response.type === "error") {
      if (pendingVoiceMsgIdRef.current) {
        const voiceId = pendingVoiceMsgIdRef.current;
        pendingVoiceMsgIdRef.current = null;
        setIsVoiceTranscribing(false);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === voiceId
              ? { ...m, content: "🎤 Voice message", isVoicePending: false }
              : m
          )
        );
      }
      if (pendingImageMsgIdRef.current) {
        pendingImageMsgIdRef.current = null;
      }
      const errorMessage = {
        id: `msg_${Date.now()}`,
        role: "agent",
        content: "Something went wrong. Please try again.",
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      setIsTyping(false);
    }
  };

  const playTextWithBrowserTTS = (text) => {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      let voices = window.speechSynthesis.getVoices();

      const speakText = () => {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        utterance.volume = 1.0;

        voices = window.speechSynthesis.getVoices();
        const preferredVoice = voices.find(
          (v) =>
            v.name.includes("Google") ||
            v.name.includes("Female") ||
            v.name.includes("Samantha") ||
            v.name.includes("Microsoft")
        );
        if (preferredVoice) utterance.voice = preferredVoice;
        else if (voices.length > 0) utterance.voice = voices[0];

        utterance.onstart = () => setIsSpeaking(true);
        utterance.onend = () => setIsSpeaking(false);
        utterance.onerror = () => setIsSpeaking(false);

        window.speechSynthesis.speak(utterance);
      };

      if (voices.length === 0) {
        window.speechSynthesis.onvoiceschanged = () => speakText();
      } else {
        speakText();
      }
    }
  };

  const stopTTS = () => {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }
  };

  // Resolve the effective user ID: customer's ID when on-behalf, else logged-in user
  const effectiveUserId = customerDetails ? customerDetails.user_id : userId;
  const effectiveUserDetails = customerDetails
    ? { name: customerDetails.full_name, phone: customerDetails.phone, address: customerDetails.address }
    : { name: userDetails.name || null, phone: userDetails.phone || null, address: userDetails.address || null };

  const buildInitialDataFull = (extra = {}) => ({
    ...extra,
    user_details: effectiveUserDetails,
    ...(selectedReporterType
      ? {
          reporter_type: selectedReporterType.value,
          reporter_type_label: selectedReporterType.label,
        }
      : {}),
    ...(customerDetails ? { reported_by_staff_id: userId, on_behalf: true } : {}),
  });

  const handleCategorySelect = (useCase, displayName) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    setMessages((prev) => [
      ...prev,
      {
        id: `msg_${Date.now()}`,
        role: "user",
        content: displayName,
        timestamp: new Date().toISOString(),
      },
    ]);
    setWorkflowStarted(true);
    pendingFirstInputRef.current = displayName;

    wsRef.current.send(
      JSON.stringify({
        type: "start",
        incident_id: `incident_${Date.now()}`,
        tenant_id: tenantId,
        user_id: effectiveUserId,
        use_case: useCase,
        initial_data: buildInitialDataFull({ use_case: useCase }),
      })
    );
  };

  const handleIncidentOptionClick = (option) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `msg_${Date.now()}`,
        role: "user",
        content: option,
        timestamp: new Date().toISOString(),
      },
    ]);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          type: "user_input",
          session_id: sessionId,
          input: { message: option },
        })
      );
    }
  };

  const sendMessage = () => {
    if (!inputText.trim() || !wsRef.current) return;

    const text = inputText.trim();

    // If in phone collection phase, route to phone lookup instead
    if (phoneCollectionPhase) {
      setInputText("");
      // Normalize phone: strip spaces/dashes, add +44 if needed
      let phone = text.replace(/[\s\-()]/g, "");
      if (/^\d{10}$/.test(phone)) phone = "+44" + phone;          // 7700900101 → +447700900101
      else if (/^0\d{10}$/.test(phone)) phone = "+44" + phone.slice(1); // 07700900101 → +447700900101
      else if (/^44\d{10}$/.test(phone)) phone = "+" + phone;     // 447700900101 → +447700900101
      else if (!phone.startsWith("+")) phone = "+" + phone;        // catch-all
      setMessages((prev) => [
        ...prev,
        { id: `msg_${Date.now()}`, role: "user", content: phone, timestamp: new Date().toISOString() },
      ]);
      setIsTyping(true);
      lookupCustomerByPhone(phone).then((customer) => {
        setCustomerDetails(customer);
        setPhoneCollectionPhase(false);
        setTimeout(() => {
          setMessages((prev) => [
            ...prev,
            {
              id: `msg_${Date.now()}`,
              role: "agent",
              content: `**Customer Details**\n**Name:** ${customer.full_name}\n**Phone:** ${customer.phone}${customer.address ? `\n**Address:** ${customer.address}` : ""}`,
              timestamp: new Date().toISOString(),
              data: { customerBanner: true, customer },
            },
          ]);
          setIsTyping(false);
          addAgentMessage(
            "Thanks. Now choose the report type to get the right triage flow, or describe the issue in your own words.",
            { reportTypePrompt: true }
          );
        }, 600);
      }).catch(() => {
        setTimeout(() => {
          setMessages((prev) => [
            ...prev,
            {
              id: `msg_${Date.now()}`,
              role: "agent",
              content: `Could not find a customer with that phone number. Please check and try again.`,
              timestamp: new Date().toISOString(),
              data: { phonePrompt: true },
            },
          ]);
          setIsTyping(false);
        }, 600);
      });
      return;
    }

    if (isReporterSelectionPending) {
      setInputText("");
      const matchedReporterType = REPORTER_TYPE_OPTIONS.find(
        (option) => option.label.toLowerCase() === text.toLowerCase()
      );

      if (matchedReporterType) {
        handleReporterTypeSelect(matchedReporterType);
      } else {
        addAgentMessage("Please choose one of the reporter types shown above to continue.", {
          reporterTypePrompt: true,
          options: REPORTER_TYPE_OPTIONS.map((option) => option.label),
        });
      }
      return;
    }

    setMessages((prev) => [
      ...prev,
      {
        id: `msg_${Date.now()}`,
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
      },
    ]);
    setInputText("");

    if (!workflowStarted) {
      setWorkflowStarted(true);
      pendingFirstInputRef.current = text;
      wsRef.current.send(
        JSON.stringify({
          type: "start",
          incident_id: `incident_${Date.now()}`,
          tenant_id: tenantId,
          user_id: effectiveUserId,
          use_case: "",
          initial_data: buildInitialDataFull(),
        })
      );
    } else {
      wsRef.current.send(
        JSON.stringify({
          type: "user_input",
          session_id: sessionId,
          input: { message: text },
        })
      );
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleVideoRecorded = async (videoBlob) => {
    setIsProcessing(true);
    setMessages((prev) => [
      ...prev,
      {
        id: `msg_${Date.now()}`,
        role: "user",
        content: "🎥 Video message (transcribing...)",
        timestamp: new Date().toISOString(),
      },
    ]);

    try {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64Video = reader.result.split(",")[1];
        const videoPayload = { video: base64Video, format: "webm", type: "video" };

        if (!workflowStarted) {
          setWorkflowStarted(true);
          pendingFirstInputRef.current = videoPayload;
          wsRef.current.send(
            JSON.stringify({
              type: "start",
              incident_id: `incident_${Date.now()}`,
              tenant_id: tenantId,
              user_id: effectiveUserId,
              use_case: "",
              initial_data: buildInitialDataFull(),
            })
          );
        } else if (wsRef.current) {
          wsRef.current.send(
            JSON.stringify({
              type: "user_input",
              session_id: sessionId,
              input: videoPayload,
            })
          );
        }
        setIsProcessing(false);
      };
      reader.readAsDataURL(videoBlob);
    } catch {
      setIsProcessing(false);
    }
  };

  const handleImageCapture = async (base64Image, format) => {
    setIsProcessing(true);
    const msgId = `img_${Date.now()}`;
    const imageDataUrl = `data:image/${format};base64,${base64Image}`;
    setMessages((prev) => [
      ...prev,
      {
        id: msgId,
        role: "user",
        content: "📷 Image (analyzing...)",
        timestamp: new Date().toISOString(),
        isImagePending: true,
        imageUrl: imageDataUrl,
      },
    ]);
    pendingImageMsgIdRef.current = msgId;

    try {
      const imagePayload = { image: base64Image, format, type: "image" };

      if (!workflowStarted) {
        setWorkflowStarted(true);
        pendingFirstInputRef.current = imagePayload;
        wsRef.current.send(
          JSON.stringify({
            type: "start",
            incident_id: `incident_${Date.now()}`,
            tenant_id: tenantId,
            user_id: effectiveUserId,
            use_case: "",
            initial_data: buildInitialDataFull(),
          })
        );
      } else if (wsRef.current) {
        wsRef.current.send(
          JSON.stringify({
            type: "user_input",
            session_id: sessionId,
            input: imagePayload,
          })
        );
      }
      setIsProcessing(false);
    } catch {
      setIsProcessing(false);
    }
  };

  const toggleVoiceMode = () => {
    if (!sessionId) {
      alert("Please start an incident report first");
      return;
    }
    setCameraMode(false);
    setVoiceMode(!voiceMode);
  };

  const openCameraMode = () => {
    setVoiceMode(false);
    setCameraMode(true);
    setCameraPreview(null);
  };

  const closeCameraMode = () => {
    setCameraMode(false);
    setCameraPreview(null);
    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
    }
  };

  const handleCameraFileSelect = () => cameraFileInputRef.current?.click();

  const handleCameraFileChange = (event) => {
    const file = event.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => setCameraPreview(reader.result);
      reader.readAsDataURL(file);
    }
  };

  const startCameraStream = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      cameraStreamRef.current = stream;
      if (cameraVideoRef.current) {
        cameraVideoRef.current.srcObject = stream;
      }
    } catch {
      alert("Could not access camera. Please upload a file instead.");
    }
  };

  const capturePhoto = () => {
    if (cameraVideoRef.current && cameraCanvasRef.current) {
      const video = cameraVideoRef.current;
      const canvas = cameraCanvasRef.current;
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d").drawImage(video, 0, 0);
      setCameraPreview(canvas.toDataURL("image/jpeg"));
      if (cameraStreamRef.current) {
        cameraStreamRef.current.getTracks().forEach((track) => track.stop());
        cameraStreamRef.current = null;
      }
    }
  };

  const sendCameraImage = () => {
    if (cameraPreview) {
      const base64Data = cameraPreview.split(",")[1];
      handleImageCapture(base64Data, "jpeg");
      closeCameraMode();
    }
  };

  const handleVoiceTranscript = async (audioData) => {
    // Transcribe the audio and place the text in the input box for editing
    setIsVoiceTranscribing(true);
    setVoiceMode(false); // Switch back to text mode so user can see the input

    try {
      // Convert base64 audio to Blob for the transcribe API
      const byteChars = atob(audioData.audio);
      const byteArray = new Uint8Array(byteChars.length);
      for (let i = 0; i < byteChars.length; i++) {
        byteArray[i] = byteChars.charCodeAt(i);
      }
      const audioBlob = new Blob([byteArray], { type: "audio/webm" });

      const result = await transcribeAudio(audioBlob);
      const transcribedText = result?.text?.trim();

      if (transcribedText) {
        setInputText(transcribedText);
      }
    } catch (err) {
      // Silently fail — user can still type manually
    } finally {
      setIsVoiceTranscribing(false);
    }
  };

  /* ── Render ─────────────────────────────────────────────────── */

  return (
    <>
      <style>{`
        @keyframes typing {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-10px); }
        }
        .typing-dot-1 { animation-delay: 0s; }
        .typing-dot-2 { animation-delay: 0.2s; }
        .typing-dot-3 { animation-delay: 0.4s; }
        @keyframes chatSlideUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      {/* FAB */}
      {!chatOpen && (
        <button
          style={styles.chatFab}
          onClick={() => {
            setChatOpen(true);
            if (!incidentStarted) startIncident();
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = "scale(1.1)";
            e.currentTarget.style.boxShadow =
              "0 22px 30px -22px rgba(3, 3, 4, 0.95)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "scale(1)";
            e.currentTarget.style.boxShadow =
              "0 16px 24px -18px rgba(3, 3, 4, 0.8)";
          }}
        >
          💬
        </button>
      )}

      {/* Chat overlay panel */}
      {chatOpen && (
        <div style={styles.chatOverlay}>
          {/* Header */}
          <div style={styles.chatHeader}>
            <div style={styles.chatHeaderTop}>
              <h2 style={styles.chatTitle}>{chatbotName}</h2>
              <div style={styles.chatHeaderRight}>
                <div
                  style={{
                    ...styles.statusBadge,
                    ...(isConnected
                      ? styles.statusConnected
                      : styles.statusDisconnected),
                  }}
                >
                  <span
                    style={{
                      ...styles.statusDot,
                      backgroundColor: isConnected ? "#16a34a" : "#dc2626",
                    }}
                  />
                  {isConnected ? "Connected" : "Disconnected"}
                </div>
                <button
                  style={styles.closeBtn}
                  onClick={() => setChatOpen(false)}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = "#e2e8f0";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = "#f1f5f9";
                  }}
                >
                  ✕
                </button>
              </div>
            </div>
            <p style={styles.chatSubtitle}>
              {incidentStarted
                ? isCallCenter
                  ? customerDetails
                    ? selectedReporterType
                      ? `Customer: ${customerDetails.full_name} · Reporter: ${selectedReporterType.label}`
                      : `Customer: ${customerDetails.full_name}`
                    : "Enter customer phone to begin"
                  : selectedReporterType
                    ? `Reporter: ${selectedReporterType.label}`
                    : "Select reporter type to begin"
                : "Ready to assist you"}
            </p>
          </div>

          {/* Messages */}
          <div
            style={{
              ...styles.messagesContainer,
              ...(voiceMode || cameraMode
                ? { filter: "blur(4px)", pointerEvents: "none" }
                : {}),
            }}
          >
            {messages.length === 0 ? (
              <div style={styles.emptyState}>
                <div style={styles.emptyIcon}>💬</div>
                <h3 style={styles.emptyTitle}>
                  {incidentStarted ? "Connecting..." : "Start a Conversation"}
                </h3>
                <p style={styles.emptyText}>
                  {incidentStarted
                    ? "Setting up your secure connection"
                    : 'Click "Start Incident Report" to begin'}
                </p>
              </div>
            ) : (
              <>
                {messages.map((message, index) => (
                  <React.Fragment key={message.id}>
                    <ChatMessage
                      message={message}
                      onOptionClick={
                        message.data?.reporterTypePrompt
                          ? handleReporterTypeSelect
                          : handleIncidentOptionClick
                      }
                    />
                    {message.data?.reportTypePrompt &&
                      message.role === "agent" &&
                      !isReporterSelectionPending &&
                      !!selectedReporterType &&
                      !workflowStarted &&
                      !phoneCollectionPhase && (
                        <div style={{ marginTop: "0.5rem", maxWidth: "90%" }}>
                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: "repeat(2, 1fr)",
                              gap: "0.5rem",
                            }}
                          >
                            {(showAllCategories
                              ? availableWorkflows
                              : availableWorkflows.slice(0, 6)
                            ).map((wf) => (
                              <button
                                key={wf.use_case}
                                onClick={() =>
                                  handleCategorySelect(
                                    wf.use_case,
                                    formatUseCaseName(wf.use_case)
                                  )
                                }
                                style={{
                                  padding: "0.5rem 0.75rem",
                                  backgroundColor: "white",
                                  border: "1.5px solid #e2e8f0",
                                  borderRadius: "0.625rem",
                                  fontSize: "0.8rem",
                                  fontWeight: "500",
                                  color: "#374151",
                                  cursor: "pointer",
                                  transition: "all 0.2s ease",
                                  textAlign: "center",
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.borderColor = "#76a0c4";
                                  e.currentTarget.style.backgroundColor = "#edf5fc";
                                  e.currentTarget.style.transform = "translateY(-1px)";
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.borderColor = "#e2e8f0";
                                  e.currentTarget.style.backgroundColor = "white";
                                  e.currentTarget.style.transform = "translateY(0)";
                                }}
                              >
                                {formatUseCaseName(wf.use_case)}
                              </button>
                            ))}
                          </div>
                          {availableWorkflows.length > 6 && (
                            <div
                              style={{
                                display: "flex",
                                justifyContent: "flex-end",
                                marginTop: "0.375rem",
                              }}
                            >
                              <button
                                onClick={() => setShowAllCategories(!showAllCategories)}
                                style={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: "0.25rem",
                                  padding: "0.25rem 0.625rem",
                                  backgroundColor: "transparent",
                                  border: "none",
                                  fontSize: "0.7rem",
                                  color: "#64748b",
                                  cursor: "pointer",
                                  transition: "all 0.2s",
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.color = "#030304";
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.color = "#64748b";
                                }}
                              >
                                {showAllCategories ? "Show less ▲" : "Show more ▼"}
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                  </React.Fragment>
                ))}
                {isTyping && (
                  <div style={{ ...styles.message, ...styles.messageAgent }}>
                    <div style={{ ...styles.avatar, ...styles.avatarAgent }}>
                      🤖
                    </div>
                    <div
                      style={{
                        ...styles.messageBubble,
                        ...styles.bubbleAgent,
                        ...styles.typingIndicator,
                      }}
                    >
                      <div style={styles.typingDot} className="typing-dot-1" />
                      <div style={styles.typingDot} className="typing-dot-2" />
                      <div style={styles.typingDot} className="typing-dot-3" />
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Input area */}
          {incidentStarted && (
            <div style={styles.inputContainer}>
              {voiceMode ? (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                  }}
                >
                  <LiveVoiceChat
                    sessionId={sessionId}
                    onTranscript={handleVoiceTranscript}
                    onAudioResponse={() => {}}
                    isConnected={isConnected}
                    onStop={() => setVoiceMode(false)}
                  />
                  <div
                    style={{
                      display: "flex",
                      gap: "0.5rem",
                      padding: "0 1rem 0.75rem",
                      width: "100%",
                      justifyContent: "center",
                    }}
                  >
                    {isSpeaking && (
                      <button
                        style={{
                          padding: "0.4rem 1rem",
                          background: "#fee2e2",
                          color: "#dc2626",
                          border: "1px solid #fecaca",
                          borderRadius: "0.5rem",
                          cursor: "pointer",
                          fontSize: "0.75rem",
                          fontWeight: "600",
                          transition: "all 0.2s",
                        }}
                        onClick={stopTTS}
                      >
                        Stop Speaking
                      </button>
                    )}
                    <button
                      style={{
                        padding: "0.4rem 1rem",
                        background: "#f1f5f9",
                        color: "#475569",
                        border: "1px solid #e2e8f0",
                        borderRadius: "0.5rem",
                        cursor: "pointer",
                        fontSize: "0.75rem",
                        fontWeight: "600",
                        transition: "all 0.2s",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.35rem",
                      }}
                      onClick={toggleVoiceMode}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = "#e2e8f0";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = "#f1f5f9";
                      }}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: "0.85rem", height: "0.85rem" }}>
                        <line x1="17" y1="10" x2="3" y2="10" />
                        <line x1="21" y1="6" x2="3" y2="6" />
                        <line x1="21" y1="14" x2="3" y2="14" />
                        <line x1="17" y1="18" x2="3" y2="18" />
                      </svg>
                      Switch to Text
                    </button>
                  </div>
                </div>
              ) : cameraMode ? (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    padding: "1.5rem 1rem",
                    gap: "1rem",
                  }}
                >
                  <input ref={cameraFileInputRef} type="file" accept="image/*" style={{ display: "none" }} onChange={handleCameraFileChange} />
                  <canvas ref={cameraCanvasRef} style={{ display: "none" }} />

                  {!cameraPreview && !cameraStreamRef.current?.active && (
                    <>
                      <div style={{ fontSize: "0.8125rem", fontWeight: "600", color: "#475569", textAlign: "center" }}>
                        Upload Image
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", width: "100%", maxWidth: "280px" }}>
                        <button
                          style={{ padding: "1.25rem 0.75rem", borderRadius: "0.75rem", border: "1.5px solid #e2e8f0", backgroundColor: "white", cursor: "pointer", transition: "all 0.2s", display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem" }}
                          onClick={handleCameraFileSelect}
                          onMouseEnter={(e) => { e.currentTarget.style.borderColor = "#030304"; e.currentTarget.style.backgroundColor = "#edf5fc"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#e2e8f0"; e.currentTarget.style.backgroundColor = "white"; }}
                        >
                          <div style={{ width: "2.5rem", height: "2.5rem", borderRadius: "0.75rem", background: primaryGradient, display: "flex", alignItems: "center", justifyContent: "center" }}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: "1.25rem", height: "1.25rem" }}>
                              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                            </svg>
                          </div>
                          <span style={{ fontSize: "0.75rem", fontWeight: "600", color: "#0f172a" }}>Choose File</span>
                        </button>
                        <button
                          style={{ padding: "1.25rem 0.75rem", borderRadius: "0.75rem", border: "1.5px solid #e2e8f0", backgroundColor: "white", cursor: "pointer", transition: "all 0.2s", display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem" }}
                          onClick={startCameraStream}
                          onMouseEnter={(e) => { e.currentTarget.style.borderColor = "#030304"; e.currentTarget.style.backgroundColor = "#edf5fc"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#e2e8f0"; e.currentTarget.style.backgroundColor = "white"; }}
                        >
                          <div style={{ width: "2.5rem", height: "2.5rem", borderRadius: "0.75rem", background: primaryGradient, display: "flex", alignItems: "center", justifyContent: "center" }}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: "1.25rem", height: "1.25rem" }}>
                              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                              <circle cx="12" cy="13" r="4" />
                            </svg>
                          </div>
                          <span style={{ fontSize: "0.75rem", fontWeight: "600", color: "#0f172a" }}>Take Photo</span>
                        </button>
                      </div>
                    </>
                  )}

                  {cameraStreamRef.current?.active && !cameraPreview && (
                    <>
                      <video ref={cameraVideoRef} autoPlay playsInline style={{ width: "100%", maxWidth: "300px", borderRadius: "0.75rem" }} />
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        <button style={{ padding: "0.5rem 1rem", borderRadius: "0.5rem", border: "none", fontSize: "0.75rem", fontWeight: "600", cursor: "pointer", background: primaryGradient, color: "white" }} onClick={capturePhoto}>Capture</button>
                        <button style={{ padding: "0.5rem 1rem", borderRadius: "0.5rem", border: "none", fontSize: "0.75rem", fontWeight: "600", cursor: "pointer", backgroundColor: "#f1f5f9", color: "#64748b" }} onClick={closeCameraMode}>Cancel</button>
                      </div>
                    </>
                  )}

                  {cameraPreview && (
                    <>
                      <img src={cameraPreview} alt="Preview" style={{ width: "100%", maxWidth: "300px", borderRadius: "0.75rem" }} />
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        <button style={{ padding: "0.5rem 1rem", borderRadius: "0.5rem", border: "none", fontSize: "0.75rem", fontWeight: "600", cursor: "pointer", background: primaryGradient, color: "white" }} onClick={sendCameraImage}>Send Image</button>
                        <button style={{ padding: "0.5rem 1rem", borderRadius: "0.5rem", border: "none", fontSize: "0.75rem", fontWeight: "600", cursor: "pointer", backgroundColor: "#f1f5f9", color: "#64748b" }} onClick={() => setCameraPreview(null)}>Retake</button>
                        <button style={{ padding: "0.5rem 1rem", borderRadius: "0.5rem", border: "none", fontSize: "0.75rem", fontWeight: "600", cursor: "pointer", backgroundColor: "#f1f5f9", color: "#64748b" }} onClick={closeCameraMode}>Cancel</button>
                      </div>
                    </>
                  )}

                  <button
                    style={{ padding: "0.4rem 1rem", background: "#f1f5f9", color: "#475569", border: "1px solid #e2e8f0", borderRadius: "0.5rem", cursor: "pointer", fontSize: "0.75rem", fontWeight: "600", transition: "all 0.2s", display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
                    onClick={closeCameraMode}
                    onMouseEnter={(e) => { e.currentTarget.style.background = "#e2e8f0"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = "#f1f5f9"; }}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: "0.85rem", height: "0.85rem" }}>
                      <line x1="17" y1="10" x2="3" y2="10" />
                      <line x1="21" y1="6" x2="3" y2="6" />
                      <line x1="21" y1="14" x2="3" y2="14" />
                      <line x1="17" y1="18" x2="3" y2="18" />
                    </svg>
                    Switch to Text
                  </button>
                </div>
              ) : (
                <>
                  <div style={styles.inputWrapper}>
                    <input
                      type="text"
                      style={styles.textInput}
                      value={inputText}
                      onChange={(e) => setInputText(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder={
                        isVoiceTranscribing
                          ? "Transcribing voice..."
                          : phoneCollectionPhase
                            ? "Enter customer phone number..."
                            : isReporterSelectionPending
                              ? "Choose a reporter type..."
                              : "Type your message..."
                      }
                      disabled={!isConnected || isProcessing || isVoiceTranscribing}
                    />

                    <button
                      type="button"
                      onClick={toggleVoiceMode}
                      disabled={!isConnected || isProcessing || isVoiceTranscribing}
                      title="Voice mode"
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: "2.5rem",
                        height: "2.5rem",
                        borderRadius: "0.75rem",
                        border: "1px solid #cbd5e1",
                        backgroundColor: "white",
                        color: "#475569",
                        cursor: !isConnected || isProcessing || isVoiceTranscribing ? "not-allowed" : "pointer",
                        opacity: !isConnected || isProcessing || isVoiceTranscribing ? 0.5 : 1,
                        transition: "all 0.2s",
                      }}
                      onMouseEnter={(e) => {
                        if (!e.currentTarget.disabled) {
                          e.currentTarget.style.borderColor = "#030304";
                          e.currentTarget.style.color = "#030304";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!e.currentTarget.disabled) {
                          e.currentTarget.style.borderColor = "#cbd5e1";
                          e.currentTarget.style.color = "#475569";
                        }
                      }}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" style={{ width: "1.25rem", height: "1.25rem" }} aria-hidden="true">
                        <path d="M12 15a3 3 0 0 0 3-3V7a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3Z" />
                        <path d="M5 11v1a7 7 0 0 0 14 0v-1" />
                        <path d="M12 19v3" />
                      </svg>
                    </button>

                    <VideoRecorder
                      onRecordingComplete={handleVideoRecorded}
                      isRecording={isVideoRecording}
                      setIsRecording={setIsVideoRecording}
                      disabled={!isConnected || isProcessing || isVoiceTranscribing}
                    />

                    <button
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: "2.5rem",
                        height: "2.5rem",
                        borderRadius: "0.75rem",
                        border: "1px solid #cbd5e1",
                        backgroundColor: "white",
                        color: "#475569",
                        cursor: !isConnected || isProcessing ? "not-allowed" : "pointer",
                        opacity: !isConnected || isProcessing ? 0.5 : 1,
                        transition: "all 0.2s",
                      }}
                      onClick={openCameraMode}
                      disabled={!isConnected || isProcessing || isVoiceTranscribing}
                      title="Upload image"
                      onMouseEnter={(e) => {
                        if (!e.currentTarget.disabled) {
                          e.currentTarget.style.borderColor = "#030304";
                          e.currentTarget.style.color = "#030304";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!e.currentTarget.disabled) {
                          e.currentTarget.style.borderColor = "#cbd5e1";
                          e.currentTarget.style.color = "#475569";
                        }
                      }}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" style={{ width: "1.25rem", height: "1.25rem" }} aria-hidden="true">
                        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                        <circle cx="12" cy="13" r="4" />
                      </svg>
                    </button>

                    <button
                      style={{ ...styles.iconButton, ...styles.sendButton }}
                      onClick={sendMessage}
                      disabled={!isConnected || !inputText.trim() || isProcessing}
                      onMouseEnter={(e) => {
                        if (!e.target.disabled) e.target.style.transform = "scale(1.05)";
                      }}
                      onMouseLeave={(e) => {
                        e.target.style.transform = "scale(1)";
                      }}
                    >
                      ➤
                    </button>
                  </div>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginTop: "0.5rem",
                    }}
                  >
                    <p style={styles.hint}>
                      {isProcessing
                        ? "Processing..."
                        : isReporterSelectionPending
                          ? "Choose a reporter type to continue"
                          : "Enter to send"}
                    </p>
                    <button
                      style={{
                        padding: "0.375rem 0.75rem",
                        background: primaryGradient,
                        color: "white",
                        border: "none",
                        borderRadius: "0.375rem",
                        cursor: "pointer",
                        fontSize: "0.75rem",
                        fontWeight: "600",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.375rem",
                      }}
                      onClick={toggleVoiceMode}
                      disabled={!isConnected}
                    >
                      Voice Mode
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
});

export default FloatingChatWidget;
