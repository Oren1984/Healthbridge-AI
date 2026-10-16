# Deployment guide (local)

## Requirements

Windows 11 / macOS / Linux with Docker Desktop (Compose v2). ~3 GB disk. Node 22+ only for running E2E tests or
the Vite dev server. No paid services or cloud accounts.

## Ports

| Port (host, `127.0.0.1` only) | Service |
|---|---|
| 8083 | Web app (nginx → SPA + `/api` proxy) |
| 7880 / 7881 TCP, 50000–50060 UDP | LiveKit signalling / ICE TCP / media |

The backend listens on 8003 **inside** the Docker network only; PostgreSQL is not published. Ports 8000–8002 and
8080–8082 are deliberately avoided (used by other projects on the development machine).

## First start

```powershell
Copy-Item .env.example .env
# Edit .env and replace every CHANGE_ME value. Generate the Fernet key with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# LIVEKIT_API_SECRET must be at least 32 characters.
docker compose up -d --build
```

Open <http://localhost:8083>. On first start the backend applies migrations (`alembic upgrade head`) and seeds the
**showcase** scenario if the database is empty (`HB_SEED_ON_START`, `HB_SEED_SCENARIO`).
Health: `http://localhost:8083/api/health`, readiness: `/api/ready`.

## Day-to-day

| Task | Command |
|---|---|
| Stop | `docker compose down` |
| Reset demo data (keep volumes) | Administration → Demo configuration → type `RESET`, or `docker compose exec backend python -m app.services.seed reset showcase` (or `fresh`) |
| Wipe everything | `docker compose down -v` (deletes database, documents and Ollama models) |
| Logs | `docker compose logs -f backend worker` (structured JSON with request IDs) |
| Optional local LLM | `docker compose --profile ollama up -d ollama`, `docker compose exec ollama ollama pull llama3.2:3b`, then switch Administration → Assistant mode to Ollama (or set `HB_AI_MODE=ollama`) |
| Tests | see [testing.md](testing.md) |

## Video beyond this computer

By default LiveKit advertises `127.0.0.1`, so all participants must use browsers on this machine (which is how
the 3-participant test runs). For other devices on the same LAN:

1. Set `LIVEKIT_NODE_IP=<this computer's LAN IP>` and `HB_LIVEKIT_PUBLIC_URL=ws://<LAN IP>:7880`, and
   `LIVEKIT_CSP_SOURCES="ws://<LAN IP>:7880 http://<LAN IP>:7880"`.
2. Change the port bindings in `docker-compose.yml` from `127.0.0.1:` to the LAN interface and allow the ports in
   the firewall (do **not** disable the firewall).
3. Browsers require a secure context for camera/microphone on non-localhost origins → you need HTTPS (step below).

## Internet-accessible deployment (not provided; required additions)

* TLS everywhere: HTTPS for the app, `wss://` for LiveKit (put LiveKit behind a TLS-terminating proxy or use its
  built-in TLS), `HB_COOKIE_SECURE=true`, HSTS.
* TURN: deploy coturn (or enable LiveKit's TURN with TLS on 443/5349) for participants behind symmetric NAT/firewalls.
  Not included because it is not needed for localhost and was not testable here.
* Secrets in a secrets manager; KMS-managed document encryption key with rotation; encrypted database volume.
* Real identity (OIDC with MFA), professional licence verification, distributed rate limiting, WAF, backups,
  monitoring/alerting, log retention policy, and the legal/regulatory work in [privacy-regulatory.md](privacy-regulatory.md).
* Set `HB_ENVIRONMENT=production` (disables OpenAPI docs) and `HB_DEMO_MODE=false` (disables demo credentials,
  self-registration and demo reset).
