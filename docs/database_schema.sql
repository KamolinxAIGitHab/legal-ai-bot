-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    full_name VARCHAR(255),
    organization_type VARCHAR(50), -- 'budget', 'corporate'
    language VARCHAR(10) DEFAULT 'uz_lat',
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Procurement logs for analysis history
CREATE TABLE procurement_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    input_data JSONB NOT NULL, -- {amount, category, source_of_funds, etc.}
    analysis_result JSONB NOT NULL, -- {method, law_ref, steps, risks}
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Laws and regulations metadata (Vector data handled separately in Vector DB)
CREATE TABLE laws (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    document_no VARCHAR(100),
    published_date DATE,
    content_text TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Limits and Thresholds (linked to BHM/BCM)
CREATE TABLE procurement_limits (
    id SERIAL PRIMARY KEY,
    customer_type VARCHAR(50), -- 'budget', 'corporate'
    procurement_method VARCHAR(100), -- 'shop', 'auction', 'selection', 'tender'
    min_amount_bhm NUMERIC, -- minimum in multiples of BHM
    max_amount_bhm NUMERIC, -- maximum in multiples of BHM
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Global variables (e.g., current BHM value)
CREATE TABLE settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Initial BHM value for Uzbekistan (as of late 2024 / early 2025: 375,000 UZS)
INSERT INTO settings (key, value) VALUES ('BHM', '375000');
