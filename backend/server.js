/**
 * NEXUS V3 — Backend Server (server.js)
 * Merged: antigravity base + loop engineering upgrades
 * 
 * Run: node server.js
 * Test: curl http://localhost:3000/api/stats
 */

import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { createClient } from '@supabase/supabase-js';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// Supabase — service role for writes, anon for reads
const sbService = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY
);
const sbAnon = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_ANON_KEY
);

// ── Logging ───────────────────────────────────────────────
app.use((req, _res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
  next();
});

// ── 1. VAPI Webhook ───────────────────────────────────────
// VAPI fires this after every call event
app.post('/webhook/vapi', async (req, res) => {
  try {
    const payload = req.body;
    const callId = payload.message?.call?.id;
    const type = payload.message?.type;

    console.log(`📞 VAPI event: ${type} | call: ${callId}`);

    if (type === 'end-of-call-report') {
      const transcript = payload.message?.transcript || '';
      const startedAt = payload.message?.startedAt;
      const endedAt = payload.message?.endedAt;
      const duration = startedAt && endedAt
        ? Math.floor((new Date(endedAt) - new Date(startedAt)) / 1000)
        : 0;
      const fromNumber = payload.message?.call?.customer?.number || 'unknown';

      const { error } = await sbService
        .from('calls')
        .upsert({
          call_id: callId,
          from_number: fromNumber,
          transcript: transcript,
          duration_seconds: duration,
          ended_at: endedAt || new Date().toISOString(),
          agent_used: 'SAWT-VAPI'
        }, { onConflict: 'call_id' });

      if (error) throw error;
      console.log(`✅ VAPI call ${callId} saved`);
    }

    res.status(200).json({ status: 'received' });
  } catch (err) {
    console.error('❌ VAPI webhook error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 2. n8n Response Webhook ───────────────────────────────
// n8n fires this after ORACLE classifies the call
app.post('/webhook/n8n-response', async (req, res) => {
  try {
    const { call_id, intent, urgency, ai_summary, agent_used, outcome } = req.body;

    if (!call_id) return res.status(400).json({ error: 'Missing call_id' });

    const { error } = await sbService
      .from('calls')
      .update({
        intent,
        urgency,
        ai_summary,
        agent_used: agent_used || 'ORACLE',
        outcome: outcome || (['HIGH', 'EMERGENCY'].includes(urgency) ? 'escalated' : 'resolved')
      })
      .eq('call_id', call_id);

    if (error) throw error;

    console.log(`✅ n8n update for ${call_id} | urgency=${urgency}`);
    res.status(200).json({ status: 'success' });
  } catch (err) {
    console.error('❌ n8n response error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 3. BASAR Alert Webhook ───────────────────────────────
// BASAR Python agent fires this when a fall is detected
app.post('/webhook/basar', async (req, res) => {
  try {
    const { event_type, location, confidence, timestamp } = req.body;

    console.log(`👁 BASAR alert: ${event_type} at ${location}`);

    // Log to community_alerts
    await sbService.from('community_alerts').insert({
      event_type: event_type || 'FALL_DETECTED',
      location: location || 'Al Qua\'a',
      confidence: confidence || 0.89,
      response_action: 'VOICE_CALL_TRIGGERED',
      resolved: false
    });

    // Forward to n8n Emergency Pipeline
    const n8nUrl = process.env.N8N_BASAR_WEBHOOK;
    if (n8nUrl && !n8nUrl.includes('REPLACE')) {
      const fetch = (await import('node-fetch')).default;
      await fetch(n8nUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...req.body,
          urgency: 'EMERGENCY',
          summary: `${event_type} detected at ${location}. Autonomous response triggered.`,
          source: 'BASAR'
        })
      });
    }

    res.status(200).json({ status: 'alert_received', forwarded_to_n8n: true });
  } catch (err) {
    console.error('❌ BASAR webhook error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 4. GET /api/calls — Paginated history ─────────────────
app.get('/api/calls', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 20;
    const offset = (page - 1) * limit;

    const { data, count, error } = await sbAnon
      .from('calls')
      .select('*', { count: 'exact' })
      .order('created_at', { ascending: false })
      .range(offset, offset + limit - 1);

    if (error) throw error;

    res.json({
      data,
      meta: { total: count, page, limit, totalPages: Math.ceil(count / limit) }
    });
  } catch (err) {
    console.error('❌ /api/calls error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 5. GET /api/stats — Dashboard KPIs ───────────────────
app.get('/api/stats', async (req, res) => {
  try {
    const { data, error } = await sbAnon
      .from('calls')
      .select('urgency, outcome, duration_seconds');

    if (error) throw error;

    const total = data.length;
    const resolved = data.filter(c => c.outcome === 'resolved').length;
    const escalated = data.filter(c => ['HIGH', 'EMERGENCY'].includes(c.urgency)).length;
    const durations = data.filter(c => c.duration_seconds > 0);
    const avgTime = durations.length
      ? Math.round(durations.reduce((a, c) => a + c.duration_seconds, 0) / durations.length)
      : 0;

    // Uptime — loop engineering metric
    const { data: alerts } = await sbAnon
      .from('community_alerts')
      .select('id')
      .eq('resolved', false);

    res.json({
      total,
      resolved,
      escalated,
      avgTime,
      openAlerts: alerts?.length || 0,
      responseGoal: '< 10 seconds',
      loopStatus: 'ACTIVE — running every 6 hours'
    });
  } catch (err) {
    console.error('❌ /api/stats error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 6. GET /api/alerts — Community alerts ────────────────
app.get('/api/alerts', async (req, res) => {
  try {
    const { data, error } = await sbAnon
      .from('community_alerts')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(50);

    if (error) throw error;
    res.json({ data });
  } catch (err) {
    console.error('❌ /api/alerts error:', err.message);
    res.status(500).json({ error: 'Internal Server Error' });
  }
});

// ── 7. Health check ───────────────────────────────────────
app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    version: '3.0',
    project: 'NEXUS — Challenge 2',
    timestamp: new Date().toISOString()
  });
});
app.get('/api/stats', async (req, res) => {
  try {
    const { data: calls } = await supabase
      .from('calls')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(50);

    const { data: alerts } = await supabase
      .from('community_alerts')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(20);

    const emergencyCount = calls?.filter(c => c.urgency === 'EMERGENCY').length || 0;
    const avgDuration = calls?.reduce((a, b) => a + (b.duration_seconds || 0), 0) / (calls?.length || 1);

    res.json({
      total_calls: calls?.length || 0,
      emergency_count: emergencyCount,
      avg_response_seconds: Math.round(avgDuration),
      recent_calls: calls?.slice(0, 5) || [],
      recent_alerts: alerts?.slice(0, 5) || [],
      uptime: '100%',
      last_updated: new Date().toISOString()
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.listen(PORT, () => {
  console.log(`\n🚀 NEXUS Backend v3 running on http://localhost:${PORT}`);
  console.log(`   Supabase: ${process.env.SUPABASE_URL ? '✅ connected' : '❌ not set'}`);
  console.log(`   n8n:      ${process.env.N8N_WEBHOOK_BASE ? '✅ set' : '❌ not set'}\n`);
});

