"""initial schema

Revision ID: c28dd1c04d1e
Revises:
Create Date: 2026-09-23 17:45:10.754510

Hand-edited after autogenerate to add three things autogenerate can't
produce on its own, all traceable to specific design decisions already
made in docs/:

1. Enum types created explicitly, once, before use (create_type=False on
   every column) — case_status in particular is referenced by two tables
   (cases, case_state_transitions); letting each column definition create
   its own copy would fail with "type already exists" on the second one.
2. A partial unique index enforcing at most one non-terminal AgentRun per
   (case_id, agent_type) — architecture.md's idempotency guarantee,
   database-enforced rather than left to application discipline.
3. Append-only enforcement via trigger on case_state_transitions,
   human_reviews, and audit_events (data-model.md, security.md) — UPDATE
   and DELETE raise an exception regardless of which role issues them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c28dd1c04d1e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CASE_STATUS_VALUES = (
    'INTAKE', 'VALIDATING', 'VALIDATION_FAILED', 'DOCUMENTS_READY', 'CLASSIFYING',
    'INVESTIGATING', 'INVESTIGATIONS_COMPLETE', 'RECONCILING', 'REINVESTIGATING',
    'RECONCILING_POST_REINVESTIGATION', 'SYNTHESIZING', 'AWAITING_HUMAN_REVIEW',
    'FINALIZED', 'FAILED', 'CANCELLED',
)

ENUM_DEFS = {
    'case_status': CASE_STATUS_VALUES,
    'agent_type': ('security_investigator', 'privacy_investigator', 'single_agent_baseline'),
    'agent_run_status': ('pending', 'running', 'succeeded', 'failed'),
    'doc_type': (
        'security_questionnaire', 'security_whitepaper', 'soc_report', 'dpa',
        'privacy_policy', 'ai_governance_doc', 'subprocessor_list', 'contract_sla',
        'pentest_attestation', 'other',
    ),
    'document_domain': ('security', 'privacy_ai_governance', 'both'),
    'claim_domain': ('security', 'privacy_ai_governance'),
    'claim_type': (
        'certification', 'policy_statement', 'sla_metric', 'data_practice',
        'subprocessor_disclosure', 'technical_control', 'other',
    ),
    'verification_status': ('supported', 'contradicted', 'unverified', 'ambiguous'),
    'conflict_type': (
        'direct_contradiction', 'subtle_contradiction', 'cross_domain_conflict', 'version_conflict',
    ),
    'conflict_status': ('open', 'reinvestigating', 'escalated', 'resolved'),
    'human_decision': ('approved', 'rejected', 'conditional', 'needs_more_info'),
}

APPEND_ONLY_TABLES = ('case_state_transitions', 'human_reviews', 'audit_events')


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUM_DEFS[name], name=name, create_type=False)


def upgrade() -> None:
    # --- 1. Enum types, created once, explicitly ---
    bind = op.get_bind()
    for name, values in ENUM_DEFS.items():
        postgresql.ENUM(*values, name=name, create_type=False).create(bind, checkfirst=True)

    # --- 2. Tables (FK-dependency order, as autogenerate produced) ---
    op.create_table('vendors',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_vendors')),
    )
    op.create_table('cases',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('vendor_id', sa.UUID(), nullable=False),
        sa.Column('status', _enum('case_status'), server_default='INTAKE', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], name=op.f('fk_cases_vendor_id_vendors')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_cases')),
    )
    op.create_table('agent_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('agent_type', _enum('agent_type'), nullable=False),
        sa.Column('status', _enum('agent_run_status'), server_default='pending', nullable=False),
        sa.Column('model', sa.Text(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_agent_runs_case_id_cases')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_runs')),
    )
    op.create_table('audit_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('actor', sa.Text(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_audit_events_case_id_cases')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events')),
    )
    op.create_table('case_state_transitions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('from_status', _enum('case_status'), nullable=True),
        sa.Column('to_status', _enum('case_status'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_case_state_transitions_case_id_cases')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_case_state_transitions')),
    )
    op.create_table('conflicts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('conflict_type', _enum('conflict_type'), nullable=False),
        sa.Column('status', _enum('conflict_status'), server_default='open', nullable=False),
        sa.Column('resolution_method', sa.Text(), nullable=True),
        sa.Column('resolution_rationale', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_conflicts_case_id_cases')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_conflicts')),
    )
    op.create_table('evidence_documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('filename', sa.Text(), nullable=False),
        sa.Column('mime_type', sa.Text(), nullable=False),
        sa.Column('doc_type', _enum('doc_type'), nullable=False),
        sa.Column('domain', _enum('document_domain'), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_evidence_documents_case_id_cases')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence_documents')),
    )
    op.create_table('human_reviews',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('reviewer_id', sa.Text(), nullable=False),
        sa.Column('decision', _enum('human_decision'), nullable=False),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_human_reviews_case_id_cases')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_human_reviews')),
    )
    op.create_table('document_versions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('storage_ref', sa.Text(), nullable=False),
        sa.Column('parsed_text_ref', sa.Text(), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('content_hash', sa.Text(), nullable=False),
        sa.Column('parsed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['evidence_documents.id'],
                                 name=op.f('fk_document_versions_document_id_evidence_documents')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_document_versions')),
        sa.UniqueConstraint('document_id', 'version_number', name=op.f('uq_document_versions_document_id')),
    )
    op.create_table('reinvestigations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conflict_id', sa.UUID(), nullable=False),
        sa.Column('agent_run_id', sa.UUID(), nullable=False),
        sa.Column('outcome', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agent_run_id'], ['agent_runs.id'],
                                 name=op.f('fk_reinvestigations_agent_run_id_agent_runs')),
        sa.ForeignKeyConstraint(['conflict_id'], ['conflicts.id'],
                                 name=op.f('fk_reinvestigations_conflict_id_conflicts')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_reinvestigations')),
        # Decision #13 (max one re-investigation round): enforced here, not
        # just in application logic — a second row for the same conflict
        # is a constraint violation.
        sa.UniqueConstraint('conflict_id', name=op.f('uq_reinvestigations_conflict_id')),
    )
    op.create_table('claims',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('agent_run_id', sa.UUID(), nullable=False),
        sa.Column('domain', _enum('claim_domain'), nullable=False),
        sa.Column('claim_type', _enum('claim_type'), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('predicate', sa.Text(), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('unit', sa.Text(), nullable=True),
        sa.Column('temporal_scope', sa.Text(), nullable=True),
        sa.Column('source_document_version_id', sa.UUID(), nullable=False),
        sa.Column('source_location', sa.Text(), nullable=False),
        sa.Column('source_excerpt', sa.Text(), nullable=False),
        sa.Column('evidence_requirement', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agent_run_id'], ['agent_runs.id'], name=op.f('fk_claims_agent_run_id_agent_runs')),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_claims_case_id_cases')),
        sa.ForeignKeyConstraint(['source_document_version_id'], ['document_versions.id'],
                                 name=op.f('fk_claims_source_document_version_id_document_versions')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_claims')),
    )
    op.create_table('evidence_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('claim_id', sa.UUID(), nullable=False),
        sa.Column('document_version_id', sa.UUID(), nullable=False),
        sa.Column('location', sa.Text(), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], name=op.f('fk_evidence_items_claim_id_claims')),
        sa.ForeignKeyConstraint(['document_version_id'], ['document_versions.id'],
                                 name=op.f('fk_evidence_items_document_version_id_document_versions')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence_items')),
    )
    op.create_table('findings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('case_id', sa.UUID(), nullable=False),
        sa.Column('agent_run_id', sa.UUID(), nullable=False),
        sa.Column('claim_id', sa.UUID(), nullable=False),
        sa.Column('verification_status', _enum('verification_status'), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agent_run_id'], ['agent_runs.id'], name=op.f('fk_findings_agent_run_id_agent_runs')),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_findings_case_id_cases')),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], name=op.f('fk_findings_claim_id_claims')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_findings')),
    )
    op.create_table('conflict_findings',
        sa.Column('conflict_id', sa.UUID(), nullable=False),
        sa.Column('finding_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['conflict_id'], ['conflicts.id'],
                                 name=op.f('fk_conflict_findings_conflict_id_conflicts')),
        sa.ForeignKeyConstraint(['finding_id'], ['findings.id'],
                                 name=op.f('fk_conflict_findings_finding_id_findings')),
        sa.PrimaryKeyConstraint('conflict_id', 'finding_id', name=op.f('pk_conflict_findings')),
    )
    op.create_table('finding_evidence_items',
        sa.Column('finding_id', sa.UUID(), nullable=False),
        sa.Column('evidence_item_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['evidence_item_id'], ['evidence_items.id'],
                                 name=op.f('fk_finding_evidence_items_evidence_item_id_evidence_items')),
        sa.ForeignKeyConstraint(['finding_id'], ['findings.id'],
                                 name=op.f('fk_finding_evidence_items_finding_id_findings')),
        sa.PrimaryKeyConstraint('finding_id', 'evidence_item_id', name=op.f('pk_finding_evidence_items')),
    )
    op.create_table('human_review_overrides',
        sa.Column('human_review_id', sa.UUID(), nullable=False),
        sa.Column('finding_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['finding_id'], ['findings.id'],
                                 name=op.f('fk_human_review_overrides_finding_id_findings')),
        sa.ForeignKeyConstraint(['human_review_id'], ['human_reviews.id'],
                                 name=op.f('fk_human_review_overrides_human_review_id_human_reviews')),
        sa.PrimaryKeyConstraint('human_review_id', 'finding_id', name=op.f('pk_human_review_overrides')),
    )

    # --- 3. Idempotency: at most one non-terminal AgentRun per (case_id, agent_type) ---
    op.execute(
        "CREATE UNIQUE INDEX uq_agent_runs_case_agent_active "
        "ON agent_runs (case_id, agent_type) "
        "WHERE status IN ('pending', 'running')"
    )

    # --- 4. Append-only enforcement (trigger, not just application discipline) ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                '% on % is append-only: % is not permitted',
                TG_OP, TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION prevent_mutation();
            """
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS prevent_mutation()")

    op.drop_table('human_review_overrides')
    op.drop_table('finding_evidence_items')
    op.drop_table('conflict_findings')
    op.drop_table('findings')
    op.drop_table('evidence_items')
    op.drop_table('claims')
    op.drop_table('reinvestigations')
    op.drop_table('document_versions')
    op.drop_table('human_reviews')
    op.drop_table('evidence_documents')
    op.drop_table('conflicts')
    op.drop_table('case_state_transitions')
    op.drop_table('audit_events')
    op.drop_table('agent_runs')
    op.drop_table('cases')
    op.drop_table('vendors')

    bind = op.get_bind()
    for name, values in ENUM_DEFS.items():
        postgresql.ENUM(*values, name=name, create_type=False).drop(bind, checkfirst=True)
