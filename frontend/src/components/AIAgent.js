import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { X, Send, AlertCircle, RefreshCw } from 'lucide-react';
import * as api from '../services/api';

export default function AIAgent({ onClose }) {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    // Load initial compliance check
    runInitialCheck();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const runInitialCheck = async () => {
    try {
      const res = await api.runComplianceCheck();
      setMessages([{
        id: Date.now(),
        role: 'assistant',
        content: `**Compliance Guardian Active**\n\n${res.data.status}`,
        timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })
      }]);
    } catch {
      setMessages([{
        id: Date.now(),
        role: 'assistant',
        content: 'Hello! I\'m your Solvit HR AI Agent. I can help you with:\n\n• **Policy Q&A** — Ask about any company policy\n• **Compliance checks** — Upcoming deadlines and alerts\n• **HR guidance** — Best practices and procedures\n\nHow can I help you today?',
        timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })
      }]);
    }
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: input,
      timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })
    };
    setMessages(prev => [...prev, userMsg]);
    const question = input;
    setInput('');
    setLoading(true);

    try {
      const res = await api.chatWithAgent({ message: question, conversation_id: conversationId });
      if (!conversationId) setConversationId(res.data.conversation_id);
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'assistant',
        content: res.data.response,
        provider: res.data.provider,
        timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })
      }]);
    } catch {
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'assistant',
        content: 'I encountered an error. Please check Settings to configure the AI provider.',
        timestamp: new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })
      }]);
    } finally {
      setLoading(false);
    }
  };

  const QUICK_PROMPTS = [
    'Check compliance status',
    'What is the leave policy?',
    'Any probation reviews due?',
    'NSSF/SHA deadlines?',
  ];

  return (
    <div style={{
      position: 'fixed', right: 0, top: 0, bottom: 0, width: '380px',
      backgroundColor: '#fff', borderLeft: '1px solid rgba(25,25,25,0.15)',
      display: 'flex', flexDirection: 'column', zIndex: 200,
      fontFamily: 'Arial, Helvetica, sans-serif', boxShadow: '-4px 0 24px rgba(0,0,0,0.08)'
    }}>
      {/* Header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(25,25,25,0.1)', backgroundColor: '#191919', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ color: '#fff', fontWeight: 900, fontSize: '14px', letterSpacing: '-0.03em' }}>AI HR Agent</div>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Policy Q&A + Compliance Guardian</div>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button onClick={runInitialCheck} title="Run compliance check" style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', padding: '4px' }}>
            <RefreshCw size={14} />
          </button>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', padding: '4px' }}>
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {messages.map(msg => (
          <div key={msg.id} style={{ display: 'flex', flexDirection: 'column', alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{
              maxWidth: '85%', padding: '10px 14px',
              backgroundColor: msg.role === 'user' ? '#FF353F' : '#F5F5F5',
              color: msg.role === 'user' ? '#fff' : '#191919',
              fontSize: '12px', lineHeight: 1.6,
              fontFamily: msg.role === 'assistant' ? 'monospace' : 'Arial',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word'
            }}>
              {msg.content}
            </div>
            <div style={{ fontSize: '10px', color: '#525252', marginTop: '3px', display: 'flex', gap: '6px', alignItems: 'center' }}>
              <span>{msg.timestamp}</span>
              {msg.provider && msg.provider !== 'fallback' && <span style={{ backgroundColor: '#22C55E', color: '#fff', padding: '0 4px', fontSize: '9px' }}>AI</span>}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', alignItems: 'flex-start' }}>
            <div style={{ padding: '10px 14px', backgroundColor: '#F5F5F5', fontFamily: 'monospace', fontSize: '12px', color: '#525252' }}>
              Processing...
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Quick prompts */}
      <div style={{ padding: '8px 16px', borderTop: '1px solid rgba(25,25,25,0.06)', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
        {QUICK_PROMPTS.map(p => (
          <button key={p} onClick={() => { setInput(p); }} style={{ padding: '4px 8px', border: '1px solid rgba(25,25,25,0.15)', backgroundColor: 'transparent', fontSize: '10px', cursor: 'pointer', color: '#525252', fontFamily: 'Arial', transition: 'all 0.15s' }}
            onMouseEnter={e => e.currentTarget.style.borderColor = '#FF353F'}
            onMouseLeave={e => e.currentTarget.style.borderColor = 'rgba(25,25,25,0.15)'}
          >{p}</button>
        ))}
      </div>

      {/* Input */}
      <form onSubmit={sendMessage} style={{ padding: '12px 16px', borderTop: '1px solid rgba(25,25,25,0.1)', display: 'flex', gap: '8px' }}>
        <input
          data-testid="ai-chat-input"
          value={input} onChange={e => setInput(e.target.value)}
          placeholder="Ask about policies, compliance..."
          disabled={loading}
          style={{ flex: 1, padding: '8px 12px', border: '1px solid rgba(25,25,25,0.2)', fontSize: '12px', outline: 'none', fontFamily: 'Arial', backgroundColor: '#fff' }}
          onFocus={e => e.target.style.borderColor = '#FF353F'}
          onBlur={e => e.target.style.borderColor = 'rgba(25,25,25,0.2)'}
        />
        <button data-testid="ai-chat-send" type="submit" disabled={loading || !input.trim()}
          style={{ padding: '8px 12px', backgroundColor: '#FF353F', color: '#fff', border: 'none', cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.7 : 1 }}>
          <Send size={14} />
        </button>
      </form>
    </div>
  );
}
