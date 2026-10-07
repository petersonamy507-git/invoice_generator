const tabs = document.querySelectorAll(".tab");
const panels = {
  employees: document.getElementById("panel-employees"),
  bulk: document.getElementById("panel-bulk"),
  templates: document.getElementById("panel-templates"),
};
const errorBox = document.getElementById("error-box");
const successBox = document.getElementById("success-box");

let currentDepartment = "";
let employeesCache = [];
let currentUser = null;

async function ensureAuth() {
  try {
    const res = await fetch("/api/auth/me", { credentials: "include" });
    const data = await res.json();
    if (!data.authenticated) {
      window.location.replace("/login.html");
      return null;
    }
    currentUser = data.user;
    const label = document.getElementById("current-user");
    if (label && currentUser) {
      label.textContent = `${currentUser.username} (${currentUser.role})`;
      label.classList.remove("hidden");
    }
    return currentUser;
  } catch {
    window.location.replace("/login.html");
    return null;
  }
}

function redirectIfUnauthorized(res) {
  if (res.status === 401) {
    window.location.replace("/login.html");
    return true;
  }
  return false;
}

document.getElementById("btn-logout")?.addEventListener("click", async () => {
  try {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
  } finally {
    window.location.replace("/login.html");
  }
});

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    Object.values(panels).forEach((p) => p && p.classList.remove("active"));
    panels[tab.dataset.tab].classList.add("active");
    hideError();
    hideSuccess();
    if (tab.dataset.tab === "templates") loadWordTemplateStatus();
    if (tab.dataset.tab === "bulk") loadCategoryStatus();
  });
});

function showError(message) {
  errorBox.textContent = typeof message === "string" ? message : JSON.stringify(message);
  errorBox.classList.remove("hidden");
  hideSuccess();
}

function hideError() {
  errorBox.classList.add("hidden");
}

function showSuccess(message) {
  successBox.textContent = message;
  successBox.classList.remove("hidden");
}

function hideSuccess() {
  successBox.classList.add("hidden");
}

function detailFromError(err) {
  if (!err) return "Request failed.";
  if (typeof err === "string") return err;
  if (Array.isArray(err)) return err.map((e) => e.msg || JSON.stringify(e)).join("; ");
  return String(err);
}

async function downloadFromResponse(response, fallbackName) {
  if (redirectIfUnauthorized(response)) return;
  if (!response.ok) {
    let detail = "Request failed.";
    try {
      const data = await response.json();
      detail = detailFromError(data.detail) || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match ? match[1] : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

async function apiJson(url, options = {}) {
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (redirectIfUnauthorized(res)) return;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(detailFromError(data.detail) || "Request failed.");
  }
  return data;
}

async function loadWordTemplateStatus() {
  const list = document.getElementById("template-status");
  if (!list) return;
  try {
    const res = await fetch("/api/templates/status", { credentials: "include" });
    if (redirectIfUnauthorized(res)) return;
    const data = await res.json();
    list.innerHTML = "";
    Object.entries(data.templates).forEach(([num, info]) => {
      const li = document.createElement("li");
      li.className = info.exists ? "uploaded" : "";
      li.textContent = `Invoice ${num} (${info.filename}): ${
        info.exists ? "Found" : "Missing"
      }`;
      list.appendChild(li);
    });
  } catch {
    list.innerHTML = "<li>Could not load template status.</li>";
  }
}

/* -------- Excel bulk (legacy) -------- */
const bulkCategoryInput = document.getElementById("bulk-category");
document.querySelectorAll("#category-buttons .category-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#category-buttons .category-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    bulkCategoryInput.value = btn.dataset.category;
    hideError();
  });
});

async function loadCategoryStatus() {
  const list = document.getElementById("category-status");
  if (!list) return;
  try {
    const res = await fetch("/api/categories/status", { credentials: "include" });
    if (redirectIfUnauthorized(res)) return;
    const data = await res.json();
    list.innerHTML = "";
    if (!data.exists) {
      list.innerHTML = `<li>Missing ${data.filename} in Data/excel/</li>`;
      return;
    }
    Object.entries(data.categories).forEach(([, info]) => {
      const li = document.createElement("li");
      li.className = info.ready ? "uploaded" : "";
      li.textContent = `${info.label}: ${info.ready ? `${info.item_count} items` : "Not ready"} — ${info.sheet}`;
      list.appendChild(li);
    });
  } catch {
    list.innerHTML = "<li>Could not load category task sheets.</li>";
  }
}

