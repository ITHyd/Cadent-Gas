import { useEffect, useRef, useState } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import { connectWebSocket } from '../services/websocket';
import { transcribeAudio } from '../services/api';
import ChatMessage from '../components/ChatMessage';
import QuestionInput from '../components/QuestionInput';
import UploadInput from '../components/UploadInput';
import LiveVoiceChat from '../components/LiveVoiceChat';
import WorkflowVisualization from '../components/WorkflowVisualization';
import { useAuth } from '../contexts/AuthContext';
import ProfileDropdown from '../components/ProfileDropdown';

const AgentChat = () => {
  const { user } = useAuth();
  const { incidentId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { useCase, geoLocation, locationText } = location.state || {};

  const [messages, setMessages] = useState([]);
  const [currentAction, setCurrentAction] = useState(null);
  const [sessionId, setSessionId] = useState('');
  const [isComplete, setIsComplete] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isTyping, setIsTyping] = useState(false);

  // Voice mode state
  const [voiceMode, setVoiceMode] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState('');
  const [isTranscribing, setIsTranscribing] = useState(false);

  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    const newSessionId = `session_${Date.now()}`;
    setSessionId(newSessionId);

    const ws = connectWebSocket(newSessionId);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      ws.send(
        JSON.stringify({
          type: 'start',
          incident_id: incidentId,
          tenant_id: user?.tenant_id,
          user_id: user?.user_id,
          use_case: useCase,
          initial_data: {
            incident_id: incidentId,
            location: locationText || null,
            geo_location: geoLocation || null,
            user_details: {
              name: user?.full_name || null,
              phone: user?.phone || null,
              address: locationText || null,
            },
          },
        }),
      );
    };

    ws.onmessage = (event) => {
      try {
        const response = JSON.parse(event.data);
        handleAgentMessage(response);
      } catch {
      }
    };

    ws.onerror = () => {
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    return () => {
      if (ws && ws.readyState <= WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [incidentId, useCase, locationText, geoLocation, user?.full_name, user?.phone]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleAgentMessage = (response) => {
    if (response.type === 'typing') {
      setIsTyping(response.typing);
      return;
    }

    if (response.type === 'agent_message') {
      setIsTyping(false);
      // Handle no-workflow redirect to manual report form
      if (response.action === 'no_workflow') {
        const agentMessage = {
          id: `msg_${Date.now()}`,
          role: 'agent',
          content: response.message,
          timestamp: new Date().toISOString(),
          data: response.data,
        };
        setMessages((prev) => [...prev, agentMessage]);
        setIsComplete(true);

        // Redirect to /report in manual mode after a short delay
        setTimeout(() => {
          navigate('/report', {
            state: {
              manualReport: true,
              incidentId: response.data?.incident_id || incidentId,
              classifiedUseCase: response.data?.classified_use_case || '',
              description: messages.find((m) => m.role === 'user')?.content || '',
            },
          });
        }, 2500);
        return;
      }

      const agentMessage = {
        id: `msg_${Date.now()}`,
        role: 'agent',
        content: response.message,
        timestamp: new Date().toISOString(),
        data: response.data, // Include data for options
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

    if (response.type === 'error') {
    }
  };

  // Common incident examples for quick start
  const commonExamples = [
    { icon: '🔥', text: 'I smell gas in my kitchen', category: 'Emergency' },
    { icon: '💨', text: 'Weak or yellow flame on my stove', category: 'Appliance' },
    { icon: '🔊', text: 'I hear a hissing sound near the gas line', category: 'Emergency' },
    { icon: '📊', text: 'My gas meter is running very fast', category: 'Meter' },
    { icon: '🌙', text: 'I only smell gas at night', category: 'Pattern' },
    { icon: '🚫', text: 'My gas supply has completely stopped', category: 'Supply' },
  ];

  const handleExampleClick = (exampleText) => {
    sendUserInput({ message: exampleText });
  };

  const sendUserInput = (input) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }

    const userMessage = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: typeof input === 'string' ? input : JSON.stringify(input),
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);

    wsRef.current.send(
      JSON.stringify({
        type: 'user_input',
        session_id: sessionId,
        input,
      }),
    );

    setCurrentAction(null);
  };

  const handleOptionClick = (option) => {
    // Send the selected option as user input
    sendUserInput({ message: option });
  };

  const handleAudioReady = async (audioBlob) => {
    setIsTranscribing(true);
    try {
      const result = await transcribeAudio(audioBlob);
      if (result.text) {
        setVoiceTranscript((prev) => (prev ? prev + ' ' + result.text : result.text));
      } else {
        setVoiceTranscript((prev) => prev || '');
      }
    } catch {
      // Show a brief placeholder so the user knows to try again
      setVoiceTranscript((prev) => prev || '');
    } finally {
      setIsTranscribing(false);
    }
  };

  const handleSendTranscript = () => {
    if (voiceTranscript.trim()) {
      sendUserInput({ message: voiceTranscript.trim() });
      setVoiceTranscript('');
    }
  };

  const handleFileUpload = async (file) => {
    if (!file) {
      sendUserInput({ upload_skipped: true });
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('session_id', sessionId);

    try {
      const response = await fetch('/api/v1/upload', {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();

      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: 'upload_complete',
            session_id: sessionId,
            file_path: data.file_path,
            file_type: data.file_type,
          }),
        );
      }
    } catch {
    }
  };

  return (
    <main className="page-container max-w-[1500px]">
      <ProfileDropdown />
      <div className="flex flex-col gap-6 xl:flex-row">
        <section className="surface-card flex min-h-[78vh] flex-1 flex-col overflow-hidden">
          <header className="border-b border-slate-200/80 bg-white/60 px-5 py-4 md:px-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h1 className="text-2xl font-bold text-slate-900">🛡️ Gas Safety Assistant</h1>
                <p className="mt-1 text-sm text-slate-600">
                  {isComplete 
                    ? `Assessment complete for incident ${incidentId?.slice(0, 8) || 'unknown'}`
                    : messages.length === 0
                    ? "I'm here to help you 24/7 with any gas-related concerns"
                    : `Helping you with incident ${incidentId?.slice(0, 8) || 'unknown'}`
                  }
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`status-pill ${
                    isConnected
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : 'border-rose-200 bg-rose-50 text-rose-700'
                  }`}
                >
                  <span className={`h-2 w-2 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                  {isConnected ? 'Connected' : 'Disconnected'}
                </span>
                {isComplete && <span className="status-pill border-brand-200 bg-brand-50 text-brand-700">✅ Complete</span>}
              </div>
            </div>
          </header>

          <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50/70 px-4 py-5 md:px-6">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} onOptionClick={handleOptionClick} />
            ))}
            
            {/* Show common examples after first agent message, before user responds */}
            {messages.length === 1 && messages[0].role === 'agent' && (
              <div className="rounded-2xl border border-slate-200 bg-white/70 p-6">
                <h4 className="mb-4 text-sm font-semibold text-slate-700">💡 Common Issues - Click to Start:</h4>
                <div className="grid gap-3 sm:grid-cols-2">
                  {commonExamples.map((example, index) => (
                    <button
                      key={index}
                      onClick={() => handleExampleClick(example.text)}
                      className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-3 text-left transition-all hover:border-blue-300 hover:bg-blue-50 hover:shadow-sm"
                      style={{ cursor: 'pointer' }}
                    >
                      <span className="text-2xl">{example.icon}</span>
                      <div className="flex-1">
                        <div className="text-sm font-medium text-slate-900">{example.text}</div>
                        <div className="mt-1 text-xs text-slate-500">{example.category}</div>
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
              <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 14 }}>
                <div
                  style={{
                    padding: '14px 20px',
                    borderRadius: 14,
                    border: '1px solid #d8e3ee',
                    background: '#ffffff',
                    boxShadow: '0 12px 24px -22px rgba(15, 31, 51, 0.45)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                  }}
                >
                  <span className="typing-dot" style={{ animationDelay: '0ms' }} />
                  <span className="typing-dot" style={{ animationDelay: '150ms' }} />
                  <span className="typing-dot" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {!isComplete && currentAction && !voiceMode && (
            <div className="border-t border-slate-200 bg-white/70 px-5 py-4 md:px-6">
              {currentAction.action === 'question' && (
                <QuestionInput questionData={currentAction.data} onSubmit={sendUserInput} />
              )}
              {currentAction.action === 'upload' && <UploadInput uploadData={currentAction.data} onUpload={handleFileUpload} />}
            </div>
          )}

          {!isComplete && voiceMode && (
            <div className="border-t border-slate-200 bg-white/70 px-5 py-4 md:px-6">
              <LiveVoiceChat
                sessionId={sessionId}
                isConnected={isConnected}
                transcribeMode={true}
                onAudioReady={handleAudioReady}
                onAudioResponse={() => {}}
                onStop={() => setVoiceMode(false)}
              />
              <div className="mt-3 flex gap-2">
                <textarea
                  className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm focus:border-blue-400 focus:outline-none"
                  rows={2}
                  placeholder={isTranscribing ? 'Transcribing...' : 'Tap the mic and speak. Your text will appear here — edit before sending.'}
                  value={voiceTranscript}
                  onChange={(e) => setVoiceTranscript(e.target.value)}
                  disabled={isTranscribing}
                />
                <button
                  onClick={handleSendTranscript}
                  disabled={!voiceTranscript.trim() || isTranscribing}
                  className="btn-primary self-end rounded-xl px-4 py-2 text-sm"
                  style={{ opacity: voiceTranscript.trim() ? 1 : 0.5 }}
                >
                  Send
                </button>
              </div>
            </div>
          )}

          {isComplete && (
            <div className="border-t border-slate-200 bg-white/70 px-5 py-4 text-center md:px-6">
              <button type="button" onClick={() => navigate('/dashboard')} className="btn-primary">
                Return To Dashboard
              </button>
            </div>
          )}
        </section>

        <aside className="surface-card w-full xl:w-[380px]">
          <WorkflowVisualization workflowId={useCase} currentStep={currentAction?.action} />
        </aside>
      </div>
    </main>
  );
};

export default AgentChat;
