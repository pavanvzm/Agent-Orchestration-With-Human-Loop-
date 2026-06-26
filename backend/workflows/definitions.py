"""
Sample workflow definitions for the Multi-Agent Platform.
"""
from __future__ import annotations

from typing import Any, Optional
from models.schemas import WorkflowDefinition, WorkflowStep, HITLCheckpointConfig, ApprovalAction


# ─────────────────────────────────────────────────────────
# Research Agent Workflow
# ─────────────────────────────────────────────────────────
def create_research_workflow() -> WorkflowDefinition:
    """Create a research agent workflow with HITL checkpoints."""
    return WorkflowDefinition(
        name="Research Task Workflow",
        description="Automated research with human verification checkpoints",
        version="1.0.0",
        steps=[
            WorkflowStep(
                id="collect",
                name="Collect Information",
                description="Gather relevant information from various sources",
                tool="web_search",
                config={"max_sources": 10}
            ),
            WorkflowStep(
                id="analyze",
                name="Analyze Data",
                description="Analyze and synthesize the collected information",
                agent_id="reasoning-agent",
                config={"depth": "comprehensive"}
            ),
            WorkflowStep(
                id="pre_review",
                name="Pre-Review Checkpoint",
                description="Human approval before generating final report",
                tool="hitl_checkpoint",
                next_step=None,  # Ends workflow after approval
                conditions={
                    "requires_approval": True,
                    "checkpoint_type": "pre_execution"
                }
            ),
            WorkflowStep(
                id="generate",
                name="Generate Report",
                description="Generate the final research report",
                tool="report_generator",
                config={"format": "markdown"}
            ),
            WorkflowStep(
                id="review",
                name="Final Review",
                description="Human review of the generated report",
                tool="hitl_checkpoint",
                conditions={
                    "requires_approval": True,
                    "checkpoint_type": "post_execution"
                }
            )
        ],
        entry_point="collect"
    )


# ─────────────────────────────────────────────────────────
# Code Review Workflow
# ─────────────────────────────────────────────────────────
def create_code_review_workflow() -> WorkflowDefinition:
    """Create a code review workflow with security checkpoints."""
    return WorkflowDefinition(
        name="Code Review Workflow",
        description="Automated code review with security and quality checkpoints",
        version="1.0.0",
        steps=[
            WorkflowStep(
                id="static_analysis",
                name="Static Analysis",
                description="Run static code analysis tools",
                tool="linter",
                config={"rules": "recommended"}
            ),
            WorkflowStep(
                id="security_scan",
                name="Security Scan",
                description="Scan for security vulnerabilities",
                tool="security_scanner",
                config={"severity_threshold": "medium"}
            ),
            WorkflowStep(
                id="security_review",
                name="Security Review Checkpoint",
                description="Human review of security findings",
                tool="hitl_checkpoint",
                conditions={
                    "requires_approval": True,
                    "condition_type": "security_finding",
                    "min_severity": "high"
                }
            ),
            WorkflowStep(
                id="code_quality",
                name="Code Quality Assessment",
                description="Assess overall code quality",
                tool="quality_metrics",
                config={"metrics": ["complexity", "maintainability", "test_coverage"]}
            ),
            WorkflowStep(
                id="final_review",
                name="Final Approval",
                description="Final human approval before merge recommendation",
                tool="hitl_checkpoint",
                conditions={
                    "requires_approval": True
                }
            )
        ],
        entry_point="static_analysis"
    )


