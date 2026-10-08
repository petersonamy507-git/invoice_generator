# Invoice Finance API — shareable for any client (Vite, curl, etc.)

Copy this file to another machine or repo. Point the client at your API host via `BASE_URL` / `VITE_API_BASE_URL`.

| Environment | Example base URL |
|-------------|------------------|
| Same PC as API | `http://127.0.0.1:8000` |
| Another PC on LAN | `http://192.168.x.x:8000` |
| Deployed | `https://api.your-domain.com` |

Interactive Swagger (when API is up): `{BASE_URL}/docs`  
OpenAPI JSON: `{BASE_URL}/openapi.json`

---

## 1. Run API so other systems can reach it

On the **API host** (project root):

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

- `--host 0.0.0.0` allows LAN access (not only localhost)
- Share `http://<API-LAN-IP>:8000` as the base URL
- Allow port `8000` in the host firewall if needed
- Configure MySQL + `.env` on the API host

Health check:

```bash
curl -s "http://127.0.0.1:8000/api/health"
# {"status":"ok","service":"invoice-generation","version":"1.2.0"}
```

### 1.1 PDF on AWS / Linux (required)

Microsoft Word + `pywin32` work **only on Windows**. On AWS/Linux the API converts DOCX→PDF with **LibreOffice**.

```bash
# Ubuntu / Debian (EC2, etc.)
sudo apt-get update
sudo apt-get install -y libreoffice-writer

# Confirm
which soffice || which libreoffice
soffice --version
```

Optional in API host `.env` if `soffice` is not on `PATH`:

```env
SOFFICE_PATH=/usr/bin/soffice
```

Then restart uvicorn. Without LibreOffice, generate endpoints return:  
`PDF export needs LibreOffice on this server...`

| Host | DOCX fill | PDF |
|------|-----------|-----|
| Windows (dev) | python-docx / Word | Word COM, else LibreOffice |
| AWS Linux | python-docx | LibreOffice headless |

---

## 2. Vite frontend on another system (recommended)

### 2.1 Env

In the Vite project root, create `.env` / `.env.local`:

```env
# Direct calls to API (cross-origin). Must be listed in API CORS_ORIGINS.
VITE_API_BASE_URL=http://127.0.0.1:8000

# Or leave empty and use the Vite proxy below (same-origin /api → backend).
# VITE_API_BASE_URL=
```

### 2.2 Option A — Vite proxy (simplest cookies)

`vite.config.ts` (or `.js`):

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react"; // or vue(), etc.

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
```

Then in the app use a **relative** base (`""` or omit host) so browser calls `http://localhost:5173/api/...` and Vite forwards to the API. Cookies stay same-origin.

### 2.3 Option B — Direct cross-origin

1. Set `VITE_API_BASE_URL=http://<API-HOST>:8000`
2. On the API host `.env`, add your Vite origin to `CORS_ORIGINS`:

```env
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://192.168.1.20:5173
```

3. Restart the API after changing `CORS_ORIGINS`
4. Always use `credentials: "include"` on `fetch` / axios

> Browsers reject `Access-Control-Allow-Origin: *` with cookies. Origins must be listed explicitly.

### 2.4 Shared API client (`src/api/client.ts`)

```ts
const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include", // required: invoice_session cookie
    headers,
  });

  if (res.status === 401) {
    // redirect to your login route
    throw new ApiError(401, "Unauthorized");
  }

  const ct = res.headers.get("content-type") || "";
  if (!res.ok) {
    let detail = res.statusText;
    if (ct.includes("application/json")) {
      const j = await res.json().catch(() => null);
      detail = (j && (j.detail || j.message)) || detail;
    }
    throw new ApiError(res.status, String(detail));
  }

  if (res.status === 204) return undefined as T;
  if (ct.includes("application/json")) return res.json() as Promise<T>;
  return res.blob() as Promise<T>; // ZIP / PDF downloads
}

export const auth = {
  login: (identifier: string, password: string) =>
    api<{ user: User }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    }),
  me: () => api<{ authenticated: boolean; user: User | null }>("/api/auth/me"),
  logout: () => api<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
};

export type User = {
  id: number;
  username: string;
  email: string;
  role: "admin" | "user";
  is_active: boolean;
};
```

### 2.5 Example usage

```ts
import { api, auth } from "./api/client";

await auth.login("admin", "Admin@12345");
const { employees } = await api<{ employees: unknown[] }>("/api/employees?department=QA");

// Download invoice ZIP
const zip = await api<Blob>("/api/employees/generate", {
  method: "POST",
  body: JSON.stringify({
    employees: [
      {
        employee_id: "EMP001",
        amount: 25000,
        invoice_no: "HH-007",
        invoice_template: 11,
      },
    ],
  }),
});
const url = URL.createObjectURL(zip);
const a = document.createElement("a");
a.href = url;
a.download = "invoices.zip";
a.click();
URL.revokeObjectURL(url);
```

| Topic | Rule |
|--------|------|
| Cookies | Always `credentials: "include"` |
| 401 | Send user to login |
| CORS | List Vite origin in API `CORS_ORIGINS` (or use proxy) |
| Binary | Treat non-JSON success as `Blob` (ZIP/PDF) |

---

## 3. Auth (cookie session)