document.getElementById("bulk-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  hideError();
  const form = e.target;
  if (!bulkCategoryInput.value) {
    showError("Please select a category.");
    return;
  }
  if (!form.current_month.files || !form.current_month.files[0]) {
    showError("Please upload the current month invoice sheet.");
    return;
  }
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  const body = new FormData();
  body.append("category", bulkCategoryInput.value);
  body.append("current_month", form.current_month.files[0]);
  try {
    const response = await fetch("/api/bulk/generate", {
      method: "POST",
      credentials: "include",
      body,
    });
    await downloadFromResponse(response, "invoices.zip");
    showSuccess("Excel bulk invoices downloaded.");
  } catch (err) {
    showError(err.message);
  } finally {
    btn.disabled = false;
  }
});

/* -------- Employees (MySQL) -------- */
const workspace = document.getElementById("employee-workspace");
const tbody = document.getElementById("employee-tbody");
const btnGenerate = document.getElementById("btn-generate");
const newForm = document.getElementById("new-employee-form");
const editForm = document.getElementById("edit-employee-form");

document.querySelectorAll("#dept-buttons .category-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    document.querySelectorAll("#dept-buttons .category-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentDepartment = btn.dataset.department;
    hideError();
    hideSuccess();
    newForm.classList.add("hidden");
    editForm.classList.add("hidden");
    workspace.classList.remove("hidden");
    document.getElementById("ne-department").value = currentDepartment;
    await loadEmployees();
  });
});

async function loadEmployees() {
  if (!currentDepartment) return;
  try {
    const data = await apiJson(`/api/employees?department=${encodeURIComponent(currentDepartment)}`);
    employeesCache = data.employees || [];
    renderEmployees();
  } catch (err) {
    showError(err.message);
  }
}

