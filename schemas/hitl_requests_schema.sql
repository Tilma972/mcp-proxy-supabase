-- ============================================================================
-- HITL (Human In The Loop) Requests Table
-- ============================================================================
-- Stores workflow validation requests awaiting human approval via Telegram
-- Used for transparent human validation without exposing new MCP tools

CREATE TABLE IF NOT EXISTS hitl_requests (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Workflow context
    workflow_name TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    original_params JSONB NOT NULL,
    
    -- Validation status
    status TEXT NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'approved', 'rejected', 'timed_out', 'modified')),
    
    -- Human decision
    validated_by TEXT,  -- Telegram user ID or username
    validated_at TIMESTAMPTZ,
    validation_decision JSONB,  -- Stores approval/rejection reason or modifications
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '30 minutes',
    
    -- Telegram message tracking
    telegram_message_id TEXT,
    telegram_chat_id TEXT,
    
    -- Result tracking
    workflow_result JSONB,
    error_details TEXT,
    
    -- Indexes for performance
    CONSTRAINT valid_expiration CHECK (expires_at > created_at)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_requests(status);
CREATE INDEX IF NOT EXISTS idx_hitl_created_at ON hitl_requests(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hitl_workflow ON hitl_requests(workflow_name);
CREATE INDEX IF NOT EXISTS idx_hitl_expires_at ON hitl_requests(expires_at) WHERE status = 'pending';

-- Row Level Security (RLS)
ALTER TABLE hitl_requests ENABLE ROW LEVEL SECURITY;

-- Policy: Service role can do everything (for MCP proxy backend)
CREATE POLICY "Service role full access" ON hitl_requests
    FOR ALL
    USING (auth.role() = 'service_role');

-- Policy: Authenticated users can read their own requests
CREATE POLICY "Users can read own requests" ON hitl_requests
    FOR SELECT
    USING (auth.uid()::text = validated_by);

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to automatically timeout expired pending requests
CREATE OR REPLACE FUNCTION timeout_expired_hitl_requests()
RETURNS INTEGER AS $$
DECLARE
    affected_count INTEGER;
BEGIN
    UPDATE hitl_requests
    SET 
        status = 'timed_out',
        error_details = 'Request expired after 30 minutes without human validation'
    WHERE 
        status = 'pending'
        AND expires_at < NOW();
    
    GET DIAGNOSTICS affected_count = ROW_COUNT;
    RETURN affected_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get pending request by ID
CREATE OR REPLACE FUNCTION get_hitl_request(request_id UUID)
RETURNS TABLE (
    id UUID,
    workflow_name TEXT,
    tool_name TEXT,
    original_params JSONB,
    status TEXT,
    created_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    telegram_message_id TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        hr.id,
        hr.workflow_name,
        hr.tool_name,
        hr.original_params,
        hr.status,
        hr.created_at,
        hr.expires_at,
        hr.telegram_message_id
    FROM hitl_requests hr
    WHERE hr.id = request_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to update request status
CREATE OR REPLACE FUNCTION update_hitl_request_status(
    request_id UUID,
    new_status TEXT,
    validator_id TEXT DEFAULT NULL,
    decision JSONB DEFAULT NULL
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE hitl_requests
    SET 
        status = new_status,
        validated_by = COALESCE(validator_id, validated_by),
        validated_at = CASE WHEN new_status IN ('approved', 'rejected', 'modified') THEN NOW() ELSE validated_at END,
        validation_decision = COALESCE(decision, validation_decision)
    WHERE id = request_id AND status = 'pending';
    
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- Cleanup Job (Optional - can be triggered by external scheduler)
-- ============================================================================

COMMENT ON TABLE hitl_requests IS 'Stores human-in-the-loop validation requests for workflows requiring approval';
COMMENT ON FUNCTION timeout_expired_hitl_requests() IS 'Marks expired pending HITL requests as timed_out';
COMMENT ON FUNCTION get_hitl_request(UUID) IS 'Retrieves a HITL request by ID';
COMMENT ON FUNCTION update_hitl_request_status(UUID, TEXT, TEXT, JSONB) IS 'Updates HITL request status with validation decision';
