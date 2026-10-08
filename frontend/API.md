# Invoice Finance API — backend on one PC, frontend on another

**Setup this project uses:**

| Role | Where it runs | What to share |
|------|----------------|---------------|
| **Backend (API)** | This PC (Invoice_finance + MySQL + Word/LibreOffice) | LAN URL, e.g. `http://10.100.4.15:8000` |
| **Frontend (Vite)** | Another system / another repo | Calls that API URL only — no backend install needed |

Copy this `API.md` to the frontend machine/repo. The frontend never needs the Python project — only the API base URL.

| Who | Base URL to use |
|-----|-----------------|
| Browser / Vite on **this** PC | `http://127.0.0.1:8000` |
| Vite / browser on **another** PC (same LAN) | `http://<THIS-PC-LAN-IP>:8000` (example: `http://10.100.4.15:8000`) |
| Deployed server | `https://api.your-domain.com` |

Interactive Swagger: `{BASE_URL}/docs`  
OpenAPI JSON: `{BASE_URL}/openapi.json`

---

## Frontend env (this repo)

This Vite app uses the **proxy** by default (cookie `SameSite=Lax` safe):

```env
VITE_API_BASE_URL=
VITE_API_PROXY_TARGET=http://10.100.4.15:8000
```

Team logins (`/api/users`) and employee create/edit/delete are **admin-only** in the UI.

See `TEMPLATES.md` for invoice template ids `1`–`14`.