function renderEmployees() {
  tbody.innerHTML = "";
  if (!employeesCache.length) {
    tbody.innerHTML = `<tr><td colspan="10">No employees in ${currentDepartment}.</td></tr>`;
    btnGenerate.disabled = true;
    return;
  }
  employeesCache.forEach((emp) => {
    const tr = document.createElement("tr");
    tr.dataset.employeeId = emp.employee_id;
    tr.innerHTML = `
      <td><input type="checkbox" class="emp-select" /></td>
      <td>${escapeHtml(emp.employee_id)}</td>
      <td>${escapeHtml(emp.name)}</td>
      <td>${escapeHtml(emp.bank_name)}</td>
      <td>${escapeHtml(emp.iban)}</td>
      <td>${escapeHtml(emp.branch_code || "")}</td>
      <td>
        <input type="text" class="emp-last-invoice" value="${escapeHtml(emp.last_invoice || "")}" placeholder="e.g. HH-007" title="Editable. Generate uses Last Invoice + 1" />
      </td>
      <td><input type="number" class="emp-amount" min="1" step="1" placeholder="Amount" /></td>
      <td>
        <select class="emp-template">
          <option value="1">1 MAXIS</option>
          <option value="2">2 ForestTech</option>
          <option value="3">3 Radnor</option>
          <option value="4">4 AppFounders</option>
          <option value="5">5 Dynamo</option>
          <option value="6">6 Ravotek</option>
          <option value="7">7 Ignitai</option>
          <option value="8">8 Coretechify</option>
          <option value="9">9 Ecomify</option>
          <option value="10">10 CozyHome</option>
          <option value="11">11 Beecodify</option>
          <option value="12">12 Bravix</option>
          <option value="13">13 AlphaDigital</option>
          <option value="14">14 Synergo</option>
        </select>
      </td>
      <td>
        <button type="button" class="btn small btn-edit">Edit</button>
        <button type="button" class="btn small danger btn-delete">Delete</button>
      </td>
    `;
    const checkbox = tr.querySelector(".emp-select");
    checkbox.addEventListener("change", () => {
      tr.classList.toggle("selected", checkbox.checked);
      syncGenerateButton();
    });
    tr.querySelector(".btn-edit").addEventListener("click", () => openEdit(emp));
    tr.querySelector(".btn-delete").addEventListener("click", () => deleteEmployee(emp));
    tbody.appendChild(tr);
  });
  syncGenerateButton();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function syncGenerateButton() {
  const any = !!tbody.querySelector(".emp-select:checked");
  btnGenerate.disabled = !any;
}

document.getElementById("btn-new-employee").addEventListener("click", () => {
  if (!currentDepartment) {
    showError("Select a department first.");
    return;
  }
  editForm.classList.add("hidden");
  newForm.classList.remove("hidden");
  document.getElementById("ne-department").value = currentDepartment;
  ["ne-id", "ne-name", "ne-iban", "ne-bank", "ne-branch", "ne-last-invoice"].forEach((id) => {
    document.getElementById(id).value = "";
  });
});

document.getElementById("ne-cancel").addEventListener("click", () => {
  newForm.classList.add("hidden");
});

document.getElementById("ne-done").addEventListener("click", async () => {
  hideError();
  try {
    await apiJson("/api/employees", {
      method: "POST",
      body: JSON.stringify({
        employee_id: document.getElementById("ne-id").value.trim(),
        name: document.getElementById("ne-name").value.trim(),
        department: document.getElementById("ne-department").value.trim(),
        iban: document.getElementById("ne-iban").value.trim(),
        bank_name: document.getElementById("ne-bank").value.trim(),
        branch_code: document.getElementById("ne-branch").value.trim(),
        last_invoice: document.getElementById("ne-last-invoice").value.trim() || null,
      }),
    });
    newForm.classList.add("hidden");
    showSuccess("Employee created.");
    await loadEmployees();
  } catch (err) {
    showError(err.message);
  }
});

function openEdit(emp) {
  newForm.classList.add("hidden");
  editForm.classList.remove("hidden");
  document.getElementById("ee-id").value = emp.employee_id;
  document.getElementById("ee-name").value = emp.name;
  document.getElementById("ee-department").value = emp.department;
  document.getElementById("ee-iban").value = emp.iban;
  document.getElementById("ee-bank").value = emp.bank_name;
  document.getElementById("ee-branch").value = emp.branch_code || "";
  document.getElementById("ee-last-invoice").value = emp.last_invoice || "";
}

document.getElementById("ee-cancel").addEventListener("click", () => {
  editForm.classList.add("hidden");
});

document.getElementById("ee-save").addEventListener("click", async () => {
  hideError();
  const employeeId = document.getElementById("ee-id").value;
  try {
    await apiJson(`/api/employees/${encodeURIComponent(employeeId)}`, {
      method: "PUT",
      body: JSON.stringify({
        name: document.getElementById("ee-name").value.trim(),
        department: document.getElementById("ee-department").value.trim(),
        iban: document.getElementById("ee-iban").value.trim(),
        bank_name: document.getElementById("ee-bank").value.trim(),
        branch_code: document.getElementById("ee-branch").value.trim(),
        last_invoice: document.getElementById("ee-last-invoice").value.trim() || null,
      }),
    });
    editForm.classList.add("hidden");
    showSuccess("Employee updated.");
    await loadEmployees();
  } catch (err) {
    showError(err.message);
  }
});

async function deleteEmployee(emp) {
  if (!confirm(`Are you sure you want to delete employee ${emp.employee_id}?`)) return;
  hideError();
  try {
    await apiJson(`/api/employees/${encodeURIComponent(emp.employee_id)}`, {
      method: "DELETE",
    });
    showSuccess("Employee deleted.");
    await loadEmployees();
  } catch (err) {
    showError(err.message);
  }
}

btnGenerate.addEventListener("click", async () => {
  hideError();
  const rows = [...tbody.querySelectorAll("tr")].filter(
    (tr) => tr.querySelector(".emp-select")?.checked
  );
  if (!rows.length) {
    showError("Select at least one employee.");
    return;
  }
  const employees = [];
  for (const tr of rows) {
    const employee_id = tr.dataset.employeeId;
    const amount = tr.querySelector(".emp-amount").value;
    const last_invoice = tr.querySelector(".emp-last-invoice").value.trim();
    const invoice_template = Number(tr.querySelector(".emp-template").value);
    if (!amount) {
      showError(`Enter amount for ${employee_id}.`);
      return;
    }
    if (!last_invoice) {
      showError(`Set Last Invoice for ${employee_id} (PDF will use Last Invoice + 1).`);
      return;
    }
    // Backend increments this value for the PDF, then saves it as the new last_invoice.
    employees.push({
      employee_id,
      amount: Number(amount),
      invoice_no: last_invoice,
      invoice_template,
    });
  }
  btnGenerate.disabled = true;
  try {
    const response = await fetch("/api/employees/generate", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ employees }),
    });
    await downloadFromResponse(response, "invoices.zip");
    showSuccess("Invoices generated and downloaded. History saved in MySQL.");
    await loadEmployees();
  } catch (err) {
    showError(err.message);
  } finally {
    syncGenerateButton();
  }
});

ensureAuth().then((user) => {
  if (!user) return;
  loadWordTemplateStatus();
  loadCategoryStatus();
});