- Cookie name: `invoice_session` (HTTP-only, ~12 hours)
- Roles: `admin` \| `user`
- No session → `401`. Non-admin on admin routes → `403`

Default seeded admin (from API host `.env` on first startup):

| Field | Value |
|-------|--------|
| Username | `admin` |
| Email | `admin@example.com` |
| Password | `Admin@12345` |

### curl (any OS)

```bash
export BASE_URL="http://127.0.0.1:8000"

curl -s -c cookies.txt -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"admin\",\"password\":\"Admin@12345\"}"

curl -s -b cookies.txt "$BASE_URL/api/auth/me"
curl -s -b cookies.txt -c cookies.txt -X POST "$BASE_URL/api/auth/logout"
```

PowerShell: use `$env:BASE_URL` and `curl.exe` the same way.

---

## 4. Endpoint reference

All paths are under `{BASE_URL}`. Auth = cookie required unless noted.

### Public

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/health` | No auth |
| POST | `/api/auth/login` | Body: `{ identifier, password }` → sets cookie |
| POST | `/api/auth/logout` | Clears cookie |
| GET | `/api/auth/me` | `{ authenticated, user }` |

### Users (admin)

| Method | Path | Body |
|--------|------|------|
| GET | `/api/users` | |
| POST | `/api/users` | `{ username, email, password, confirm_password, role, is_active }` |
| PUT | `/api/users/{id}` | `{ username, email, role, is_active }` |
| POST | `/api/users/{id}/password` | `{ password, confirm_password }` |
| DELETE | `/api/users/{id}` | |

### Departments / employees

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/departments` | `QA`, `Devops`, `Call centre`, `Account`, `HR` |
| GET | `/api/employees` | Query: `?department=` |
| GET | `/api/employees/{employee_id}` | |
| POST | `/api/employees` | `{ employee_id, name, department, iban, bank_name, branch_code, last_invoice? }` |
| PUT | `/api/employees/{employee_id}` | Partial update fields |
| DELETE | `/api/employees/{employee_id}` | Hard delete |
| POST | `/api/employees/generate` | See below → **ZIP of PDFs** |

**Generate invoices**

```json
{
  "employees": [
    {
      "employee_id": "EMP001",
      "amount": 25000,
      "invoice_no": "HH-007",
      "invoice_template": 1
    }
  ]
}
```

- Request `invoice_no` = current **last invoice**
- PDF uses **last + 1**, then saves that as new `last_invoice`
- `invoice_template`: `1`–`14`
- Response: `application/zip`

### Clubbing / history / status

| Method | Path | Query |
|--------|------|--------|
| GET | `/api/clubbing` | `department` |
| GET | `/api/invoice-history` | `employee_id`, `department`, `limit` |
| GET | `/api/templates/status` | Word template presence |
| GET | `/api/categories/status` | |

### Legacy / file uploads

| Method | Path | Form fields | Response |
|--------|------|-------------|----------|
| POST | `/api/manual/generate` | `person_name`, `company_name`, `email`, `total_amount`, `invoice_number` | PDF |
| POST | `/api/bulk/generate` | `category`, `current_month` (file) | ZIP |
| POST | `/api/bulk/payment-generate` | `sheet` (file) | ZIP |
| POST | `/api/word-test/generate` | `sheet` (file) | ZIP |

---

## 5. curl cheat sheet

```bash
export BASE_URL="http://127.0.0.1:8000"
# export BASE_URL="http://192.168.1.50:8000"

# Login
curl -s -c cookies.txt -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"admin\",\"password\":\"Admin@12345\"}"

# Employees
curl -s -b cookies.txt "$BASE_URL/api/employees"
curl -s -b cookies.txt "$BASE_URL/api/employees?department=QA"

curl -s -b cookies.txt -X POST "$BASE_URL/api/employees" \
  -H "Content-Type: application/json" \
  -d "{\"employee_id\":\"EMP001\",\"name\":\"Ali Khan\",\"department\":\"QA\",\"iban\":\"PK00XXXX0000000000000000\",\"bank_name\":\"HBL\",\"branch_code\":\"1234\",\"last_invoice\":\"HH-007\"}"

# Generate ZIP
curl -s -b cookies.txt -X POST "$BASE_URL/api/employees/generate" \
  -H "Content-Type: application/json" \
  -o invoices.zip \
  -d "{\"employees\":[{\"employee_id\":\"EMP001\",\"amount\":25000,\"invoice_no\":\"HH-007\",\"invoice_template\":1}]}"

# Clubbing / history
curl -s -b cookies.txt "$BASE_URL/api/clubbing?department=Call%20centre"
curl -s -b cookies.txt "$BASE_URL/api/invoice-history?employee_id=EMP001&limit=50"
```

---

## 6. Checklist for a separate Vite app

1. API running with `--host 0.0.0.0 --port 8000`
2. Copy this `API.md` into the Vite repo (or link to it)
3. Prefer **Vite proxy** `/api` → API (section 2.2), **or** set `VITE_API_BASE_URL` + API `CORS_ORIGINS`
4. Use the `api()` helper with `credentials: "include"`
5. Login once → call `/api/auth/me` on app boot → protect routes on `401`
6. For ZIP/PDF endpoints, download as `Blob`
7. Optional: generate TS types from `{BASE_URL}/openapi.json` (e.g. `openapi-typescript`)
