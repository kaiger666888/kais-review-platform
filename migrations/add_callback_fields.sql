-- Migration: Add callback_url and callback_secret to reviews table
-- Date: 2026-05-07
-- Requirements: DB-01, DB-02, DB-04

-- Add columns only if they don't already exist (idempotent)
ALTER TABLE reviews ADD COLUMN callback_url TEXT;
ALTER TABLE reviews ADD COLUMN callback_secret TEXT;
