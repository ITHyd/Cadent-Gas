import { useEffect, useRef, useState } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { connectWebSocket } from "../services/websocket";
import ChatMessage from "../components/ChatMessage";
import QuestionInput from "../components/QuestionInput";
import WorkflowVisualization from "../components/WorkflowVisualization";
import { normalizeDemoReferenceId } from "../constants/referenceIds";
import { useAuth } from "../contexts/AuthContext";
import ProfileDropdown from "../components/ProfileDropdown";

const AgentChat = () => {
  const { user } = useAuth();
  const { incidentId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { useCase, geoLocation, locationText, description } = location.state || {};

  const [messages, setMessages] = useState([]);
  const [currentAction, setCurrentAction] = useState(null);
  const [sessionId, setSessionId] = useState("");
  const [isComplete, setIsComplete] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isTyping, setIsTyping] = useState(false);

  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const manualCloseRef = useRef(false);
  const hasStartedRef = useRef(false);
  const isCompleteRef = useRef(false);

  useEffect(() => {
    isCompleteRef.current = isComplete;
  }, [isComplete]);

  useEffect(() => {
    let isCancelled = false;
    const buildInitialData = () => ({
      incident_id: incidentId,
      description: description || null,
      location: locationText || null,
      geo_location: geoLocation || null,
      user_details: {
        name: user?.full_name || null,
        phone: user?.phone || null,
        address: locationText || null,
      },
    });

    const scheduleReconnect = () => {
      if (isCancelled || manualCloseRef.current || isCompleteRef.current) return;
      reconnectAttemptsRef.current += 1;
      const delayMs = Math.min(1000 * 2 ** (reconnectAttemptsRef.current - 1), 10000);
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = setTimeout(() => {
        connectSocket(true);
      }, delayMs);
    };

    const attachSocketHandlers = (ws, shouldResume) => {
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
        const payload = shouldResume && hasStartedRef.current
          ? {
              type: "resume_session",
              incident_id: incidentId,
              tenant_id: user?.tenant_id,
              user_id: user?.user_id,
              use_case: useCase,
              initial_data: buildInitialData(),
            }
          : {
              type: "start",
              incident_id: incidentId,
              tenant_id: user?.tenant_id,
              user_id: user?.user_id,
              use_case: useCase,
              initial_data: buildInitialData(),
            };

        hasStartedRef.current = true;
        ws.send(JSON.stringify(payload));
      };

      ws.onmessage = (event) => {
        try {
          const response = JSON.parse(event.data);
          handleAgentMessage(response);
        } catch {
          setIsTyping(false);
        }
      };

      ws.onerror = (event) => {
        console.error("[AgentChat][WebSocket] error", event);
      };

      ws.onclose = (event) => {
        console.warn("[AgentChat][WebSocket] closed", {
          code: event.code,
          reason: event.reason,
          wasClean: event.wasClean,
        });
        setIsConnected(false);
        wsRef.current = null;
        if (manualCloseRef.current || isCancelled || isCompleteRef.current) return;
        scheduleReconnect();
      };
    };

    const connectSocket = async (shouldResume = false) => {
      const transportSessionId = `session_${Date.now()}`;
      try {
        setSessionId(transportSessionId);
        const ws = await connectWebSocket(transportSessionId);
        if (isCancelled) {
          if (ws.readyState <= WebSocket.OPEN) {
            ws.close();
          }
          return;
        }
        attachSocketHandlers(ws, shouldResume);
      } catch (error) {
        if (isCancelled) return;
        setIsConnected(false);
        console.error("[AgentChat][WebSocket] connect failed", error);
        scheduleReconnect();
      }
    };

    manualCloseRef.current = false;
    connectSocket(false);

    return () => {
      isCancelled = true;
      manualCloseRef.current = true;
      clearTimeout(reconnectTimerRef.current);
      if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) {
        wsRef.current.close();
      }
    };
  }, [
    incidentId,
    useCase,
    description,
    locationText,
    geoLocation,
    user?.full_name,
    user?.phone,
  ]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const handleAgentMessage = (response) => {
    if (response.type === "typing") {
      setIsTyping(response.typing);
      return;
    }

    if (response.type === "agent_message") {
      if (response.session_id && response.session_id !== sessionId) {
        setSessionId(response.session_id);
      }
      setIsTyping(false);
      if (response.action === "open_existing_incident") {
        const agentMessage = {
          id: `msg_${Date.now()}`,
          role: "agent",
          content: response.message,
          timestamp: new Date().toISOString(),
          data: response.data,
        };
        setMessages((prev) => [...prev, agentMessage]);
        setIsComplete(true);

        setTimeout(() => {
          navigate(response.data?.redirect || `/my-reports/${response.data?.incident_id}`);
        }, 800);
        return;
      }

      // Handle no-workflow redirect to manual report form
      if (response.action === "no_workflow") {
        const agentMessage = {
          id: `msg_${Date.now()}`,
          role: "agent",
          content: response.message,
          timestamp: new Date().toISOString(),
          data: response.data,
        };
        setMessages((prev) => [...prev, agentMessage]);
        setIsComplete(true);

        // Redirect to /report in manual mode after a short delay
        setTimeout(() => {
          navigate("/report", {
            state: {
              manualReport: true,
              incidentId: response.data?.incident_id || incidentId,
              classifiedUseCase: response.data?.classified_use_case || "",
              description:
                messages.find((m) => m.role === "user")?.content || "",
            },
          });
        }, 2500);
        return;
      }

      const agentMessage = {
        id: `msg_${Date.now()}`,
        role: "agent",
        content: response.message,
        timestamp: new Date().toISOString(),
        data: response.data, // Include data for options and kb_validation
        kb_validation: response.data?.kb_validation, // Store KB validation
        risk_assessment: response.data?.risk_assessment, // Store risk assessment
      };
      setMessages((prev) => [...prev, agentMessage]);

      setCurrentAction({
        action: response.action,
        data: response.data,
      });

      if (response.completed) {
        setIsComplete(true);
      }
      return;
    }

    if (response.type === "error") {
      setIsTyping(false);
    }
  };

  // Common incident examples for quick start
  const commonExamples = [
    { icon: "🔥", text: "I smell gas in my kitchen", category: "Emergency" },
    {
      icon: "💨",
      text: "Weak or yellow flame on my stove",
      category: "Appliance",
    },
    {
      icon: "🔊",
      text: "I hear a hissing sound near the gas line",
      category: "Emergency",
    },
    {
      icon: "📊",
      text: "My gas meter is running very fast",
      category: "Meter",
    },
    { icon: "🌙", text: "I only smell gas at night", category: "Pattern" },
    {
      icon: "🚫",
      text: "My gas supply has completely stopped",
      category: "Supply",
    },
  ];

  const handleExampleClick = (exampleText) => {
    sendUserInput({ message: exampleText });
  };

  const sendUserInput = (input) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }

    let outgoingInput = input;
    let displayContent =
      typeof input === "string"
        ? input
        : input?.message || input?.text || JSON.stringify(input);

    if (currentAction?.action === "reference_id_prompt") {
      const rawReferenceValue =
        typeof input === "string" ? input : input?.message || input?.text || "";
      const normalizedReferenceValue = normalizeDemoReferenceId(rawReferenceValue);

      if (normalizedReferenceValue) {
        displayContent = normalizedReferenceValue;
        if (typeof input === "string") {
          outgoingInput = { message: normalizedReferenceValue };
        } else if (input?.message !== undefined) {
          outgoingInput = { ...input, message: normalizedReferenceValue };
        } else if (input?.text !== undefined) {
          outgoingInput = { ...input, text: normalizedReferenceValue };
        } else {
          outgoingInput = { message: normalizedReferenceValue };
        }
      } else {
        displayContent = rawReferenceValue;
      }
    }

    const userMessage = {
      id: `msg_${Date.now()}`,
      role: "user",
      content: displayContent,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);

    wsRef.current.send(
      JSON.stringify({
        type: "user_input",
        session_id: sessionId,
        input: outgoingInput,
      }),
    );

    setCurrentAction(null);
  };

  const handleOptionClick = (option) => {
    // Send the selected option as user input
    sendUserInput({ message: option });
  };

  const getQuestionInputData = () => {
    if (!currentAction) return null;

    if (currentAction.action === "question") {
      return currentAction.data;
    }

    if (currentAction.action === "reference_id_prompt") {
      return {
        question_type: "text",
        question_text: "REF ID",
        required: true,
        placeholder: "Enter REF ID",
      };
    }

    if (currentAction.action === "awaiting_incident_report") {
      return {
        question_type: "text",
        question_text: "Incident description",
        required: true,
        placeholder: "Describe the gas-related issue",
      };
    }

    return null;
  };

  const questionInputData = getQuestionInputData();

  return (
    <main className="page-container max-w-[1500px]">
      <ProfileDropdown />
      <div className="flex flex-col gap-6 xl:flex-row">
        <section className="surface-card flex min-h-[78vh] flex-1 flex-col overflow-hidden">
          <header className="border-b border-slate-200/80 bg-white/60 px-5 py-4 md:px-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h1 className="text-2xl font-bold text-slate-900">
                  🛡️ Gas Safety Assistant
                </h1>
                <p className="mt-1 text-sm text-slate-600">
                  {isComplete
                    ? `Assessment complete for incident ${incidentId?.slice(0, 8) || "unknown"}`
                    : messages.length === 0
                      ? "I'm here to help you 24/7 with any gas-related concerns"
                      : `Helping you with incident ${incidentId?.slice(0, 8) || "unknown"}`}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`status-pill ${
                    isConnected
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-rose-200 bg-rose-50 text-rose-700"
                  }`}
                >
                  <span
                    className={`h-2 w-2 rounded-full ${isConnected ? "bg-emerald-500" : "bg-rose-500"}`}
                  />
                  {isConnected ? "Connected" : "Disconnected"}
                </span>
                {isComplete && (
                  <span className="status-pill border-brand-200 bg-brand-50 text-brand-700">
                    ✅ Complete
                  </span>
                )}
              </div>
            </div>
          </header>

          <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50/70 px-4 py-5 md:px-6">
            {messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                onOptionClick={handleOptionClick}
              />
            ))}

            {/* Show KB Validation after completion */}
            {isComplete &&
              messages.length > 0 &&
              (() => {
                const lastMessage = messages[messages.length - 1];
                const kbValidation = lastMessage?.kb_validation;

                // Debug logging
                console.log("🔍 KB Validation Debug:", {
                  isComplete,
                  messageCount: messages.length,
                  lastMessage: lastMessage,
                  kbValidation: kbValidation,
                });

                // Show debug info if no KB validation
                if (!kbValidation) {
                  return (
                    <div
                      style={{
                        padding: "16px",
                        background: "#f8fafc",
                        border: "1px solid #e2e8f0",
                        borderRadius: "12px",
                        fontSize: "0.85rem",
                        color: "#64748b",
                      }}
                    >
                      ℹ️ No KB validation data available for this incident
                    </div>
                  );
                }

                if (kbValidation.verdict === "unknown") {
                  return (
                    <div
                      style={{
                        padding: "16px",
                        background: "#f8fafc",
                        border: "1px solid #e2e8f0",
                        borderRadius: "12px",
                        fontSize: "0.85rem",
                        color: "#64748b",
                      }}
                    >
                      🔍 No similar incidents found in knowledge base (scores:
                      true={kbValidation.true_kb_score?.toFixed(2) || 0}, false=
                      {kbValidation.false_kb_score?.toFixed(2) || 0})
                    </div>
                  );
                }

                if (!kbValidation.verdict) return null;

                const isTrue = kbValidation.verdict === "true";
                const confidence = kbValidation.confidence || 0;
                const matchedEntry = kbValidation.matched_entry;

                return (
                  <div
                    style={{
                      borderRadius: "16px",
                      overflow: "hidden",
                      border: isTrue
                        ? "1px solid #bbf7d0"
                        : "1px solid #fde68a",
                      background: "#fff",
                      boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                    }}
                  >
                    <div
                      style={{
                        padding: "16px 20px",
                        background: isTrue
                          ? "linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)"
                          : "linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%)",
                        borderBottom: isTrue
                          ? "1px solid #bbf7d0"
                          : "1px solid #fde68a",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                        gap: "10px",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "10px",
                        }}
                      >
                        <span style={{ fontSize: "1.4rem" }}>
                          {isTrue ? "⚠️" : "ℹ️"}
                        </span>
                        <div>
                          <div
                            style={{
                              fontWeight: "700",
                              fontSize: "1rem",
                              color: "#1e293b",
                            }}
                          >
                            Knowledge Base Match
                          </div>
                          <div
                            style={{
                              fontSize: "0.8rem",
                              color: "#64748b",
                              marginTop: "2px",
                            }}
                          >
                            {isTrue
                              ? "Similar confirmed incident"
                              : "Similar false alarm"}
                          </div>
                        </div>
                      </div>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                        }}
                      >
                        <span
                          style={{
                            padding: "4px 12px",
                            borderRadius: "8px",
                            fontSize: "0.8rem",
                            fontWeight: "700",
                            background: isTrue ? "#dcfce7" : "#fef3c7",
                            color: isTrue ? "#166534" : "#92400e",
                            border: isTrue
                              ? "1px solid #86efac"
                              : "1px solid #fcd34d",
                          }}
                        >
                          {isTrue ? "True Incident" : "False Report"}
                        </span>
                        <span
                          style={{
                            padding: "4px 12px",
                            borderRadius: "8px",
                            fontSize: "0.8rem",
                            fontWeight: "700",
                            background:
                              confidence >= 0.7
                                ? "#dcfce7"
                                : confidence >= 0.4
                                  ? "#fef3c7"
                                  : "#fee2e2",
                            color:
                              confidence >= 0.7
                                ? "#166534"
                                : confidence >= 0.4
                                  ? "#92400e"
                                  : "#991b1b",
                          }}
                        >
                          {(confidence * 100).toFixed(0)}% match
                        </span>
                      </div>
                    </div>
                    <div style={{ padding: "18px 20px" }}>
                      {matchedEntry?.description && (
                        <div style={{ marginBottom: "14px" }}>
                          <div
                            style={{
                              fontSize: "0.75rem",
                              fontWeight: "700",
                              color: "#64748b",
                              marginBottom: "6px",
                              textTransform: "uppercase",
                            }}
                          >
                            Similar Case
                          </div>
                          <div
                            style={{
                              fontSize: "0.9rem",
                              color: "#334155",
                              lineHeight: 1.6,
                            }}
                          >
                            {matchedEntry.description}
                          </div>
                        </div>
                      )}
                      {isTrue && matchedEntry?.root_cause && (
                        <div
                          style={{
                            marginBottom: "14px",
                            padding: "12px 14px",
                            borderRadius: "10px",
                            background: "#fef2f2",
                            borderLeft: "4px solid #f87171",
                          }}
                        >
                          <div
                            style={{
                              fontSize: "0.75rem",
                              fontWeight: "700",
                              color: "#991b1b",
                              marginBottom: "4px",
                            }}
                          >
                            Typical Root Cause
                          </div>
                          <div
                            style={{
                              fontSize: "0.85rem",
                              color: "#7f1d1d",
                              lineHeight: 1.5,
                            }}
                          >
                            {matchedEntry.root_cause}
                          </div>
                        </div>
                      )}
                      {matchedEntry?.tags && matchedEntry.tags.length > 0 && (
                        <div
                          style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: "6px",
                            marginTop: "10px",
                          }}
                        >
                          {matchedEntry.tags.slice(0, 5).map((tag, i) => (
                            <span
                              key={i}
                              style={{
                                padding: "3px 10px",
                                borderRadius: "6px",
                                fontSize: "0.75rem",
                                fontWeight: "600",
                                background: "#f1f5f9",
                                color: "#475569",
                              }}
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}

            {/* Show common examples after first agent message, before user responds */}
            {messages.length === 1 &&
              messages[0].role === "agent" &&
              !messages[0].data?.refIdPrompt &&
              currentAction?.action !== "reference_id_exists" && (
              <div className="rounded-2xl border border-slate-200 bg-white/70 p-6">
                <h4 className="mb-4 text-sm font-semibold text-slate-700">
                  💡 Common Issues - Click to Start:
                </h4>
                <div className="grid gap-3 sm:grid-cols-2">
                  {commonExamples.map((example, index) => (
                    <button
                      key={index}
                      onClick={() => handleExampleClick(example.text)}
                      className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-3 text-left transition-all hover:border-blue-300 hover:bg-blue-50 hover:shadow-sm"
                      style={{ cursor: "pointer" }}
                    >
                      <span className="text-2xl">{example.icon}</span>
                      <div className="flex-1">
                        <div className="text-sm font-medium text-slate-900">
                          {example.text}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {example.category}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
                <p className="mt-4 text-center text-xs text-slate-500">
                  Or describe your situation in your own words below
                </p>
              </div>
            )}

            {isTyping && (
              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-start",
                  marginBottom: 14,
                }}
              >
                <div
                  style={{
                    padding: "14px 20px",
                    borderRadius: 14,
                    border: "1px solid #d8e3ee",
                    background: "#ffffff",
                    boxShadow: "0 12px 24px -22px rgba(15, 31, 51, 0.45)",
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                  }}
                >
                  <span
                    className="typing-dot"
                    style={{ animationDelay: "0ms" }}
                  />
                  <span
                    className="typing-dot"
                    style={{ animationDelay: "150ms" }}
                  />
                  <span
                    className="typing-dot"
                    style={{ animationDelay: "300ms" }}
                  />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {!isComplete && currentAction && (
            <div className="border-t border-slate-200 bg-white/70 px-5 py-4 md:px-6">
              {questionInputData && (
                <QuestionInput
                  questionData={questionInputData}
                  onSubmit={sendUserInput}
                />
              )}
            </div>
          )}

          {isComplete && (
            <div className="border-t border-slate-200 bg-white/70 px-5 py-4 text-center md:px-6">
              <button
                type="button"
                onClick={() => navigate("/dashboard")}
                className="btn-primary"
              >
                Return To Dashboard
              </button>
            </div>
          )}
        </section>

        <aside className="surface-card w-full xl:w-[380px]">
          <WorkflowVisualization
            workflowId={useCase}
            currentStep={currentAction?.action}
          />
        </aside>
      </div>
    </main>
  );
};

export default AgentChat;
