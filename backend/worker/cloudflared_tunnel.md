# Cloudflare Named Tunnel Runbook for Turbo Worker (`turbo.limo-ai.online`)

This runbook details how to set up, configure, and maintain the Cloudflare Named Tunnel connecting the local heavy Turbo Worker machine to the Render web demo backend at `https://turbo.limo-ai.online`.

---

## Architecture Overview

```
[Client / Browser]
        │
        ▼ (HTTPS)
[Render API Service] (https://api.limo-ai.online, 512MB RAM, Native Python)
        │
        ▼ (Authenticated HTTPS Stream via Cloudflare Tunnel)
[Cloudflare Edge Network] (`turbo.limo-ai.online`)
        │
        ▼ (Encrypted Wire, Inbound Port 0 Opened)
[Local Machine: cloudflared daemon]
        │
        ▼ (Local HTTP `localhost:8005`)
[Turbo Worker Service] (`backend/worker/turbo_worker.py`)
        │
        ▼ (Local Dedicated Artifact Directory)
`worker_artifacts/` (High-CPU / GPU Rendering: FFmpeg, OpenMontage, Prismo)
```

---

## 1. Prerequisites

1. Cloudflare account managing domain `limo-ai.online`.
2. `cloudflared` CLI installed on the local worker machine:
   - **Windows**: `winget install Cloudflare.cloudflared` or `choco install cloudflared`
   - **macOS**: `brew install cloudflared`
   - **Linux**: `sudo apt-get install cloudflared`
3. Turbo Worker Python environment (`backend/.venv` with FastAPI, Uvicorn, FFmpeg installed).

---

## 2. Authentication & Tunnel Creation

Run once on the worker host:

```bash
# 1. Login to Cloudflare
cloudflared tunnel login

# 2. Create the named tunnel 'limo-turbo-worker'
cloudflared tunnel create limo-turbo-worker
```
This generates a tunnel credentials file:
`~/.cloudflared/<tunnel-uuid>.json`.

---

## 3. Tunnel Configuration File

Create or update `~/.cloudflared/config.yml` (or `%USERPROFILE%\.cloudflared\config.yml` on Windows):

```yaml
tunnel: limo-turbo-worker
credentials-file: C:\Users\Admin\.cloudflared\<tunnel-uuid>.json

ingress:
  # Route traffic for turbo.limo-ai.online to local Turbo Worker
  - hostname: turbo.limo-ai.online
    service: http://localhost:8005
    originRequest:
      connectTimeout: 30s
      noTLSVerify: false
  # Catch-all rule (required)
  - service: http_status:404
```

---

## 4. Route DNS to Tunnel

Associate the subdomain with the tunnel:

```bash
cloudflared tunnel route dns limo-turbo-worker turbo.limo-ai.online
```
Cloudflare automatically provisions the CNAME record `turbo.limo-ai.online -> <tunnel-uuid>.cfargotunnel.com` with Cloudflare SSL certificate.

---

## 5. Running the Services

### Terminal 1: Launch Turbo Worker
```bash
# Set environment variables
export WORKER_AUTH_TOKEN="your-secure-shared-worker-token-64-hex"
export WORKER_ARTIFACT_DIR="./worker_artifacts"

# Start Turbo Worker on port 8005
python backend/worker/turbo_worker.py
```

### Terminal 2: Launch Cloudflare Tunnel
```bash
cloudflared tunnel run limo-turbo-worker
```

---

## 6. Verifying Connectivity

### A. Local Health Check
```bash
curl http://localhost:8005/health
# {"status":"online","service":"limo-turbo-worker","engines":{"ffmpeg":true,...}}
```

### B. Public Tunnel Health Check
```bash
curl -i https://turbo.limo-ai.online/health
# HTTP/2 200
# {"status":"online","service":"limo-turbo-worker",...}
```

### C. Authenticated Execute Verification
```bash
curl -X POST https://turbo.limo-ai.online/execute \
  -H "X-Limo-Worker-Key: your-secure-shared-worker-token-64-hex" \
  -H "Content-Type: application/json" \
  -d '{"job_id":"test_job","artifact_id":"art_test_123","deliverable_type":"video"}'
```

---

## 7. Render Production Configuration

In Render Dashboard (`limo-backend` environment variables):
- `TURBO_WORKER_URL`: `https://turbo.limo-ai.online`
- `WORKER_AUTH_TOKEN`: `your-secure-shared-worker-token-64-hex`
- `LIMO_SURFACE`: `web`

Whenever Render backend receives a heavy video/infographic job or a streaming request for a `worker://` artifact, it proxies securely through `https://turbo.limo-ai.online` without overloading Render's 512MB RAM.
