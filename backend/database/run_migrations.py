#!/usr/bin/env python3
"""
Simple migration runner that executes statements one by one
"""

import os
import boto3
from pathlib import Path
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Get config from environment
cluster_arn = os.environ.get("AURORA_CLUSTER_ARN")
secret_arn = os.environ.get("AURORA_SECRET_ARN")
database = os.environ.get("AURORA_DATABASE", "alex")
region = os.environ.get("DEFAULT_AWS_REGION", "us-east-1")

if not cluster_arn or not secret_arn:
    raise ValueError("Missing AURORA_CLUSTER_ARN or AURORA_SECRET_ARN in environment variables")

client = boto3.client("rds-data", region_name=region)

# Read migration file
with open("migrations/001_schema.sql") as f:
    sql = f.read()

# Define statements in order (since splitting is complex)
statements = [
    # Extension
    'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"',
    # Tables
    """CREATE TABLE IF NOT EXISTS users (
        clerk_user_id VARCHAR(255) PRIMARY KEY,
        display_name VARCHAR(255),
        years_until_retirement INTEGER,
        target_retirement_income DECIMAL(12,2),
        asset_class_targets JSONB DEFAULT '{"equity": 70, "fixed_income": 30}',
        region_targets JSONB DEFAULT '{"north_america": 50, "international": 50}',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS instruments (
        symbol VARCHAR(20) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        instrument_type VARCHAR(50),
        current_price DECIMAL(12,4),
        allocation_regions JSONB DEFAULT '{}',
        allocation_sectors JSONB DEFAULT '{}',
        allocation_asset_class JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS accounts (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        clerk_user_id VARCHAR(255) REFERENCES users(clerk_user_id) ON DELETE CASCADE,
        account_name VARCHAR(255) NOT NULL,
        account_purpose TEXT,
        cash_balance DECIMAL(12,2) DEFAULT 0,
        cash_interest DECIMAL(5,4) DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS positions (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
        symbol VARCHAR(20) REFERENCES instruments(symbol),
        quantity DECIMAL(20,8) NOT NULL,
        as_of_date DATE DEFAULT CURRENT_DATE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(account_id, symbol)
    )""",
    """CREATE TABLE IF NOT EXISTS jobs (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        clerk_user_id VARCHAR(255) REFERENCES users(clerk_user_id) ON DELETE CASCADE,
        job_type VARCHAR(50) NOT NULL,
        status VARCHAR(20) DEFAULT 'pending',
        request_payload JSONB,
        report_payload JSONB,
        charts_payload JSONB,
        retirement_payload JSONB,
        summary_payload JSONB,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        updated_at TIMESTAMP DEFAULT NOW()
    )""",
    # Indexes
    "CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(clerk_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_positions_account ON positions(account_id)",
    "CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(clerk_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
    # Job Tracker
    """CREATE TABLE IF NOT EXISTS job_tracker (
    job_id       UUID PRIMARY KEY REFERENCES jobs(id),
    symbol_count INTEGER      NOT NULL,
    symbols_done INTEGER      NOT NULL DEFAULT 0,
    status       VARCHAR(20)  NOT NULL DEFAULT 'pending',  -- pending|running|done|error
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP    NULL)""",
    """CREATE TABLE IF NOT EXISTS job_tracker_items (
    job_id        UUID        NOT NULL REFERENCES job_tracker(job_id),
    symbol        VARCHAR(20) NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending|running|done|error
    retry_count   INTEGER     NOT NULL DEFAULT 0,
    error_message TEXT,
    last_updated  TIMESTAMP   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job_id, symbol))""",
    """CREATE INDEX IF NOT EXISTS idx_job_tracker_items_job_id ON job_tracker_items (job_id)""",
    """CREATE INDEX IF NOT EXISTS idx_job_tracker_status ON job_tracker (status)""",
    """CREATE INDEX IF NOT EXISTS idx_job_tracker_items_job_symbol ON job_tracker_items (job_id, status)""",
    # Function for timestamps
    """CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""",
    # Triggers
    """CREATE OR REPLACE TRIGGER update_users_updated_at BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",
    """CREATE OR REPLACE TRIGGER update_instruments_updated_at BEFORE UPDATE ON instruments
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",
    """CREATE OR REPLACE TRIGGER update_accounts_updated_at BEFORE UPDATE ON accounts
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",
    """CREATE OR REPLACE TRIGGER update_positions_updated_at BEFORE UPDATE ON positions
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",
    """CREATE OR REPLACE TRIGGER update_jobs_updated_at BEFORE UPDATE ON jobs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()""",

    # Alerts & TODOs
    """CREATE TABLE IF NOT EXISTS alerts (
    alert_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    clerk_user_id VARCHAR(255) NOT NULL,
    job_id        UUID NULL,
    symbol        VARCHAR(20) NULL,

    domain        VARCHAR(20) NOT NULL CHECK (domain IN ('portfolio', 'retirement')),
    category      VARCHAR(50) NOT NULL,
    severity      VARCHAR(20) NOT NULL CHECK (severity IN ('info','warning','critical')),

    title         TEXT NOT NULL,
    message       TEXT NOT NULL,
    rationale     TEXT NULL,

    status        VARCHAR(20) NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new','read','dismissed')),

    created_at    TIMESTAMP DEFAULT NOW(),
    updated_at    TIMESTAMP DEFAULT NOW(),

    CONSTRAINT fk_alert_user FOREIGN KEY (clerk_user_id)
        REFERENCES users(clerk_user_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_alert_job FOREIGN KEY (job_id)
        REFERENCES jobs(id)
        ON DELETE SET NULL
    )""",
    # Table TODOs
    """CREATE TABLE IF NOT EXISTS todos (
    todo_id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    clerk_user_id VARCHAR(255) NOT NULL,
    job_id        UUID NULL,
    symbol        VARCHAR(20) NULL,

    domain        VARCHAR(20) NOT NULL CHECK (domain IN ('portfolio', 'retirement')),

    title         TEXT NOT NULL,
    description   TEXT NOT NULL,
    rationale     TEXT NULL,

    action_type   VARCHAR(50) NOT NULL,
    priority      VARCHAR(20) NOT NULL CHECK (priority IN ('low','medium','high')),

    status        VARCHAR(20) NOT NULL DEFAULT 'open'
                  CHECK (status IN ('open','in_progress','done')),

    due_at        TIMESTAMP NULL,

    created_at    TIMESTAMP DEFAULT NOW(),
    updated_at    TIMESTAMP DEFAULT NOW(),

    CONSTRAINT fk_todo_user FOREIGN KEY (clerk_user_id)
        REFERENCES users(clerk_user_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_todo_job FOREIGN KEY (job_id)
        REFERENCES jobs(id)
        ON DELETE SET NULL
    )""",
    # Indexes Alerts
    """CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(clerk_user_id)""",
    """CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)""",
    """CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON alerts(symbol)""",
    """CREATE INDEX IF NOT EXISTS idx_alerts_domain ON alerts(domain)""",
    """CREATE INDEX IF NOT EXISTS idx_alerts_job ON alerts(job_id)""",
    """CREATE INDEX IF NOT EXISTS idx_alerts_user_status ON alerts(clerk_user_id, status)""",
    """CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity)""",
    # Indexes TODOs
    """CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(clerk_user_id)""",
    """CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status)""",
    """CREATE INDEX IF NOT EXISTS idx_todos_symbol ON todos(symbol)""",
    """CREATE INDEX IF NOT EXISTS idx_todos_domain ON todos(domain)""",
    """CREATE INDEX IF NOT EXISTS idx_todos_job ON todos(job_id)""",
    """CREATE INDEX IF NOT EXISTS idx_todos_user_status ON todos(clerk_user_id, status)""",
    """CREATE INDEX IF NOT EXISTS idx_todos_priority ON todos(priority)""",
    """CREATE INDEX IF NOT EXISTS idx_todos_due ON todos(due_at)""",
    # ALERT EXTENSIONS
    """ALTER TABLE alerts ADD COLUMN IF NOT EXISTS action_required BOOLEAN DEFAULT false""",
    """ALTER TABLE alerts ADD COLUMN IF NOT EXISTS confidence_score INTEGER 
    CHECK (confidence_score BETWEEN 0 AND 100)""",
    """ALTER TABLE alerts ADD COLUMN IF NOT EXISTS action_hint VARCHAR(50)""",
    """ALTER TABLE alerts ADD COLUMN engine_version VARCHAR(20)""",
    """ALTER TABLE alerts ADD COLUMN reasoning JSONB""",
    # TODO LINKING
    """ALTER TABLE todos ADD COLUMN IF NOT EXISTS source_alert_id UUID""",
    """ALTER TABLE todos ADD CONSTRAINT fk_todo_alert 
    FOREIGN KEY (source_alert_id) REFERENCES alerts(alert_id) ON DELETE SET NULL""",
]

