-- invoice_generation schema initialization
-- Safe to re-run (IF NOT EXISTS / guarded ALTERs applied in Python migrator)

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
