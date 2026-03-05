-- Migration: Create mcp_email_drafts Table
-- Description: Stores temporary email drafts for FlowChat MCP workflow.

CREATE TABLE IF NOT EXISTS public.mcp_email_drafts (
    id UUID PRIMARY KEY,
    payload JSONB NOT NULL,
    expires_at BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index pour la purge rapide
CREATE INDEX IF NOT EXISTS idx_mcp_email_drafts_expires_at ON public.mcp_email_drafts(expires_at);

-- Fonction de purge de l'historique expiré
CREATE OR REPLACE FUNCTION purge_expired_drafts() RETURNS void AS \$$$
BEGIN
  DELETE FROM public.mcp_email_drafts WHERE expires_at < extract(epoch from now());
END;
\$$$ LANGUAGE plpgsql;
