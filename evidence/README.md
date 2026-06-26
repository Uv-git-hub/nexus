# Evidence Folder

## Response Time Proof
- `n8n_execution_log.png` — shows timestamp from webhook to VAPI call < 10 seconds
- `supabase_rows.png` — shows real call records in database

## Demo Screenshots  
- `whatsapp_triage.png` — Arabic/English WhatsApp reply from HERALD
- `dashboard_live.png` — React dashboard with live Supabase data
- `vapi_call_log.png` — VAPI dashboard showing completed calls

## Demo Video
- `demo_video.mp4` — 2-minute full pipeline demo

## Falsifiable Claims Evidence
1. Response < 10 sec: see n8n_execution_log.png (timestamp diff)
2. Works on any phone: see whatsapp_triage.png (no app needed)
3. Arabic voice: see vapi_call_log.png + audio
4. Zero cost: see cost_breakdown.md
5. Live data: see dashboard_live.png + supabase_rows.png