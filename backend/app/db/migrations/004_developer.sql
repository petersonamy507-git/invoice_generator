-- Developer role, audit trail, feature flags, API request logs.

-- Expand users.role to include developer (safe if already applied).
ALTER TABLE users
  MODIFY role ENUM('admin', 'developer', 'user') NOT NULL DEFAULT 'user';

CREATE TABLE IF NOT EXISTS developer_audit_log (
  id BIGINT NOT NULL AUTO_INCREMENT,
  actor_user_id BIGINT NULL,
  actor_username VARCHAR(100) NULL,
  action VARCHAR(64) NOT NULL,
  resource_type VARCHAR(64) NOT NULL,
  resource_id VARCHAR(128) NULL,
  table_name VARCHAR(128) NULL,
  before_json LONGTEXT NULL,
  after_json LONGTEXT NULL,
  meta_json LONGTEXT NULL,
  ip_address VARCHAR(64) NULL,
  user_agent VARCHAR(512) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_dev_audit_created (created_at),
  KEY idx_dev_audit_actor (actor_user_id),
  KEY idx_dev_audit_action (action),
  KEY idx_dev_audit_table (table_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS feature_flags (
  flag_key VARCHAR(100) NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 0,
  value_json TEXT NULL,
  description VARCHAR(500) NULL,
  updated_by BIGINT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (flag_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS api_request_logs (
  id BIGINT NOT NULL AUTO_INCREMENT,
  method VARCHAR(16) NOT NULL,
  path VARCHAR(512) NOT NULL,
  status_code INT NOT NULL,
  duration_ms INT NULL,
  user_id BIGINT NULL,
  username VARCHAR(100) NULL,
  ip_address VARCHAR(64) NULL,
  error_detail VARCHAR(1000) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_api_logs_created (created_at),
  KEY idx_api_logs_status (status_code),
  KEY idx_api_logs_path (path(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO feature_flags (flag_key, enabled, description) VALUES
  ('developer_api_logging', 1, 'Record API request metadata for the Developer Panel'),
  ('developer_panel', 1, 'Enable Developer Panel UI features');
