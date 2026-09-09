-- ─────────────────────────────────────────────────────────────────────────
-- Digital Overtime Management System — schema
-- Target: the main `ckdo_dashboard` PostgreSQL database.
--
-- Why this file exists: Base.metadata.create_all() only runs when
-- ENVIRONMENT=development (see app/main.py's lifespan), so on the dev and
-- production servers these tables have to be created explicitly. Every
-- statement is idempotent — re-running it is safe and changes nothing.
--
--   docker compose exec -T postgres psql -U <user> -d ckdo_dashboard --       < backend/scripts/overtime_schema.sql
--
-- Source of truth is app/models/overtime.py; this DDL was generated from it.
-- If a column is added there, add it here too (create_all does NOT ALTER an
-- existing table — it silently skips it).
-- ─────────────────────────────────────────────────────────────────────────

BEGIN;

CREATE TABLE IF NOT EXISTS overtime_approval_matrix (
	id SERIAL NOT NULL, 
	employee_id VARCHAR(20) NOT NULL, 
	employee_name VARCHAR(200), 
	department VARCHAR(100), 
	team VARCHAR(100), 
	role_level VARCHAR(20) NOT NULL, 
	team_head_id VARCHAR(20), 
	dept_head_id VARCHAR(20), 
	is_active BOOLEAN NOT NULL, 
	updated_by VARCHAR(200), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_overtime_approval_matrix_role_level ON overtime_approval_matrix (role_level);
CREATE UNIQUE INDEX IF NOT EXISTS ix_overtime_approval_matrix_employee_id ON overtime_approval_matrix (employee_id);
CREATE INDEX IF NOT EXISTS ix_overtime_approval_matrix_dept_head_id ON overtime_approval_matrix (dept_head_id);
CREATE INDEX IF NOT EXISTS ix_overtime_approval_matrix_team ON overtime_approval_matrix (team);
CREATE INDEX IF NOT EXISTS ix_overtime_approval_matrix_team_head_id ON overtime_approval_matrix (team_head_id);
CREATE INDEX IF NOT EXISTS ix_overtime_approval_matrix_department ON overtime_approval_matrix (department);

CREATE TABLE IF NOT EXISTS overtime_cutoff_config (
	id SERIAL NOT NULL, 
	name VARCHAR(100), 
	start_day INTEGER NOT NULL, 
	end_day INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	updated_by VARCHAR(200), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS overtime_notification_settings (
	id SERIAL NOT NULL, 
	event_key VARCHAR(50) NOT NULL, 
	label VARCHAR(200), 
	in_app BOOLEAN NOT NULL, 
	email BOOLEAN NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	updated_by VARCHAR(200), 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_overtime_notification_settings_event_key ON overtime_notification_settings (event_key);

CREATE TABLE IF NOT EXISTS overtime_notifications (
	id SERIAL NOT NULL, 
	recipient_email VARCHAR(200) NOT NULL, 
	recipient_id VARCHAR(20), 
	event_key VARCHAR(50), 
	title VARCHAR(300) NOT NULL, 
	body TEXT, 
	request_id INTEGER, 
	request_no VARCHAR(30), 
	is_read BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_overtime_notifications_recipient_email ON overtime_notifications (recipient_email);
CREATE INDEX IF NOT EXISTS ix_overtime_notifications_request_id ON overtime_notifications (request_id);
CREATE INDEX IF NOT EXISTS ix_overtime_notifications_recipient_id ON overtime_notifications (recipient_id);
CREATE INDEX IF NOT EXISTS ix_overtime_notifications_created_at ON overtime_notifications (created_at);
CREATE INDEX IF NOT EXISTS ix_overtime_notifications_event_key ON overtime_notifications (event_key);
CREATE INDEX IF NOT EXISTS ix_overtime_notifications_is_read ON overtime_notifications (is_read);

CREATE TABLE IF NOT EXISTS overtime_rate_config (
	id SERIAL NOT NULL, 
	grade VARCHAR(50) NOT NULL, 
	hourly_rate NUMERIC(14, 2) NOT NULL, 
	updated_by VARCHAR(200), 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_overtime_rate_config_grade ON overtime_rate_config (grade);

CREATE TABLE IF NOT EXISTS overtime_requests (
	id SERIAL NOT NULL, 
	request_no VARCHAR(30) NOT NULL, 
	employee_id VARCHAR(20) NOT NULL, 
	employee_name VARCHAR(200), 
	employee_email VARCHAR(200), 
	department VARCHAR(100), 
	division VARCHAR(100), 
	team VARCHAR(100), 
	overtime_type VARCHAR(20) NOT NULL, 
	work_category VARCHAR(20), 
	task_description TEXT NOT NULL, 
	ot_date DATE NOT NULL, 
	work_start VARCHAR(5), 
	work_finish VARCHAR(5), 
	plan_start VARCHAR(5), 
	plan_finish VARCHAR(5), 
	planned_minutes INTEGER, 
	plan_status VARCHAR(20) NOT NULL, 
	plan_submitted_at TIMESTAMP WITHOUT TIME ZONE, 
	th_approver_id VARCHAR(20), 
	th_approver_name VARCHAR(200), 
	th_decision VARCHAR(20), 
	th_decision_at TIMESTAMP WITHOUT TIME ZONE, 
	th_note TEXT, 
	dh_approver_id VARCHAR(20), 
	dh_approver_name VARCHAR(200), 
	dh_decision VARCHAR(20), 
	dh_decision_at TIMESTAMP WITHOUT TIME ZONE, 
	dh_note TEXT, 
	rz_status VARCHAR(20) NOT NULL, 
	actual_start VARCHAR(5), 
	actual_finish VARCHAR(5), 
	actual_minutes INTEGER, 
	gap_minutes INTEGER, 
	gap_reason TEXT, 
	rz_submitted_at TIMESTAMP WITHOUT TIME ZONE, 
	rz_th_approver_id VARCHAR(20), 
	rz_th_approver_name VARCHAR(200), 
	rz_th_decision VARCHAR(20), 
	rz_th_decision_at TIMESTAMP WITHOUT TIME ZONE, 
	rz_th_note TEXT, 
	rz_dh_approver_id VARCHAR(20), 
	rz_dh_approver_name VARCHAR(200), 
	rz_dh_decision VARCHAR(20), 
	rz_dh_decision_at TIMESTAMP WITHOUT TIME ZONE, 
	rz_dh_note TEXT, 
	hr_approver_id VARCHAR(20), 
	hr_approver_name VARCHAR(200), 
	hr_decision VARCHAR(20), 
	hr_decision_at TIMESTAMP WITHOUT TIME ZONE, 
	hr_note TEXT, 
	payable_minutes INTEGER, 
	overtime_index NUMERIC(10, 2), 
	hourly_rate NUMERIC(14, 2), 
	estimated_cost NUMERIC(16, 2), 
	cancelled_at TIMESTAMP WITHOUT TIME ZONE, 
	cancel_reason TEXT, 
	created_by VARCHAR(200), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_overtime_requests_plan_status ON overtime_requests (plan_status);
CREATE INDEX IF NOT EXISTS ix_overtime_requests_employee_id ON overtime_requests (employee_id);
CREATE INDEX IF NOT EXISTS ix_overtime_requests_team ON overtime_requests (team);
CREATE UNIQUE INDEX IF NOT EXISTS ix_overtime_requests_request_no ON overtime_requests (request_no);
CREATE INDEX IF NOT EXISTS ix_overtime_requests_ot_date ON overtime_requests (ot_date);
CREATE INDEX IF NOT EXISTS ix_overtime_requests_department ON overtime_requests (department);
CREATE INDEX IF NOT EXISTS ix_overtime_requests_employee_email ON overtime_requests (employee_email);
CREATE INDEX IF NOT EXISTS ix_overtime_requests_rz_status ON overtime_requests (rz_status);
CREATE INDEX IF NOT EXISTS ix_overtime_requests_overtime_type ON overtime_requests (overtime_type);

CREATE TABLE IF NOT EXISTS overtime_rules (
	id SERIAL NOT NULL, 
	seq INTEGER, 
	title VARCHAR(300) NOT NULL, 
	content TEXT, 
	is_active BOOLEAN NOT NULL, 
	updated_by VARCHAR(200), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS overtime_approval_logs (
	id SERIAL NOT NULL, 
	request_id INTEGER NOT NULL, 
	stage VARCHAR(20) NOT NULL, 
	action VARCHAR(30) NOT NULL, 
	actor_id VARCHAR(20), 
	actor_name VARCHAR(200), 
	actor_email VARCHAR(200), 
	actor_role VARCHAR(20), 
	note TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_id) REFERENCES overtime_requests (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_overtime_approval_logs_request_id ON overtime_approval_logs (request_id);

CREATE TABLE IF NOT EXISTS overtime_attachments (
	id SERIAL NOT NULL, 
	request_id INTEGER NOT NULL, 
	original_name VARCHAR(300) NOT NULL, 
	stored_name VARCHAR(300) NOT NULL, 
	content_type VARCHAR(120), 
	size_bytes INTEGER, 
	uploaded_by VARCHAR(200), 
	uploaded_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(request_id) REFERENCES overtime_requests (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_overtime_attachments_request_id ON overtime_attachments (request_id);

CREATE TABLE IF NOT EXISTS overtime_hour_details (
	id SERIAL NOT NULL, 
	request_id INTEGER NOT NULL, 
	hour_no INTEGER NOT NULL, 
	detail TEXT, 
	start_time VARCHAR(5), 
	finish_time VARCHAR(5), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_ot_hour_detail UNIQUE (request_id, hour_no), 
	FOREIGN KEY(request_id) REFERENCES overtime_requests (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_overtime_hour_details_request_id ON overtime_hour_details (request_id);

-- ── Seed rows the application would otherwise create on first use ────────
-- Cut-off window: the 11th of one month to the 10th of the next.
INSERT INTO overtime_cutoff_config (name, start_day, end_day, is_active, updated_by, created_at, updated_at)
SELECT 'Default', 11, 10, TRUE, 'system', NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM overtime_cutoff_config WHERE is_active);

-- Notification events (site map D.5). in_app on, email off — no mail sender
-- is wired up yet.
INSERT INTO overtime_notification_settings (event_key, label, in_app, email, is_active, updated_by, updated_at)
SELECT v.event_key, v.label, TRUE, FALSE, TRUE, 'system', NOW()
FROM (VALUES
    ('need_approval', 'Need Approval Notification'),
    ('approval',      'Approval Notification'),
    ('rejection',     'Rejection Notification'),
    ('adjustment',    'Adjustment Permission Notification')
) AS v(event_key, label)
WHERE NOT EXISTS (
    SELECT 1 FROM overtime_notification_settings s WHERE s.event_key = v.event_key
);

COMMIT;
