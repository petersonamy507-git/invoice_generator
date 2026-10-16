-- Run ON the live AWS MySQL host (localhost from the EC2 box), e.g.:
--   mysql -u invoice_user -p invoice_generation < scripts/seed_live_developer.sql
-- Password for login after this: Developer@12345

ALTER TABLE users
  MODIFY role ENUM('admin', 'developer', 'user') NOT NULL DEFAULT 'user';

INSERT INTO users (username, email, password_hash, role, is_active)
SELECT
  'developer',
  'developer@invoice.local',
  '$2b$12$dFU9oYfLzMZCN8GeZ8bZC.2.9co/4dnPpFsqpEgjadlvxRzY25H3y',
  'developer',
  1
WHERE NOT EXISTS (
  SELECT 1 FROM users WHERE username = 'developer' OR email = 'developer@invoice.local'
);

UPDATE users
SET role = 'developer', is_active = 1
WHERE username = 'developer' OR email = 'developer@invoice.local';
