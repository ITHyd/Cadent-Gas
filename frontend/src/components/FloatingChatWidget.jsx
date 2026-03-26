/**
 * FloatingChatWidget — reusable floating chat FAB + overlay panel.
 *
 * Extracted from ProfessionalDashboard. Contains all WebSocket chat logic,
 * workflow category selection, and message rendering.
 *
 * Used by ProfessionalDashboard. Props control cosmetic differences.
 */
import React, {
  useState,
  useRef,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from "react";
import { useNavigate } from "react-router-dom";
import { connectWebSocket } from "../services/websocket";
import { getTenantWorkflows, lookupCustomerByPhone } from "../services/api";
import {
  normalizeDemoReferenceId,
} from "../constants/referenceIds";
import ChatMessage from "./ChatMessage";
import { formatUseCase } from "../utils/formatters";

const DEFAULT_GRADIENT = "#8DE971";

const formatUseCaseName = formatUseCase;
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
    chatbotName = "Agent Assistant",
    onNoWorkflow,
  },
  ref,
) {
  const navigate = useNavigate();

  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [incidentStarted, setIncidentStarted] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [isProcessing] = useState(false);
  const [availableWorkflows, setAvailableWorkflows] = useState([]);
  const [workflowStarted, setWorkflowStarted] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [showAllCategories, setShowAllCategories] = useState(false);
  const [selectedReferenceId, setSelectedReferenceId] = useState(null);
  const [isReferenceIdPending, setIsReferenceIdPending] = useState(false);

  // On-behalf-of-customer flow (company/call-center role)
  const isCallCenter = userRole === "company";
  const [phoneCollectionPhase, setPhoneCollectionPhase] = useState(false);
  const [customerDetails, setCustomerDetails] = useState(null);

  const messagesEndRef = useRef(null);
  const wsRef = useRef(null);
  const pendingFirstInputRef = useRef(null);
  const referenceValidationPendingRef = useRef(false);
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const manualCloseRef = useRef(false);
  const incidentIdRef = useRef("");
  const activeUseCaseRef = useRef("");
  const hasStartedWorkflowRef = useRef(false);
  const completedRef = useRef(false);

  // Expose open() so parent (hero button) can programmatically open the widget
  useImperativeHandle(ref, () => ({
    open: () => {
      setChatOpen(true);
      if (!incidentStarted) {
        startIncident();
      } else if (!wsRef.current || wsRef.current.readyState > WebSocket.OPEN) {
        startIncident({ reconnect: true });
      }
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

  useEffect(() => () => {
    manualCloseRef.current = true;
    clearTimeout(reconnectTimerRef.current);
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) {
      wsRef.current.close();
    }
  }, []);

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

  const promptForReportType = () => {
    addAgentMessage(
      "Thanks. Now choose the report type to get the right triage flow, or describe the issue in your own words.",
      { reportTypePrompt: true },
    );
  };

  const promptForCustomerPhone = () => {
    setPhoneCollectionPhase(true);
    addAgentMessage(
      "Please enter the customer's registered phone number to look up their details.",
      { phonePrompt: true },
    );
  };

  const promptForReferenceId = ({ replace = false } = {}) => {
    setIsReferenceIdPending(true);
    const refPromptMessage = {
      id: `msg_${Date.now()}_ref_prompt`,
      role: "agent",
      content: "Please enter the REF ID before we begin.",
      timestamp: new Date().toISOString(),
      data: {
        refIdPrompt: true,
      },
    };

    if (replace) {
      setMessages([refPromptMessage]);
      return;
    }

    setMessages((prev) => [...prev, refPromptMessage]);
  };

  const handleReferenceIdSelect = (
    referenceOption,
    { appendUserMessage = true, displayValue } = {},
  ) => {
    const normalizedReferenceId =
      normalizeDemoReferenceId(
        typeof referenceOption === "string"
          ? referenceOption
          : referenceOption?.label,
      ) || normalizeDemoReferenceId(referenceOption);

    if (!normalizedReferenceId) {
      addAgentMessage(
        "Please enter a valid REF ID to continue.",
        {
          refIdPrompt: true,
        },
      );
      return;
    }

    setSelectedReferenceId(normalizedReferenceId);
    setIsReferenceIdPending(false);
    if (appendUserMessage) {
      setMessages((prev) => [
        ...prev,
        {
          id: `msg_${Date.now()}`,
          role: "user",
          content: displayValue || normalizedReferenceId,
          timestamp: new Date().toISOString(),
        },
      ]);
    }
    setPhoneCollectionPhase(false);

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      referenceValidationPendingRef.current = true;
      activeUseCaseRef.current = "";
      sendStartOrResume(wsRef.current, {
        useCase: "",
        extraInitialData: { reference_id: normalizedReferenceId },
      });
      return;
    }

    if (isCallCenter) {
      promptForCustomerPhone();
      return;
    }
    promptForReportType();
  };

  const startIncident = async ({ reconnect = false } = {}) => {
    setChatOpen(true);
    manualCloseRef.current = false;
    const newSessionId = `session_${Date.now()}`;
    setSessionId(newSessionId);
    if (!reconnect) {
      incidentIdRef.current = `incident_${Date.now()}`;
      activeUseCaseRef.current = "";
      hasStartedWorkflowRef.current = false;
      completedRef.current = false;
      setIncidentStarted(true);
      setWorkflowStarted(false);
      setShowAllCategories(false);
      setSelectedReferenceId(null);
      setIsReferenceIdPending(false);
      setCustomerDetails(null);
      setPhoneCollectionPhase(false);
      referenceValidationPendingRef.current = false;
    }

    try {
      const ws = await connectWebSocket(newSessionId);
      attachSocketHandlers(ws, { reconnect });
    } catch (error) {
      setIsConnected(false);
      if (reconnect) {
        scheduleReconnect();
        return;
      }
      setMessages([
        {
          id: `msg_${Date.now()}`,
          role: "agent",
          content: error.message || "Your session expired. Please sign in again.",
          timestamp: new Date().toISOString(),
        },
      ]);
    }
  };

  const handleAgentMessage = (response) => {
    if (response.type === "typing") {
      setIsTyping(Boolean(response.typing));
      return;
    }

    if (response.type === "agent_message") {
      const newSid = response.session_id;
      if (newSid && newSid !== sessionId) {
        setSessionId(newSid);
      }

      if (response.action === "reference_id_prompt") {
        setIsReferenceIdPending(true);
        setSelectedReferenceId(null);
      } else if (
        response.action === "awaiting_incident_report" ||
        response.action === "reference_id_exists" ||
        response.action === "open_existing_incident"
      ) {
        setIsReferenceIdPending(false);
      }

      if (
        referenceValidationPendingRef.current &&
        response.action === "awaiting_incident_report"
      ) {
        referenceValidationPendingRef.current = false;
        setIsTyping(false);
        if (isCallCenter && !customerDetails) {
          promptForCustomerPhone();
        } else {
          promptForReportType();
        }
        return;
      }

      if (response.action === "reference_id_exists") {
        referenceValidationPendingRef.current = false;
        setPhoneCollectionPhase(false);
      }

      if (response.action === "reference_id_prompt") {
        referenceValidationPendingRef.current = false;
      }

      if (
        pendingFirstInputRef.current &&
        newSid &&
        response.action === "awaiting_incident_report"
      ) {
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
              }),
            );
          }
        }, 100);
        return;
      }

      if (response.action === "open_existing_incident") {
        completedRef.current = true;
        referenceValidationPendingRef.current = false;
        const agentMessage = {
          id: `msg_${Date.now()}`,
          role: "agent",
          content: response.message,
          timestamp: new Date().toISOString(),
          data: response.data || {},
          completed: true,
        };
        setMessages((prev) => [...prev, agentMessage]);
        setIsTyping(false);
        pendingFirstInputRef.current = null;

        setTimeout(() => {
          navigate(
            response.data?.redirect ||
              `/my-reports/${response.data?.incident_id || ""}`,
          );
        }, 800);
        return;
      }

      // Handle no-workflow
      if (response.action === "no_workflow") {
        completedRef.current = true;
        referenceValidationPendingRef.current = false;
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
            messageContent = messageContent.replace(
              question,
              `**${question}**`,
            );
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
        if (response.completed) {
          completedRef.current = true;
        }
      }, 800);
    } else if (response.type === "error") {
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

  // Resolve the effective user ID: customer's ID when on-behalf, else logged-in user
  const effectiveUserId = customerDetails ? customerDetails.user_id : userId;
  const effectiveUserDetails = customerDetails
    ? {
        name: customerDetails.full_name,
        phone: customerDetails.phone,
        address: customerDetails.address,
      }
    : {
        name: userDetails.name || null,
        phone: userDetails.phone || null,
        address: userDetails.address || null,
      };

  const buildInitialDataFull = (extra = {}) => ({
    ...extra,
    user_details: effectiveUserDetails,
    ...(selectedReferenceId
      ? {
          reference_id: selectedReferenceId,
        }
      : {}),
    ...(customerDetails
      ? { reported_by_staff_id: userId, on_behalf: true }
      : {}),
  });

  const sendStartOrResume = (
    ws,
    { shouldResume = false, useCase = "", extraInitialData = {} } = {},
  ) => {
    const incidentId = incidentIdRef.current || `incident_${Date.now()}`;
    if (!incidentIdRef.current) {
      incidentIdRef.current = incidentId;
    }

    const resolvedUseCase = useCase || activeUseCaseRef.current || "";
    const initialData = buildInitialDataFull(
      resolvedUseCase
        ? { ...extraInitialData, use_case: resolvedUseCase }
        : extraInitialData,
    );
    const payload =
      shouldResume && hasStartedWorkflowRef.current
        ? {
            type: "resume_session",
            incident_id: incidentId,
            tenant_id: tenantId,
            user_id: effectiveUserId,
            use_case: resolvedUseCase,
            initial_data: initialData,
          }
        : {
            type: "start",
            incident_id: incidentId,
            tenant_id: tenantId,
            user_id: effectiveUserId,
            use_case: resolvedUseCase,
            initial_data: initialData,
          };

    if (!shouldResume) {
      hasStartedWorkflowRef.current = true;
    }

    ws.send(JSON.stringify(payload));
  };

  const scheduleReconnect = () => {
    if (manualCloseRef.current || completedRef.current || !incidentStarted) return;
    reconnectAttemptsRef.current += 1;
    const delayMs = Math.min(
      1000 * 2 ** (reconnectAttemptsRef.current - 1),
      10000,
    );
    clearTimeout(reconnectTimerRef.current);
    reconnectTimerRef.current = setTimeout(() => {
      startIncident({ reconnect: true });
    }, delayMs);
  };

  const attachSocketHandlers = (ws, { reconnect = false } = {}) => {
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      reconnectAttemptsRef.current = 0;
      if (reconnect && hasStartedWorkflowRef.current) {
        sendStartOrResume(ws, { shouldResume: true });
      } else {
        promptForReferenceId({ replace: messages.length === 0 });
      }
    };

    ws.onmessage = (event) => {
      const response = JSON.parse(event.data);
      handleAgentMessage(response);
    };

    ws.onerror = (event) => {
      console.error("[FloatingChatWidget][WebSocket] error", event);
      setIsConnected(false);
    };

    ws.onclose = (event) => {
      console.warn("[FloatingChatWidget][WebSocket] closed", {
        code: event.code,
        reason: event.reason,
        wasClean: event.wasClean,
      });
      setIsConnected(false);
      wsRef.current = null;
      if (manualCloseRef.current || completedRef.current) return;
      scheduleReconnect();
    };
  };

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
    activeUseCaseRef.current = useCase;
    sendStartOrResume(wsRef.current, { useCase });
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
        }),
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
      if (/^\d{10}$/.test(phone))
        phone = "+44" + phone; // 7700900101 → +447700900101
      else if (/^0\d{10}$/.test(phone))
        phone = "+44" + phone.slice(1); // 07700900101 → +447700900101
      else if (/^44\d{10}$/.test(phone))
        phone = "+" + phone; // 447700900101 → +447700900101
      else if (!phone.startsWith("+")) phone = "+" + phone; // catch-all
      setMessages((prev) => [
        ...prev,
        {
          id: `msg_${Date.now()}`,
          role: "user",
          content: phone,
          timestamp: new Date().toISOString(),
        },
      ]);
      setIsTyping(true);
      lookupCustomerByPhone(phone)
        .then((customer) => {
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
            promptForReportType();
          }, 600);
        })
        .catch(() => {
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

    if (isReferenceIdPending) {
      setInputText("");
      const normalizedReferenceId = normalizeDemoReferenceId(text);
      setMessages((prev) => [
        ...prev,
        {
          id: `msg_${Date.now()}`,
          role: "user",
          content: normalizedReferenceId || text,
          timestamp: new Date().toISOString(),
        },
      ]);

      if (workflowStarted) {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(
            JSON.stringify({
              type: "user_input",
              session_id: sessionId,
              input: { message: normalizedReferenceId || text },
            }),
          );
        }
        return;
      }

      if (normalizedReferenceId) {
        handleReferenceIdSelect(normalizedReferenceId, {
          appendUserMessage: false,
        });
      } else {
        addAgentMessage(
          "Please enter a valid REF ID to continue.",
          {
            refIdPrompt: true,
          },
        );
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
      activeUseCaseRef.current = "";
      sendStartOrResume(wsRef.current, { useCase: "" });
    } else {
      wsRef.current.send(
        JSON.stringify({
          type: "user_input",
          session_id: sessionId,
          input: { message: text },
        }),
      );
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
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
            if (!incidentStarted) {
              startIncident();
            } else if (!wsRef.current || wsRef.current.readyState > WebSocket.OPEN) {
              startIncident({ reconnect: true });
            }
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
                  onClick={() => {
                    manualCloseRef.current = true;
                    clearTimeout(reconnectTimerRef.current);
                    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) {
                      wsRef.current.close();
                    }
                    setChatOpen(false);
                  }}
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
                    ? `Customer: ${customerDetails.full_name}`
                    : "Enter customer phone to begin"
                  : selectedReferenceId
                    ? `REF ID: ${selectedReferenceId}`
                    : "Enter REF ID to begin"
                : "Ready to assist you"}
            </p>
          </div>

          {/* Messages */}
          <div
            style={{
              ...styles.messagesContainer,
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
                {messages.map((message) => (
                  <React.Fragment key={message.id}>
                    <ChatMessage
                      message={message}
                      onOptionClick={
                        message.data?.refIdPrompt
                          ? handleReferenceIdSelect
                          : handleIncidentOptionClick
                      }
                    />
                    {message.data?.reportTypePrompt &&
                      message.role === "agent" &&
                      !isReferenceIdPending &&
                      !!selectedReferenceId &&
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
                                    formatUseCaseName(wf.use_case),
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
                                  e.currentTarget.style.backgroundColor =
                                    "#edf5fc";
                                  e.currentTarget.style.transform =
                                    "translateY(-1px)";
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.borderColor = "#e2e8f0";
                                  e.currentTarget.style.backgroundColor =
                                    "white";
                                  e.currentTarget.style.transform =
                                    "translateY(0)";
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
                                onClick={() =>
                                  setShowAllCategories(!showAllCategories)
                                }
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
                                {showAllCategories
                                  ? "Show less ▲"
                                  : "Show more ▼"}
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
              <>
                <div style={styles.inputWrapper}>
                  <input
                    type="text"
                    style={styles.textInput}
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={
                      phoneCollectionPhase
                        ? "Enter customer phone number..."
                        : isReferenceIdPending
                          ? "Enter REF ID..."
                          : "Type your message..."
                    }
                    disabled={!isConnected || isProcessing}
                  />

                  <button
                    style={{ ...styles.iconButton, ...styles.sendButton }}
                    onClick={sendMessage}
                    disabled={!isConnected || !inputText.trim() || isProcessing}
                    onMouseEnter={(e) => {
                      if (!e.target.disabled)
                        e.target.style.transform = "scale(1.05)";
                    }}
                    onMouseLeave={(e) => {
                      e.target.style.transform = "scale(1)";
                    }}
                  >
                    ➤
                  </button>
                </div>
                <p style={styles.hint}>
                  {isProcessing
                    ? "Processing..."
                    : isReferenceIdPending
                      ? "Enter REF ID to continue"
                      : "Enter to send"}
                </p>
              </>
            </div>
          )}
        </div>
      )}
    </>
  );
});

export default FloatingChatWidget;
