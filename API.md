# Invoice Finance API (shareable)

Use this file on **any machine**. Set `BASE_URL` to wherever the backend is running, then copy the curls as-is.

| Environment | Example `BASE_URL` |
|-------------|--------------------|
| Same PC as server | `http://127.0.0.1:8000` |
| Another PC on LAN | `http://192.168.x.x:8000` |
| Deployed / staging | `https://api.your-domain.com` |

Interactive docs (when server is up): `{BASE_URL}/docs`

---

## 1. Set BASE_URL once

**Bash / macOS / Linux / Git Bash**

```bash
export BASE_URL="http://127.0.0.1:8000"
# export BASE_URL="http://192.168.1.50:8000"   # other system on LAN
```

**Windows PowerShell**

```powershell
$env:BASE_URL = "http://127.0.0.1:8000"
# $env:BASE_URL = "http://192.168.1.50:8000"
```

**Quick connectivity check**

```bash
curl -s "$BASE_URL/api/health"
```

```powershell
curl.exe -s "$env:BASE_URL/api/health"
```

Expected: `{"status":"ok","service":"invoice-generation","version":"1.2.0"}`

---

## 2. Auth (cookie session)

- Cookie name: `invoice_session` (HTTP-only, ~12 hours)
- After login, send the cookie on every call (`-c` / `-b` in curl, or `credentials: "include"` in browser)
- Roles: `admin` | `user`
- No session → `401`. Non-admin on admin routes → `403`

Default seeded admin (first startup from server `.env`):

| Field | Value |
|-------|--------|
| Username | `admin` |
| Email | `admin@example.com` |
| Password | `Admin@12345` |

### Login (save cookie jar)

```bash
curl -s -c cookies.txt -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"identifier\":\"admin\",\"password\":\"Admin@12345\"}"
```

```powershell
curl.exe -s -c cookies.txt -X POST "$env:BASE_URL/api/auth/login" `
  -H "Content-Type: application/json" `
  -d "{\"identifier\":\"admin\",\"password\":\"Admin@12345\"}"
```

`identifier` = username **or** email. Response includes `user`; sets `invoice_session`.

### Me / Logout

```bash
curl -s -b cookies.txt "$BASE_URL/api/auth/me"
curl -s -b cookies.txt -c cookies.txt -X POST "$BASE_URL/api/auth/logout"
```

```powershell
curl.exe -s -b cookies.txt "$env:BASE_URL/api/auth/me"
curl.exe -s -b cookies.txt -c cookies.txt -X POST "$env:BASE_URL/api/auth/logout"
```

---

## 3. Users (admin only)

```bash
# List
curl -s -b cookies.txt "$BASE_URL/api/users"

# Create
curl -s -b cookies.txt -X POST "$BASE_URL/api/users" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"jane\",\"email\":\"jane@example.com\",\"password\":\"UserPass123\",\"confirm_password\":\"UserPass123\",\"role\":\"user\",\"is_active\":true}"

# Update
curl -s -b cookies.txt -X PUT "$BASE_URL/api/users/2" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"jane\",\"email\":\"jane@example.com\",\"role\":\"user\",\"is_active\":true}"

# Reset password
curl -s -b cookies.txt -X POST "$BASE_URL/api/users/2/password" \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"NewPass123\",\"confirm_password\":\"NewPass123\"}"

# Delete
curl -s -b cookies.txt -X DELETE "$BASE_URL/api/users/2"
```

---

## 4. Departments

```bash
curl -s -b cookies.txt "$BASE_URL/api/departments"
```

Values: `QA`, `Devops`, `Call centre`, `Account`, `HR`.

---

## 5. Employees

