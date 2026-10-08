import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.app.auth_deps import OptionalUser, RequireAdmin, RequireUser
from backend.app.db import run_migrations
from backend.app.db.clubing_repo import list_clubs
from backend.app.db.employees_repo import (
    VALID_DEPARTMENTS,
    create_employee,
    delete_employee,
    get_employee,
    list_employees,
    update_employee,
)
from backend.app.db.invoice_backup_repo import list_invoice_history
from backend.app.db.sessions_repo import SESSION_TTL_HOURS, delete_session
from backend.app.db.users_repo import (
    create_user,
    delete_user,
    list_users,
    set_user_password,
    update_user,
)
from backend.app.services.auth_service import (
    SESSION_COOKIE,
    authenticate_login,
    ensure_initial_admin,
)
from backend.app.services.category_tasks import categories_status
from backend.app.services.employee_invoice_generate import generate_invoices_for_employees
from backend.app.services.excel_parser import generate_bulk_invoices
from backend.app.services.html_templates import HTML_DIR
from backend.app.services.payment_sheet_processor import build_payment_sheet_zip
from backend.app.services.validation import ValidationError
from backend.app.services.word_invoice_generator import (
    generate_word_invoice,
    parse_manual_word_invoice,
)
from backend.app.services.word_templates import (
    INVOICE_TEMPLATE_LABELS,
    INVOICE_WORD_MAP,
    WORD_DIR,
    template_filename,
    template_path,
)
from backend.app.services.word_test_processor import build_word_test_zip
from backend.app.services.word_to_pdf import convert_docx_batch_to_pdf
from backend.app.services.zip_export import build_zip

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title="Invoice Generation System",
    version="1.2.0",
    description="Employees, club assignment, Word/PDF invoice generation, and auth.",
)

# Cookie auth requires explicit origins (not *). Comma-separated in CORS_ORIGINS.
_cors_raw = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000",
)
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.on_event("startup")
def _startup() -> None:
    try:
        run_migrations()
        ensure_initial_admin()
    except ValidationError as e:
        print(f"[startup] warning: {e}")
    except Exception as e:  # pragma: no cover - surface DB/config issues
        print(f"[startup] warning: {e}")


# ---------- models ----------


class EmployeeCreate(BaseModel):
    employee_id: str
    name: str
    department: str
    iban: str
    bank_name: str
    branch_code: str = ""
    last_invoice: str | None = None


class EmployeeUpdate(BaseModel):
    name: str | None = None
    department: str | None = None
    iban: str | None = None
    bank_name: str | None = None
    branch_code: str | None = None
    last_invoice: str | None = None


class EmployeeGenerateItem(BaseModel):
    employee_id: str
    amount: float
    invoice_no: str
    invoice_template: int = Field(..., ge=1, le=14)


class EmployeeGenerateRequest(BaseModel):
    employees: list[EmployeeGenerateItem]


class LoginRequest(BaseModel):
    identifier: str
    password: str


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    confirm_password: str
    role: str = "user"
    is_active: bool = True


class UserUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    role: str | None = None
    is_active: bool | None = None


class PasswordResetRequest(BaseModel):
    password: str
    confirm_password: str


def _http_error(exc: ValidationError, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_HOURS * 3600,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")


# ---------- public ----------


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "invoice-generation", "version": "1.2.0"}


@app.get("/")
async def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "Invoice API is running. Place frontend in /frontend."}


@app.get("/login.html")
async def login_page():
    page = FRONTEND_DIR / "login.html"
    if page.exists():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="login.html not found")


# ---------- auth ----------


@app.post("/api/auth/login")
async def auth_login(body: LoginRequest, request: Request):
    try:
        client = request.client.host if request.client else "unknown"
        user, session_id = authenticate_login(
            body.identifier,
            body.password,
            client_key=f"{client}:{body.identifier.strip().lower()}",
        )
    except ValidationError as e:
        raise _http_error(e) from e
    response = JSONResponse({"user": user})
    _set_session_cookie(response, session_id)
    return response


@app.post("/api/auth/logout")
async def auth_logout(response: Response, request: Request, _user: OptionalUser):
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        delete_session(session_id)
    _clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(user: OptionalUser):
    if not user:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": user}


# ---------- admin users ----------


@app.get("/api/users")
async def users_list(_admin: RequireAdmin):
    return {"users": list_users()}


@app.post("/api/users")
async def users_create(body: UserCreate, _admin: RequireAdmin):
    if body.password != body.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    try:
        return create_user(
            username=body.username,
            email=body.email,
            password=body.password,
            role=body.role,
            is_active=body.is_active,
        )
    except ValidationError as e:
        raise _http_error(e) from e


@app.put("/api/users/{user_id}")
async def users_update(user_id: int, body: UserUpdate, _admin: RequireAdmin):
    try:
        payload = {k: v for k, v in body.model_dump().items() if v is not None}
        return update_user(user_id, payload)
    except ValidationError as e:
        raise _http_error(e) from e


@app.post("/api/users/{user_id}/password")
async def users_set_password(
    user_id: int, body: PasswordResetRequest, _admin: RequireAdmin
):
    if body.password != body.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")
    try:
        set_user_password(user_id, body.password)
        return {"id": user_id, "password_updated": True}
    except ValidationError as e:
        raise _http_error(e) from e


@app.delete("/api/users/{user_id}")
async def users_delete(user_id: int, _admin: RequireAdmin):
    try:
        return delete_user(user_id)
    except ValidationError as e:
        raise _http_error(e) from e


