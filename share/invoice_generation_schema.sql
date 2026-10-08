-- =============================================================================
-- Invoice Finance — MySQL schema (share with backend / ops / frontend setup)
-- Database: invoice_generation
-- Safe to re-run: uses CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS
-- =============================================================================
-- Usage (MySQL client):
--   mysql -u root -p < invoice_generation_schema.sql
-- Or in MySQL Workbench: open this file and Execute.
--
-- After schema is applied, start the API once so it can seed the initial admin
-- from .env (INITIAL_ADMIN_USERNAME / EMAIL / PASSWORD).
-- Default admin (if seeded by app): username=admin  password=Admin@12345
-- =============================================================================

CREATE DATABASE IF NOT EXISTS invoice_generation
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE invoice_generation;

-- ---------------------------------------------------------------------------
-- 001_init — employees, clubing, invoice history
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS employees (
  employee_id VARCHAR(64) NOT NULL,
  name VARCHAR(255) NOT NULL,
  department VARCHAR(100) NOT NULL,
  iban VARCHAR(100) NOT NULL,
  bank_name VARCHAR(255) NOT NULL,
  branch_code VARCHAR(100) NULL,
  last_invoice VARCHAR(100) NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (employee_id),
  KEY idx_employees_department (department),
  KEY idx_employees_active_dept (is_active, department)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS clubing (
  s_no INT NOT NULL AUTO_INCREMENT,
  club_id VARCHAR(255) NULL,
  clubs VARCHAR(255) NULL,
  department VARCHAR(200) NULL,
  PRIMARY KEY (s_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Indexes on clubing (uq_clubing_club_id, idx_clubing_department) are also
-- applied automatically when the API starts (Python migrator).

CREATE TABLE IF NOT EXISTS invoice_backup (
  id BIGINT NOT NULL AUTO_INCREMENT,
  employee_id VARCHAR(64) NOT NULL,
  department VARCHAR(100) NOT NULL,
  club_id VARCHAR(255) NOT NULL,
  club_name VARCHAR(255) NULL,
  invoice_template TINYINT NOT NULL,
  sheet_invoice_no VARCHAR(100) NOT NULL,
  document_invoice_no VARCHAR(100) NOT NULL,
  amount INT NOT NULL,
  invoice_date DATE NOT NULL,
  invoice_year SMALLINT NOT NULL,
  invoice_month TINYINT NOT NULL,
  line_items_json TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_club_same_month (club_id, invoice_year, invoice_month),
  KEY idx_backup_employee_date (employee_id, invoice_date),
  KEY idx_backup_department (department),
  KEY idx_backup_year_month (invoice_year, invoice_month),
  KEY idx_backup_club_id (club_id),
  CONSTRAINT fk_backup_employee
    FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 002_users — portal team logins (NOT invoice employees)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
  id BIGINT NOT NULL AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL,
  email VARCHAR(255) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin', 'user') NOT NULL DEFAULT 'user',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  last_login DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_username (username),
  UNIQUE KEY uq_users_email (email),
  KEY idx_users_role (role),
  KEY idx_users_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- 003_auth_sessions — cookie sessions for login
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS auth_sessions (
  id CHAR(64) NOT NULL,
  user_id BIGINT NOT NULL,
  expires_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_sessions_user (user_id),
  KEY idx_sessions_expires (expires_at),
  CONSTRAINT fk_sessions_user
    FOREIGN KEY (user_id) REFERENCES users (id)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================================================
-- Notes for frontend / ops
-- =============================================================================
-- Tables:
--   employees       → invoice people (bank / IBAN / department)
--   clubing         → club line-item pools per department
--   invoice_backup  → generated invoice history
--   users           → portal logins (admin adds team via POST /api/users)
--   auth_sessions   → login cookies (invoice_session)
--
-- Do NOT insert plaintext passwords into users — API hashes with bcrypt.
-- Seed admin by starting the API with INITIAL_ADMIN_* in .env, or use
-- POST /api/users as an existing admin.
-- =============================================================================
