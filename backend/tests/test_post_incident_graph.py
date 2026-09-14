"""
End-to-end integration tests for the post_incident vertical
(Vertical 1, Section 8.1). Mirrors test_contract_tracking_graph.py's
pattern: real database, real embeddings, only the LLM is mocked.

Three call_llm call sites are involved in the full pipeline:
  - orchestration.reason_node's call_llm (LLM reasoning + tool calls)
  - The tool calls themselves are real (real DB queries)

The mock sits at app.core.orchestration.call_llm (used by reason_node)
since this vertical uses the shared orchestration nodes directly.
"""

import json

import pytest

from app.core.db import get_connection
from app.schemas.agent_contract import AgentRunInput, TriggerType
from app.verticals.post_incident.graph import (
    run_post_incident_vertical,
    _parse_header_metadata,
    _content_hash,
    ACTION_THRESHOLD,
)


# -------------------------------------------------------------------
# Sample postmortem text for tests
# -------------------------------------------------------------------

SAMPLE_POSTMORTEM = """\
# Incident: Database Connection Pool Exhaustion — Payments Service
Date: 2024-03-15
Service: payments-service
Severity: P1

## Summary
The payments-service experienced a complete outage lasting 47 minutes.

## Root Cause
Connection leak in the batch reconciliation job.

## Mitigation
Killed the batch job and performed rolling pod restart.
"""

SAMPLE_POSTMORTEM_SHORT = """\
# Incident: Auth Token Storm
Date: 2024-05-22
Service: auth-service
Severity: P2

## Summary
Auth service flooded with token refresh requests.
"""


# -------------------------------------------------------------------
# Test: header metadata parsing
# -------------------------------------------------------------------

def test_parse_header_metadata_extracts_all_fields():
    metadata = _parse_header_metadata(SAMPLE_POSTMORTEM)
    assert metadata["title"] == "Database Connection Pool Exhaustion — Payments Service"
    assert metadata["service"] == "payments-service"
    assert metadata["severity"] == "P1"
    assert metadata["date"] == "2024-03-15"
    assert metadata["root_cause_tag"]  # should derive something from title


def test_parse_header_metadata_handles_missing_fields():
    metadata = _parse_header_metadata("Just some plain text with no headers.")
    assert metadata["title"] == ""
    assert metadata["service"] == ""
    assert metadata["severity"] == ""


# -------------------------------------------------------------------
# Test: content hash deduplication
# -------------------------------------------------------------------

def test_content_hash_is_deterministic():
    h1 = _content_hash("some text")
    h2 = _content_hash("some text")
    assert h1 == h2


def test_content_hash_differs_for_different_text():
    h1 = _content_hash("text A")
    h2 = _content_hash("text B")
    assert h1 != h2


# -------------------------------------------------------------------
# Test: high-confidence run creates a remediation ticket
# -------------------------------------------------------------------

