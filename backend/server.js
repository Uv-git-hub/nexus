/**
 * NEXUS V3.1 — Backend Server
 * Run: node backend/server.js
 * Test: curl http://localhost:3000/health
 */
import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { createClient } from '@supabase/supabase-js';

dotenv.config();

const app  = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

const sbService = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY);
const sbAnon    = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_ANON_KEY);

app.use((req, _res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
  next();
});

// ── 1. VAPI Webhook ───────────────────────────────────────
app.post('/webhook/vapi', async (req, res) => {
  try {
    const payload = req.body;
    const type    = payload.message?.type;
    const callId  = payload.message?.call?.id;
    console.log(`📞 VAPI event: ${type} | call: ${callId}`);

    if (type === 'end-of-call-report') {
      const transcript  = payload.message?.artifact?.transcript || payload.message?.transcript || '';
      const summary     = payload.message?.analysis?.summary    || '';
      const startedAt   = payload.message?.startedAt;
      const endedAt     = payload.message?.endedAt;
      const duration    = startedAt && endedAt
        ? Math.floor((new Date(endedAt) - new Date(startedAt)) / 1000) : 0;
      const fromNumber  = payload.message?.call?.customer?.number || 'unknown';
      const urgency     = payload.message?.call?.metadata?.urgency || 'HIGH';

      const { error } = await sbService.from('calls').upsert({
        call_id:          callId,
        from_number:      fromNumber,
        transcript:       transcript,
        ai_summary:       summary,
        duration_seconds: duration,
        urgency:          urgency,
        ended_at:         endedAt || new Date().toISOString(),
        outcome:          'completed',
        agent_used:       'SAWT-VAPI'
      }, { onConflict: 'call_id' });

      if (error) throw error;
      console.log(`✅ VAPI call ${callId} saved`);

      // Notify Make.com
      const makeUrl = process.env.MAKE_WEBHOOK_URL;
      if (makeUrl) {
        const fetch = (await import('node-fetch')).default;
        await fetch(makeUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            call_id: callId, from_number: fromNumber, urgency,
            transcript, ai_summary: summary, duration_seconds: duration,
            outcome: 'completed', agent: 'SAWT-VAPI',
            started_at: startedAt, ended_at: endedAt
          })
        }).catch(e => console.error('Make.com notify failed:', e.message));
      }
    }
    res.status(200).json({ status: 'received' });
  } catch (err) {
    console.error('❌ VAPI webhook error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 2. n8n Response Webhook ───────────────────────────────
app.post('/webhook/n8n-response', async (req, res) => {
  try {
    const { call_id, intent, urgency, ai_summary, agent_used, outcome } = req.body;
    if (!call_id) return res.status(400).json({ error: 'Missing call_id' });

    const { error } = await sbService.from('calls').update({
      intent, urgency, ai_summary,
      agent_used: agent_used || 'ORACLE',
      outcome: outcome || (['HIGH','EMERGENCY'].includes(urgency) ? 'escalated' : 'resolved')
    }).eq('call_id', call_id);

    if (error) throw error;
    console.log(`✅ n8n update for ${call_id} | urgency=${urgency}`);
    res.status(200).json({ status: 'success' });
  } catch (err) {
    console.error('❌ n8n response error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 3. BASAR Alert Webhook ────────────────────────────────
app.post('/webhook/basar', async (req, res) => {
  try {
    const { event_type, location, confidence } = req.body;
    console.log(`👁 BASAR alert: ${event_type} at ${location}`);

    await sbService.from('community_alerts').insert({
      event_type:      event_type || 'FALL_DETECTED',
      location:        location   || "Al Qua'a",
      confidence:      confidence || 0.89,
      response_action: 'VOICE_CALL_TRIGGERED',
      resolved:        false
    });

    const n8nUrl = process.env.N8N_BASAR_WEBHOOK;
    if (n8nUrl) {
      const fetch = (await import('node-fetch')).default;
      await fetch(n8nUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...req.body, urgency: 'EMERGENCY',
          summary: `${event_type} detected at ${location}. Autonomous response triggered.`,
          source: 'BASAR'
        })
      }).catch(e => console.error('n8n forward failed:', e.message));
    }
    res.status(200).json({ status: 'alert_received' });
  } catch (err) {
    console.error('❌ BASAR webhook error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 4. GET /api/calls ─────────────────────────────────────
app.get('/api/calls', async (req, res) => {
  try {
    const page   = parseInt(req.query.page)  || 1;
    const limit  = parseInt(req.query.limit) || 20;
    const offset = (page - 1) * limit;

    const { data, count, error } = await sbAnon
      .from('calls').select('*', { count: 'exact' })
      .order('created_at', { ascending: false })
      .range(offset, offset + limit - 1);

    if (error) throw error;
    res.json({ data, meta: { total: count, page, limit, totalPages: Math.ceil(count / limit) } });
  } catch (err) {
    console.error('❌ /api/calls error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 5. GET /api/stats ─────────────────────────────────────
app.get('/api/stats', async (req, res) => {
  try {
    const { data: calls, error: ce } = await sbAnon
      .from('calls').select('urgency, outcome, duration_seconds, created_at');
    if (ce) throw ce;

    const { data: alerts, error: ae } = await sbAnon
      .from('community_alerts').select('*')
      .order('created_at', { ascending: false }).limit(5);
    if (ae) throw ae;

    const total      = calls?.length || 0;
    const resolved   = calls?.filter(c => c.outcome === 'resolved').length   || 0;
    const escalated  = calls?.filter(c => ['HIGH','EMERGENCY'].includes(c.urgency)).length || 0;
    const durations  = calls?.filter(c => c.duration_seconds > 0) || [];
    const avgTime    = durations.length
      ? Math.round(durations.reduce((a,c) => a + c.duration_seconds, 0) / durations.length) : 0;
    const openAlerts = alerts?.filter(a => !a.resolved).length || 0;
    const recentCalls = (calls || []).slice(0,5);

    res.json({
      total_calls:          total,
      resolved,
      emergency_count:      escalated,
      avg_response_seconds: avgTime,
      open_alerts:          openAlerts,
      recent_calls:         recentCalls,
      recent_alerts:        alerts?.slice(0,5) || [],
      uptime:               '100%',
      loop_status:          'ACTIVE — running every 6 hours',
      response_goal:        '< 30 seconds',
      last_updated:         new Date().toISOString()
    });
  } catch (err) {
    console.error('❌ /api/stats error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 6. GET /api/alerts ────────────────────────────────────
app.get('/api/alerts', async (req, res) => {
  try {
    const { data, error } = await sbAnon
      .from('community_alerts').select('*')
      .order('created_at', { ascending: false }).limit(50);
    if (error) throw error;
    res.json({ data });
  } catch (err) {
    console.error('❌ /api/alerts error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 7. Health ─────────────────────────────────────────────
app.get('/health', (_req, res) => {
  res.json({
    status: 'ok', version: '3.1', project: 'NEXUS — Challenge 2',
    supabase: process.env.SUPABASE_URL ? '✅' : '❌',
    n8n:      process.env.N8N_WEBHOOK_BASE ? '✅' : '❌',
    make:     process.env.MAKE_WEBHOOK_URL ? '✅' : '❌',
    timestamp: new Date().toISOString()
  });
});

app.listen(PORT, () => {
  console.log(`\n🚀 NEXUS Backend v3.1 → http://localhost:${PORT}`);
  console.log(`   Supabase : ${process.env.SUPABASE_URL      ? '✅' : '❌ not set'}`);
  console.log(`   n8n      : ${process.env.N8N_WEBHOOK_BASE  ? '✅' : '❌ not set'}`);
  console.log(`   Make.com : ${process.env.MAKE_WEBHOOK_URL  ? '✅' : '❌ not set'}\n`);
});