print("🚀 Running database migrations...")
print("=" * 50)

success_count = 0
error_count = 0

for i, stmt in enumerate(statements, 1):
    # Get a description of what we're creating
    stmt_type = "statement"
    if "CREATE TABLE" in stmt.upper():
        stmt_type = "table"
    elif "CREATE INDEX" in stmt.upper():
        stmt_type = "index"
    elif "CREATE OR REPLACE TRIGGER" in stmt.upper():
        stmt_type = "trigger"
    elif "CREATE OR REPLACE FUNCTION" in stmt.upper():
        stmt_type = "function"
    elif "CREATE EXTENSION" in stmt.upper():
        stmt_type = "extension"
    elif "ALTER TABLE" in stmt.upper():
        stmt_type = "alter table"
    # First non-empty line for display
    first_line = next(l for l in stmt.split("\n") if l.strip())[:60]
    print(f"\n[{i}/{len(statements)}] Creating {stmt_type}...")
    print(f"    {first_line}...")

    try:
        response = client.execute_statement(
            resourceArn=cluster_arn, secretArn=secret_arn, database=database, sql=stmt
        )
        print(f"    ✅ Success")
        success_count += 1

    except ClientError as e:
        error_msg = e.response["Error"]["Message"]
        if "already exists" in error_msg.lower():
            print(f"    ⚠️  Already exists (skipping)")
            success_count += 1
        else:
            print(f"    ❌ Error: {error_msg[:100]}")
            error_count += 1

print("\n" + "=" * 50)
print(f"Migration complete: {success_count} successful, {error_count} errors")

if error_count == 0:
    print("\n✅ All migrations completed successfully!")
    print("\n📝 Next steps:")
    print("1. Load seed data: uv run seed_data.py")
    print("2. Test database operations: uv run test_db.py")
else:
    print(f"\n⚠️  Some statements failed. Check errors above.")