def test_high_confidence_creates_ticket(monkeypatch):
    """When the LLM returns high confidence and should_create_ticket=True,
    the graph should auto-create an incident ticket."""
    monkeypatch.setattr(
        "app.core.orchestration.call_llm",
        lambda **kwargs: {
            "content": json.dumps({
                "confidence": 0.92,
                "should_create_ticket": True,
                "ticket_title": "Fix connection pool leak in payments-service",
                "linked_incident_ids": [],
                "analysis_summary": "Recurring pool exhaustion pattern detected.",
            }),
            "tool_calls": [],
        },
    )

    agent_input = AgentRunInput(
        vertical="post_incident",
        trigger_type=TriggerType.UPLOAD,
        input_payload={"text": SAMPLE_POSTMORTEM},
    )
    output = run_post_incident_vertical(agent_input)

    assert output.status == "completed"
    assert output.escalated is False
    assert len(output.actions_taken) == 1
    assert output.actions_taken[0].action_name == "create_incident_ticket"

    # Verify the ticket was actually created in the DB
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, status FROM incident_tickets WHERE run_id = %s;",
                (output.run_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["title"] == "Fix connection pool leak in payments-service"
    assert row["status"] == "open"


# -------------------------------------------------------------------
# Test: low-confidence run escalates
# -------------------------------------------------------------------

def test_low_confidence_escalates(monkeypatch):
    monkeypatch.setattr(
        "app.core.orchestration.call_llm",
        lambda **kwargs: {
            "content": json.dumps({
                "confidence": 0.3,
                "should_create_ticket": False,
                "ticket_title": "",
                "linked_incident_ids": [],
                "analysis_summary": "Insufficient evidence to create a ticket.",
            }),
            "tool_calls": [],
        },
    )

    agent_input = AgentRunInput(
        vertical="post_incident",
        trigger_type=TriggerType.UPLOAD,
        input_payload={"text": SAMPLE_POSTMORTEM},
    )
    output = run_post_incident_vertical(agent_input)

    assert output.status == "escalated"
    assert output.escalated is True
    assert output.escalation_reason is not None

    # Verify escalation was created in DB
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT reason, status FROM escalations WHERE run_id = %s;",
                (output.run_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["status"] == "open"


# -------------------------------------------------------------------
# Test: chunks are persisted into the KB
# -------------------------------------------------------------------

def test_chunks_are_persisted_into_kb(monkeypatch):
    """Each section of the postmortem should be embedded in the KB."""
    monkeypatch.setattr(
        "app.core.orchestration.call_llm",
        lambda **kwargs: {
            "content": json.dumps({
                "confidence": 0.5,
                "should_create_ticket": False,
                "ticket_title": "",
                "linked_incident_ids": [],
                "analysis_summary": "Analysis done.",
            }),
            "tool_calls": [],
        },
    )

    # Use a unique marker to find our embeddings
    unique_marker = "unique_kb_test_marker_xz92q"
    test_text = SAMPLE_POSTMORTEM.replace("47 minutes", unique_marker)

    agent_input = AgentRunInput(
        vertical="post_incident",
        trigger_type=TriggerType.UPLOAD,
        input_payload={"text": test_text},
    )
    run_post_incident_vertical(agent_input)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as cnt FROM embeddings WHERE vertical = 'post_incident' AND chunk_text LIKE %s;",
                (f"%{unique_marker}%",),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    # The marker is in the Summary section. section_chunker prepends the
    # header to each chunk, so the marker chunk should exist.
    assert row["cnt"] >= 1


# -------------------------------------------------------------------
# Test: incident row is inserted with metadata
# -------------------------------------------------------------------

def test_incident_row_is_inserted(monkeypatch):
    monkeypatch.setattr(
        "app.core.orchestration.call_llm",
        lambda **kwargs: {
            "content": json.dumps({
                "confidence": 0.5,
                "should_create_ticket": False,
                "ticket_title": "",
                "linked_incident_ids": [],
                "analysis_summary": "Done.",
            }),
            "tool_calls": [],
        },
    )

    agent_input = AgentRunInput(
        vertical="post_incident",
        trigger_type=TriggerType.UPLOAD,
        input_payload={"text": SAMPLE_POSTMORTEM_SHORT},
    )
    run_post_incident_vertical(agent_input)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, service FROM incidents WHERE service = 'auth-service';"
            )
            row = cur.fetchone()
    finally:
        conn.close()
    assert row is not None
    assert "Auth Token Storm" in row["title"]
    assert row["service"] == "auth-service"


# -------------------------------------------------------------------
# Test: deduplication — same postmortem doesn't create duplicate
# -------------------------------------------------------------------

def test_deduplication_prevents_duplicate_incidents(monkeypatch):
    monkeypatch.setattr(
        "app.core.orchestration.call_llm",
        lambda **kwargs: {
            "content": json.dumps({
                "confidence": 0.5,
                "should_create_ticket": False,
                "ticket_title": "",
                "linked_incident_ids": [],
                "analysis_summary": "Done.",
            }),
            "tool_calls": [],
        },
    )

    unique_text = "# Incident: Dedup Test Incident XYZ123\nDate: 2024-01-01\nService: dedup-test\nSeverity: P3\n\n## Summary\nTest for deduplication."

    agent_input = AgentRunInput(
        vertical="post_incident",
        trigger_type=TriggerType.UPLOAD,
        input_payload={"text": unique_text},
    )
    # Run twice with same text
    run_post_incident_vertical(agent_input)
    run_post_incident_vertical(agent_input)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) as cnt FROM incidents WHERE service = 'dedup-test';"
            )
            row = cur.fetchone()
    finally:
        conn.close()
    # Only one incident row, not two
    assert row["cnt"] == 1


# -------------------------------------------------------------------
# Test: malformed LLM output fails safe
# -------------------------------------------------------------------

def test_malformed_llm_output_fails_safe(monkeypatch):
    monkeypatch.setattr(
        "app.core.orchestration.call_llm",
        lambda **kwargs: {
            "content": "not valid json at all",
            "tool_calls": [],
        },
    )

    agent_input = AgentRunInput(
        vertical="post_incident",
        trigger_type=TriggerType.UPLOAD,
        input_payload={"text": SAMPLE_POSTMORTEM},
    )
    output = run_post_incident_vertical(agent_input)

    # Fails safe: escalated (confidence 0.0 < threshold), no crash
    assert output.status == "escalated"
    assert output.escalated is True
    assert output.actions_taken == []