# ---------- departments / employees ----------


@app.get("/api/departments")
async def departments(_user: RequireUser):
    return {"departments": list(VALID_DEPARTMENTS)}


@app.get("/api/employees")
async def employees_list(_user: RequireUser, department: str | None = None):
    try:
        return {"employees": list_employees(department)}
    except ValidationError as e:
        raise _http_error(e) from e


@app.get("/api/employees/{employee_id}")
async def employees_get(_user: RequireUser, employee_id: str):
    try:
        return get_employee(employee_id)
    except ValidationError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.post("/api/employees")
async def employees_create(_user: RequireUser, body: EmployeeCreate):
    try:
        return create_employee(body.model_dump())
    except ValidationError as e:
        raise _http_error(e) from e


@app.put("/api/employees/{employee_id}")
async def employees_update(
    _user: RequireUser, employee_id: str, body: EmployeeUpdate
):
    try:
        payload = {
            k: v
            for k, v in body.model_dump().items()
            if v is not None or k == "last_invoice"
        }
        return update_employee(employee_id, payload)
    except ValidationError as e:
        raise _http_error(e) from e


@app.delete("/api/employees/{employee_id}")
async def employees_delete(_user: RequireUser, employee_id: str):
    try:
        return delete_employee(employee_id)
    except ValidationError as e:
        raise _http_error(e) from e


@app.post("/api/employees/generate")
async def employees_generate(_user: RequireUser, body: EmployeeGenerateRequest):
    try:
        zip_bytes = generate_invoices_for_employees(
            [item.model_dump() for item in body.employees]
        )
        zip_name = f"invoices_{date.today().strftime('%Y-%m-%d')}.zip"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
        )
    except ValidationError as e:
        raise _http_error(e) from e


# ---------- clubs / history / templates ----------


@app.get("/api/clubbing")
async def clubbing_list(_user: RequireUser, department: str | None = None):
    try:
        return {"clubs": list_clubs(department)}
    except ValidationError as e:
        raise _http_error(e) from e


@app.get("/api/invoice-history")
async def invoice_history(
    _user: RequireUser,
    employee_id: str | None = None,
    department: str | None = None,
    limit: int = 100,
):
    try:
        return {
            "history": list_invoice_history(
                employee_id=employee_id, department=department, limit=limit
            )
        }
    except ValidationError as e:
        raise _http_error(e) from e


@app.get("/api/templates/status")
async def word_templates_status(_user: RequireUser):
    return {
        "word_dir": str(WORD_DIR),
        "preview_dir": str(HTML_DIR),
        "templates": {
            str(n): {
                "id": n,
                "label": INVOICE_TEMPLATE_LABELS.get(n, INVOICE_WORD_MAP[n]),
                "name": INVOICE_WORD_MAP[n],
                "filename": template_filename(n),
                "exists": template_path(n).is_file(),
            }
            for n in INVOICE_WORD_MAP
        },
    }


@app.get("/api/categories/status")
async def category_tasks_status(_user: RequireUser):
    return categories_status()


# ---------- legacy / other generate paths ----------


@app.post("/api/manual/generate")
async def manual_generate(
    _user: RequireUser,
    person_name: str = Form(...),
    company_name: str = Form(...),
    email: str = Form(...),
    total_amount: float = Form(...),
    invoice_number: int = Form(...),
):
    try:
        data = parse_manual_word_invoice(
            person_name=person_name,
            company_name=company_name,
            email=email,
            total_amount=total_amount,
            invoice_number=invoice_number,
        )
        docx_bytes, filename = generate_word_invoice(data)
        pdf_bytes, pdf_filename = convert_docx_batch_to_pdf([(docx_bytes, filename)])[0]
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{pdf_filename}"'},
        )
    except ValidationError as e:
        raise _http_error(e) from e


@app.post("/api/bulk/generate")
async def bulk_generate(
    _user: RequireUser,
    category: str = Form(...),
    current_month: UploadFile = File(...),
):
    try:
        current_bytes = await current_month.read()
        result = generate_bulk_invoices(current_bytes, category)
        zip_bytes = build_zip(
            result.invoices,
            updated_history_bytes=result.updated_history_bytes,
            updated_history_filename=result.updated_history_filename,
            last_three_months_history_bytes=result.last_three_months_history_bytes,
            last_three_months_history_filename=result.last_three_months_history_filename,
        )
        zip_name = f"invoices_{date.today().strftime('%Y-%m-%d')}.zip"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
        )
    except ValidationError as e:
        raise _http_error(e) from e


@app.post("/api/bulk/payment-generate")
async def payment_bulk_generate(_user: RequireUser, sheet: UploadFile = File(...)):
    try:
        content = await sheet.read()
        zip_bytes, _files = build_payment_sheet_zip(content)
        zip_name = f"payment_invoices_{date.today().strftime('%Y-%m-%d')}.zip"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
        )
    except ValidationError as e:
        raise _http_error(e) from e


@app.post("/api/word-test/generate")
async def word_test_generate(_user: RequireUser, sheet: UploadFile = File(...)):
    try:
        content = await sheet.read()
        zip_bytes, _files = build_word_test_zip(content)
        zip_name = f"word_invoices_{date.today().strftime('%Y-%m-%d')}.zip"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
        )
    except ValidationError as e:
        raise _http_error(e) from e