```bash
# List / filter
curl -s -b cookies.txt "$BASE_URL/api/employees"
curl -s -b cookies.txt "$BASE_URL/api/employees?department=QA"

# Get one
curl -s -b cookies.txt "$BASE_URL/api/employees/EMP001"

# Create
curl -s -b cookies.txt -X POST "$BASE_URL/api/employees" \
  -H "Content-Type: application/json" \
  -d "{\"employee_id\":\"EMP001\",\"name\":\"Ali Khan\",\"department\":\"QA\",\"iban\":\"PK00XXXX0000000000000000\",\"bank_name\":\"HBL\",\"branch_code\":\"1234\",\"last_invoice\":\"HH-007\"}"

# Update
curl -s -b cookies.txt -X PUT "$BASE_URL/api/employees/EMP001" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Ali Khan\",\"iban\":\"PK00XXXX0000000000000000\",\"bank_name\":\"HBL\",\"branch_code\":\"1234\",\"last_invoice\":\"HH-008\"}"

# Delete (hard delete)
curl -s -b cookies.txt -X DELETE "$BASE_URL/api/employees/EMP001"
```

### Generate invoices (ZIP of PDFs)

- Request `invoice_no` = current **last invoice**
- PDF uses **last + 1**, then saves that as new `last_invoice`
- `invoice_template`: `1`–`14`

```bash
curl -s -b cookies.txt -X POST "$BASE_URL/api/employees/generate" \
  -H "Content-Type: application/json" \
  -o invoices.zip \
  -d "{\"employees\":[{\"employee_id\":\"EMP001\",\"amount\":25000,\"invoice_no\":\"HH-007\",\"invoice_template\":1}]}"
```

---

## 6. Clubbing / history / status

```bash
curl -s -b cookies.txt "$BASE_URL/api/clubbing"
curl -s -b cookies.txt "$BASE_URL/api/clubbing?department=Call%20centre"

curl -s -b cookies.txt "$BASE_URL/api/invoice-history"
curl -s -b cookies.txt "$BASE_URL/api/invoice-history?employee_id=EMP001&limit=50"
curl -s -b cookies.txt "$BASE_URL/api/invoice-history?department=QA&limit=100"

curl -s -b cookies.txt "$BASE_URL/api/templates/status"
curl -s -b cookies.txt "$BASE_URL/api/categories/status"
```

---

## 7. Legacy / other generation

Paths below are on **the machine running curl** (upload file from that PC).

```bash
# Manual PDF
curl -s -b cookies.txt -X POST "$BASE_URL/api/manual/generate" \
  -F "person_name=Ali Khan" \
  -F "company_name=Acme Corp" \
  -F "email=ali@example.com" \
  -F "total_amount=15000" \
  -F "invoice_number=1001" \
  -o invoice.pdf

# Excel bulk ZIP
curl -s -b cookies.txt -X POST "$BASE_URL/api/bulk/generate" \
  -F "category=QA" \
  -F "current_month=@./current_month.xlsx" \
  -o invoices.zip

# Payment sheet ZIP
curl -s -b cookies.txt -X POST "$BASE_URL/api/bulk/payment-generate" \
  -F "sheet=@./payment_sheet.xlsx" \
  -o payment_invoices.zip

# Word test ZIP
curl -s -b cookies.txt -X POST "$BASE_URL/api/word-test/generate" \
  -F "sheet=@./sheet.xlsx" \
  -o word_invoices.zip
```

---

## 8. Frontend on another system

```js
const BASE_URL = "http://192.168.1.50:8000"; // change per environment

// Login
await fetch(`${BASE_URL}/api/auth/login`, {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ identifier: "admin", password: "Admin@12345" }),
});

// Any protected call
await fetch(`${BASE_URL}/api/employees?department=QA`, {
  credentials: "include",
});
```

| Topic | Rule |
|--------|------|
| Cookies | Always `credentials: "include"` |
| 401 | Send user to login |
| Cross-origin FE | Cookie auth needs matching CORS origins (not `*`) + server reachable from that machine |
| Same host | Open `{BASE_URL}/` or `{BASE_URL}/login.html` |

---

## 9. Run server so other systems can reach it

On the **API host**:

```bash
# from project root
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

- `--host 0.0.0.0` allows LAN access (not only localhost)
- Share `http://<this-machine-LAN-IP>:8000` as `BASE_URL`
- Allow port `8000` in the host firewall if needed
- MySQL + `.env` must be configured on the API host

Swagger: `http://<host>:8000/docs`