# ─────────────────────────────────────────────────────────
# Customer Support Workflow
# ─────────────────────────────────────────────────────────
def create_support_workflow() -> WorkflowDefinition:
    """Create a customer support workflow with escalation checkpoints."""
    return WorkflowDefinition(
        name="Customer Support Workflow",
        description="AI-assisted customer support with human escalation",
        version="1.0.0",
        steps=[
            WorkflowStep(
                id="understand",
                name="Understand Issue",
                description="Parse and understand the customer's issue",
                agent_id="reasoning-agent",
                config={"task_type": "comprehension"}
            ),
            WorkflowStep(
                id="search_kb",
                name="Search Knowledge Base",
                description="Search for relevant knowledge base articles",
                tool="kb_search",
                config={"max_results": 5}
            ),
            WorkflowStep(
                id="generate_response",
                name="Generate Response",
                description="Generate a helpful response",
                agent_id="reasoning-agent",
                config={"tone": "professional"}
            ),
            WorkflowStep(
                id="sensitivity_check",
                name="Sensitivity Check",
                description="Check for sensitive topics requiring human review",
                tool="content_filter",
                conditions={
                    "checkpoint_type": "sensitivity",
                    "threshold": 0.7
                }
            ),
            WorkflowStep(
                id="escalation",
                name="Escalation Checkpoint",
                description="Escalate to human if needed",
                tool="hitl_checkpoint",
                conditions={
                    "requires_approval": True,
                    "condition_type": "escalation",
                    "auto_escalate_topics": ["billing", "legal", "refund"]
                }
            ),
            WorkflowStep(
                id="send_response",
                name="Send Response",
                description="Send the final response to customer",
                tool="email_sender",
                config={"template": "support_response"}
            )
        ],
        entry_point="understand"
    )


# ─────────────────────────────────────────────────────────
# Document Processing Workflow
# ─────────────────────────────────────────────────────────
def create_document_workflow() -> WorkflowDefinition:
    """Create a document processing workflow with compliance checkpoints."""
    return WorkflowDefinition(
        name="Document Processing Workflow",
        description="Automated document processing with compliance verification",
        version="1.0.0",
        steps=[
            WorkflowStep(
                id="extract",
                name="Extract Content",
                description="Extract text and metadata from document",
                tool="document_parser",
                config={"formats": ["pdf", "docx", "txt"]}
            ),
            WorkflowStep(
                id="classify",
                name="Classify Document",
                description="Classify document type and sensitivity",
                tool="classifier",
                config={"categories": ["contract", "invoice", "report", "other"]}
            ),
            WorkflowStep(
                id="compliance_check",
                name="Compliance Checkpoint",
                description="Verify compliance requirements",
                tool="hitl_checkpoint",
                conditions={
                    "requires_approval": True,
                    "condition_type": "compliance",
                    "sensitive_types": ["contract", "legal"]
                }
            ),
            WorkflowStep(
                id="extract_entities",
                name="Extract Entities",
                description="Extract key entities (names, dates, amounts)",
                tool="ner_extractor",
                config={"entity_types": ["person", "organization", "date", "money"]}
            ),
            WorkflowStep(
                id="store",
                name="Store Document",
                description="Store processed document and metadata",
                tool="document_store",
                config={"index": True}
            )
        ],
        entry_point="extract"
    )


# ─────────────────────────────────────────────────────────
# Workflow Registry
# ─────────────────────────────────────────────────────────
class WorkflowRegistry:
    """Registry for workflow definitions."""
    
    def __init__(self):
        self._workflows: dict[str, WorkflowDefinition] = {}
        self._register_defaults()
    
    def _register_defaults(self):
        """Register default workflows."""
        self.register("research", create_research_workflow())
        self.register("code_review", create_code_review_workflow())
        self.register("customer_support", create_support_workflow())
        self.register("document_processing", create_document_workflow())
    
    def register(self, name: str, workflow: WorkflowDefinition) -> None:
        """Register a workflow."""
        self._workflows[name] = workflow
    
    def get(self, name: str) -> Optional[WorkflowDefinition]:
        """Get a workflow by name."""
        return self._workflows.get(name)
    
    def list(self) -> list[str]:
        """List all registered workflow names."""
        return list(self._workflows.keys())
    
    def all(self) -> dict[str, WorkflowDefinition]:
        """Get all workflows."""
        return self._workflows.copy()


# Global registry instance
workflow_registry = WorkflowRegistry()
