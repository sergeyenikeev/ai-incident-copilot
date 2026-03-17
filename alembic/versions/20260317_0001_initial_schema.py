"""Начальная схема хранения инцидентов и workflow."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260317_0001"
down_revision = None
branch_labels = None
depends_on = None


incident_status = sa.Enum(
    "received",
    "analysis_requested",
    "analyzing",
    "analyzed",
    "failed",
    name="incident_status",
    native_enum=False,
)
severity_level = sa.Enum(
    "low",
    "medium",
    "high",
    "critical",
    name="severity_level",
    native_enum=False,
)
workflow_run_status = sa.Enum(
    "pending",
    "running",
    "completed",
    "failed",
    name="workflow_run_status",
    native_enum=False,
)
workflow_step_status = sa.Enum(
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
    name="workflow_step_status",
    native_enum=False,
)
event_processing_status = sa.Enum(
    "pending",
    "published",
    "consumed",
    "failed",
    name="event_processing_status",
    native_enum=False,
)
incident_event_type = sa.Enum(
    "incident.created",
    "incident.analysis.requested",
    "incident.analysis.completed",
    name="incident_event_type",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=True),
        sa.Column("status", incident_status, nullable=False),
        sa.Column("classification", sa.String(length=128), nullable=True),
        sa.Column("severity", severity_level, nullable=True),
        sa.Column("priority_score", sa.Integer(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("last_analysis_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_incidents_idempotency_key")),
    )
    op.create_index(op.f("ix_incidents_source"), "incidents", ["source"], unique=False)
    op.create_index(op.f("ix_incidents_status"), "incidents", ["status"], unique=False)
    op.create_index(op.f("ix_incidents_classification"), "incidents", ["classification"], unique=False)
    op.create_index(op.f("ix_incidents_severity"), "incidents", ["severity"], unique=False)
    op.create_index(op.f("ix_incidents_idempotency_key"), "incidents", ["idempotency_key"], unique=True)

    op.create_table(
        "incident_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", incident_event_type, nullable=False),
        sa.Column("kafka_topic", sa.String(length=255), nullable=False),
        sa.Column("event_key", sa.String(length=255), nullable=False),
        sa.Column("status", event_processing_status, nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_incident_events_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_events")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_incident_events_idempotency_key")),
    )
    op.create_index(op.f("ix_incident_events_incident_id"), "incident_events", ["incident_id"], unique=False)
    op.create_index(op.f("ix_incident_events_event_key"), "incident_events", ["event_key"], unique=False)
    op.create_index(op.f("ix_incident_events_kafka_topic"), "incident_events", ["kafka_topic"], unique=False)
    op.create_index(
        op.f("ix_incident_events_idempotency_key"),
        "incident_events",
        ["idempotency_key"],
        unique=True,
    )

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_event_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_name", sa.String(length=128), nullable=False),
        sa.Column("status", workflow_run_status, nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_workflow_runs_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trigger_event_id"],
            ["incident_events.id"],
            name=op.f("fk_workflow_runs_trigger_event_id_incident_events"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_runs")),
    )
    op.create_index(op.f("ix_workflow_runs_incident_id"), "workflow_runs", ["incident_id"], unique=False)

    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("node_name", sa.String(length=128), nullable=False),
        sa.Column("status", workflow_step_status, nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_workflow_steps_workflow_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_steps")),
    )
    op.create_index(op.f("ix_workflow_steps_workflow_run_id"), "workflow_steps", ["workflow_run_id"], unique=False)
    op.create_index(op.f("ix_workflow_steps_node_name"), "workflow_steps", ["node_name"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_audit_logs_incident_id_incidents"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_incident_id"), "audit_logs", ["incident_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_entity_id"), "audit_logs", ["entity_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_entity_type"), "audit_logs", ["entity_type"], unique=False)
    op.create_index(op.f("ix_audit_logs_request_id"), "audit_logs", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_request_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_entity_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_entity_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_incident_id"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_workflow_steps_node_name"), table_name="workflow_steps")
    op.drop_index(op.f("ix_workflow_steps_workflow_run_id"), table_name="workflow_steps")
    op.drop_table("workflow_steps")

    op.drop_index(op.f("ix_workflow_runs_incident_id"), table_name="workflow_runs")
    op.drop_table("workflow_runs")

    op.drop_index(op.f("ix_incident_events_idempotency_key"), table_name="incident_events")
    op.drop_index(op.f("ix_incident_events_kafka_topic"), table_name="incident_events")
    op.drop_index(op.f("ix_incident_events_event_key"), table_name="incident_events")
    op.drop_index(op.f("ix_incident_events_incident_id"), table_name="incident_events")
    op.drop_table("incident_events")

    op.drop_index(op.f("ix_incidents_idempotency_key"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_severity"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_classification"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_status"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_source"), table_name="incidents")
    op.drop_table("incidents")
