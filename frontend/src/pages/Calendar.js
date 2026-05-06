import React, { useState, useEffect } from 'react';
import * as api from '../services/api';

export default function Calendar() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [daysAhead, setDaysAhead] = useState(90);

  useEffect(() => { load(); }, [daysAhead]);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.getCalendarEvents(daysAhead);
      setEvents(r.data);
    } finally { setLoading(false); }
  };

  const filtered = filter === 'all' ? events : events.filter(e => e.event_type === filter);
  const types = [...new Set(events.map(e => e.event_type))];

  // Group by month
  const grouped = filtered.reduce((acc, e) => {
    const month = e.start_date ? new Date(e.start_date).toLocaleDateString('en-KE', { month: 'long', year: 'numeric' }) : 'Unknown';
    if (!acc[month]) acc[month] = [];
    acc[month].push(e);
    return acc;
  }, {});

  return (
    <div data-testid="calendar-page" style={{ fontFamily: 'Arial, Helvetica, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '24px' }}>
        <div>
          <h1 style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '-0.05em', color: '#191919', margin: 0 }}>HR Calendar</h1>
          <p style={{ color: '#525252', fontSize: '13px', margin: '4px 0 0' }}>{filtered.length} events · next {daysAhead} days · EAT timezone</p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {[30, 90, 180].map(d => (
            <button key={d} data-testid={`days-${d}`} onClick={() => setDaysAhead(d)} style={{ padding: '6px 12px', backgroundColor: daysAhead === d ? '#191919' : 'transparent', color: daysAhead === d ? '#fff' : '#191919', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{d}d</button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: '6px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <button onClick={() => setFilter('all')} style={{ padding: '4px 10px', backgroundColor: filter === 'all' ? '#FF353F' : 'transparent', color: filter === 'all' ? '#fff' : '#525252', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.05em' }}>All ({events.length})</button>
        {types.map(t => (
          <button key={t} onClick={() => setFilter(t)} style={{ padding: '4px 10px', backgroundColor: filter === t ? '#191919' : 'transparent', color: filter === t ? '#fff' : '#525252', border: '1px solid rgba(25,25,25,0.2)', cursor: 'pointer', fontSize: '11px', fontWeight: 700, fontFamily: 'Arial', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t} ({events.filter(e => e.event_type === t).length})</button>
        ))}
      </div>

      {loading ? <div style={{ padding: '48px', textAlign: 'center' }}>Loading...</div> : Object.keys(grouped).length === 0 ? (
        <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)', padding: '48px', textAlign: 'center', color: '#9CA3AF' }}>No events in this window</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {Object.entries(grouped).map(([month, items]) => (
            <div key={month}>
              <h3 style={{ fontSize: '13px', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#525252', margin: '0 0 8px' }}>{month}</h3>
              <div style={{ backgroundColor: '#fff', border: '1px solid rgba(25,25,25,0.08)' }}>
                {items.map((e, i) => (
                  <div key={e.id || i} data-testid={`event-${i}`} style={{ display: 'grid', gridTemplateColumns: '80px 1fr auto', gap: '16px', padding: '12px 16px', borderBottom: i < items.length - 1 ? '1px solid rgba(25,25,25,0.05)' : 'none', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: '20px', fontWeight: 900, color: '#191919', letterSpacing: '-0.04em' }}>{e.start_date ? new Date(e.start_date).getDate() : '?'}</div>
                      <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#525252' }}>{e.start_date ? new Date(e.start_date).toLocaleDateString('en-KE', { weekday: 'short', month: 'short' }) : ''}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 700, color: '#191919' }}>{e.title}</div>
                      <div style={{ fontSize: '11px', color: '#525252', marginTop: '2px' }}>{e.module || ''} {e.description ? `· ${e.description}` : ''}</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ width: '8px', height: '8px', backgroundColor: e.color || '#9CA3AF', borderRadius: '50%' }} />
                      <span style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: e.color || '#525252', fontWeight: 700 }}>{e.event_type}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
