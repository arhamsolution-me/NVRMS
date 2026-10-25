-- PostgreSQL initialization script
-- Enable required extensions

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Ensure the database exists (idempotent)
SELECT current_database();
