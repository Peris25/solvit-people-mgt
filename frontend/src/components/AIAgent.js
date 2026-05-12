import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useTheme, themeTokens } from '../context/ThemeContext';
import { X, Send, RefreshCw, Sparkles } from 'lucide-react';
import * as api from '../services/api';

const QUICK_PROMPTS = [
  'Daily brief — what needs my attention today?',
  'Who has leave pending approval?',
  'Probation reviews due this week',
  'Headcount by department',
  'Status of solver tiers',
  'Open disciplinary cases',
  'Open recruitment requisitions',
  'NSSF / SHA / PAYE deadlines',
  'Show me the leave policy',
];

export default function AIAgent({ onClose }) {
  const { user } = useAuth();
  const { theme } = useTheme();
  const tk = themeTokens(theme);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const messagesEndRef = useRef(null);

  useEffect(() => { runInitialBrief(); }, []);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const runInitialBrief = async () => {
    try {
      const res = await api.getAiSnapshot();
      const s = res.data;
      const lines = [
        `**Good ${new Date().getHours() < 12 ? 'morning' : (new Date().getHours() < 17 ? 'afternoon' : 'evening')}, ${(user?.full_name || 'HR').split(' ')[0]}.**`,
        `Here's your live platform brief:`,
        ``,
        `• **Headcount:** ${s.headcount.total_active_fte} active FTE across ${Object.keys(s.headcount.by_department).length} departments`,
        `• **Leave:** ${s.leave.pending_approval} pending approval · ${s.leave.on_leave_today_count} on leave today`,
        `• **Performance:** ${s.performance.total_reviews} reviews on record`,
        `• **Recruitment:** ${s.recruitment.open_requisitions} open requisition(s) · ${s.recruitment.candidates_total} candidate(s)`,
        `• **Solvers:** ${s.solvers.total} total`,
        `• **Recognition (this month):** ${s.recognition.this_month}`,
        `• **Onboarding/probation:** ${s.onboarding.in_onboarding_or_probation} in progress`,
        ``,
        `**Compliance check:**`,
        ...(s.compliance_issues || []).map(i => `• ${i}`),
        ``,
        `Ask me anything — leave, performance, training, candidates, budget, solvers, policies, status of a specific employee. I work across the whole platform.`,
      ].filter(Boolean);
      setMessages([{
        id: Date.now(), role: 'assistant',
        content: lines.join('\n'),
        timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' }),
      }]);
    } catch {
      setMessages([{
        id: Date.now(), role: 'assistant',
        content: 'Hello! I\'m your Solvit HR AI Assistant. I can help you with anything across the platform — Leave, Performance, Recruitment, Onboarding, L&D, Recognition, Solvers, Budget, Disciplinary, Policies and Compliance. Try one of the quick prompts below.',
        timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' }),
      }]);
    }
  };

  const sendMessage = async (e, override) => {
    if (e) e.preventDefault();
    const text = override ?? input;
    if (!text.trim() || loading) return;
    const userMsg = { id: Date.now(), role: 'user', content: text,
      timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' }) };
    setMessages(prev => [...prev, userMsg]);
    setInput(''); setLoading(true);
    try {
      const res = await api.chatWithAgent({ message: text, conversation_id: conversationId });
      if (!conversationId) setConversationId(res.data.conversation_id);
      setMessages(prev => [...prev, {
        id: Date.now() + 1, role: 'assistant', content: res.data.response,
        provider: res.data.provider,
        proposed_action: res.data.proposed_action || null,
        timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' }),
      }]);
    } catch {
      setMessages(prev => [...prev, {
        id: Date.now() + 1, role: 'assistant',
        content: 'I hit an error reaching the assistant. Try again in a moment — or check the LLM provider configuration.',
        timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' }),
      }]);
    } finally { setLoading(false); }
  };

  const updateMessage = (id, patch) => setMessages(prev => prev.map(m => m.id === id ? { ...m, ...patch } : m));

  const confirmAction = async (msg, edits) => {
    const action = msg.proposed_action;
    updateMessage(msg.id, { actionStatus: 'running' });
    try {
      const r = await api.executeAiAction(action.id, edits && Object.keys(edits).length ? edits : null);
      updateMessage(msg.id, { actionStatus: r.data.outcome, actionResult: r.data.result, proposed_action: null });
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'assistant',
        content: r.data.outcome === 'executed'
          ? `Done. ${action.kind.replace(/_/g, ' ')} completed.`
          : `Action failed: ${r.data.result?.error || 'unknown error'}`,
        provider: 'live',
        timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' }),
      }]);
    } catch (err) {
      updateMessage(msg.id, { actionStatus: 'failed', actionError: err?.response?.data?.detail || err.message });
    }
  };

  const cancelAction = async (msg) => {
    const action = msg.proposed_action;
    try {
      await api.cancelAiAction(action.id);
      updateMessage(msg.id, { actionStatus: 'cancelled', proposed_action: null });
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'assistant',
        content: 'Cancelled. No action was taken.',
        provider: 'live',
        timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' }),
      }]);
    } catch (err) {
      updateMessage(msg.id, { actionStatus: 'failed', actionError: err?.response?.data?.detail || err.message });
    }
  };

  return (
    <div data-testid="ai-agent-panel" style={{
      position: 'fixed', right: 0, top: 0, bottom: 0, width: '420px',
      backgroundColor: '#fff', borderLeftWidth: '1px', borderLeftStyle: 'solid', borderLeftColor: 'rgba(25,25,25,0.15)',
      display: 'flex', flexDirection: 'column', zIndex: 200,
      fontFamily: 'Nunito Sans, sans-serif', boxShadow: '-4px 0 24px rgba(0,0,0,0.08)',
    }}>
      <div style={{ padding: '16px 20px', borderBottomWidth: '1px', borderBottomStyle: 'solid', borderBottomColor: 'rgba(25,25,25,0.1)', backgroundColor: tk.aiHeaderBg, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ width: '32px', height: '32px', backgroundColor: '#FF353F', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Sparkles size={16} color="#fff" />
          </div>
          <div>
            <div style={{ color: tk.aiHeaderText, fontWeight: 900, fontSize: '14px', letterSpacing: '-0.03em', fontFamily: 'Barlow' }}>Solvit HR Assistant</div>
            <div style={{ color: tk.aiHeaderMuted, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Barlow' }}>Full-platform copilot</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button data-testid="ai-refresh" onClick={runInitialBrief} title="Refresh daily brief" style={{ background: 'none', border: 'none', color: tk.aiHeaderMuted, cursor: 'pointer', padding: '4px' }}>
            <RefreshCw size={14} />
          </button>
          <button data-testid="ai-close" onClick={onClose} style={{ background: 'none', border: 'none', color: tk.aiHeaderMuted, cursor: 'pointer', padding: '4px' }}>
            <X size={16} />
          </button>
        </div>
      </div>

      <div data-testid="ai-messages" style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {messages.map(msg => (
          <div key={msg.id} style={{ display: 'flex', flexDirection: 'column', alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{
              maxWidth: '88%', padding: '10px 14px',
              backgroundColor: msg.role === 'user' ? '#FF353F' : '#F5F5F5',
              color: msg.role === 'user' ? '#fff' : '#191919',
              fontSize: '12px', lineHeight: 1.6, fontFamily: 'Nunito Sans',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>{msg.content}</div>
            {msg.proposed_action && (
              <ActionCard msg={msg} action={msg.proposed_action} onConfirm={confirmAction} onCancel={cancelAction} />
            )}
            {msg.actionStatus && (
              <div data-testid={`action-status-${msg.actionStatus}`} style={{ marginTop: '4px', fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: msg.actionStatus === 'executed' ? '#22C55E' : msg.actionStatus === 'cancelled' ? '#525252' : '#FF353F', fontFamily: 'Barlow' }}>
                {msg.actionStatus === 'executed' && '✓ Executed'}
                {msg.actionStatus === 'cancelled' && '· Cancelled'}
                {msg.actionStatus === 'failed' && '✗ Failed'}
                {msg.actionStatus === 'running' && 'Running…'}
              </div>
            )}
            <div style={{ fontSize: '10px', color: '#9CA3AF', marginTop: '3px', display: 'flex', gap: '6px', alignItems: 'center' }}>
              <span>{msg.timestamp}</span>
              {msg.provider && msg.provider !== 'fallback' && (
                <span style={{ backgroundColor: '#22C55E', color: '#fff', padding: '0 5px', fontSize: '9px', fontFamily: 'Barlow', fontWeight: 700, letterSpacing: '0.05em' }}>AI · {msg.provider}</span>
              )}
              {msg.provider === 'fallback' && (
                <span style={{ backgroundColor: '#525252', color: '#fff', padding: '0 5px', fontSize: '9px', fontFamily: 'Barlow', fontWeight: 700, letterSpacing: '0.05em' }}>Live data</span>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', alignItems: 'flex-start' }}>
            <div style={{ padding: '10px 14px', backgroundColor: '#F5F5F5', fontFamily: 'Nunito Sans', fontSize: '12px', color: '#525252' }}>
              Thinking…
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div style={{ padding: '10px 16px 6px', borderTopWidth: '1px', borderTopStyle: 'solid', borderTopColor: 'rgba(25,25,25,0.06)' }}>
        <div style={{ fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.18em', color: '#9CA3AF', fontFamily: 'Barlow', marginBottom: '6px' }}>Quick prompts</div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {QUICK_PROMPTS.map(p => (
            <button key={p} data-testid={`ai-prompt-${p.slice(0,12).replace(/[^a-zA-Z]/g, '-').toLowerCase()}`} onClick={() => sendMessage(null, p)} disabled={loading}
              style={{ padding: '4px 10px', border: '1px solid rgba(25,25,25,0.15)', backgroundColor: 'transparent', fontSize: '10px', cursor: loading ? 'not-allowed' : 'pointer', color: '#525252', fontFamily: 'Nunito Sans', transition: 'all 0.15s' }}
              onMouseEnter={e => { if (!loading) { e.currentTarget.style.borderColor = '#FF353F'; e.currentTarget.style.color = '#FF353F'; } }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(25,25,25,0.15)'; e.currentTarget.style.color = '#525252'; }}
            >{p}</button>
          ))}
        </div>
      </div>

      <form onSubmit={sendMessage} style={{ padding: '12px 16px', borderTopWidth: '1px', borderTopStyle: 'solid', borderTopColor: 'rgba(25,25,25,0.1)', display: 'flex', gap: '8px' }}>
        <input data-testid="ai-chat-input" value={input} onChange={e => setInput(e.target.value)}
          placeholder="Ask anything HR — e.g. 'Status of Sarah's leave', 'open requisitions', 'pay-band alerts'…"
          disabled={loading}
          style={{ flex: 1, padding: '8px 12px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '12px', outline: 'none', fontFamily: 'Nunito Sans', backgroundColor: '#fff' }}
          onFocus={e => e.target.style.borderColor = '#FF353F'}
          onBlur={e => e.target.style.borderColor = 'rgba(25,25,25,0.2)'} />
        <button data-testid="ai-chat-send" type="submit" disabled={loading || !input.trim()}
          style={{ padding: '8px 14px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: loading || !input.trim() ? 'not-allowed' : 'pointer', opacity: loading || !input.trim() ? 0.6 : 1 }}>
          <Send size={14} />
        </button>
      </form>
    </div>
  );
}

function ActionCard({ msg, action, onConfirm, onCancel }) {
  const [edits, setEdits] = React.useState({});
  const riskColor = action.risk === 'high' ? '#FF353F' : action.risk === 'medium' ? '#F59E0B' : '#22C55E';
  const editable = action.editable || {};
  return (
    <div data-testid={`action-card-${action.id}`} style={{
      marginTop: '8px', width: '88%', backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.12)',
      borderLeftWidth: '4px', borderLeftStyle: 'solid', borderLeftColor: riskColor, fontFamily: 'Nunito Sans',
    }}>
      <div style={{ padding: '8px 12px', backgroundColor: action.risk === 'high' ? '#FEE2E2' : action.risk === 'medium' ? '#FEF3C7' : '#DCFCE7', fontSize: '9px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: riskColor, fontFamily: 'Barlow' }}>
        Action proposed · {action.risk} risk · confirmation required
      </div>
      <div style={{ padding: '10px 14px', fontSize: '12px', color: '#191919', whiteSpace: 'pre-wrap' }} dangerouslySetInnerHTML={{ __html: simpleMd(action.summary) }} />

      {Object.keys(editable).length > 0 && (
        <div style={{ padding: '0 14px 10px' }}>
          {Object.entries(editable).map(([k, v]) => (
            <div key={k} style={{ marginBottom: '8px' }}>
              <label style={{ display: 'block', fontSize: '9px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#525252', marginBottom: '3px', fontFamily: 'Barlow' }}>{k.replace(/_/g, ' ')}</label>
              <textarea
                data-testid={`action-edit-${k}`}
                rows={2}
                defaultValue={v}
                onChange={e => setEdits(p => ({ ...p, [k]: e.target.value }))}
                style={{ width: '100%', padding: '6px 8px', border: '1px solid rgba(25,25,25,0.15)', fontSize: '11px', fontFamily: 'Nunito Sans', boxSizing: 'border-box', resize: 'vertical' }}
              />
            </div>
          ))}
        </div>
      )}

      <div style={{ padding: '8px 12px', borderTopWidth: '1px', borderTopStyle: 'solid', borderTopColor: 'rgba(25,25,25,0.06)', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
        <button data-testid={`action-cancel-${action.id}`} onClick={() => onCancel(msg)}
          style={{ padding: '6px 14px', border: '1px solid rgba(25,25,25,0.2)', backgroundColor: 'transparent', cursor: 'pointer', fontSize: '10px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          {action.cancel_label || 'Cancel'}
        </button>
        <button data-testid={`action-confirm-${action.id}`} onClick={() => onConfirm(msg, edits)}
          style={{ padding: '6px 14px', backgroundColor: riskColor, color: '#fff', border: 'none', cursor: 'pointer', fontSize: '10px', fontWeight: 700, fontFamily: 'Barlow', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          {action.confirm_label || 'Confirm'}
        </button>
      </div>
    </div>
  );
}

/** Render a tiny subset of markdown (**bold** and *italic*) used in summaries. */
function simpleMd(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>');
}
