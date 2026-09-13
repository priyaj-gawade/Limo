---
name: validation
description: Verification audits, citation cross-checking, hallucination detection, and compliance scoring.
category: audit
triggers:
  - validate
  - verify
  - audit
  - check citations
  - fact check
  - compliance
deliverables:
  - validation_report
modes:
  - docs
  - audit
intents:
  - validate_artifact
  - audit_claims
  - verify_citations
required_tools:
  - artifact_tool
  - storage_tool
  - source_read
---

# Deliverable Validation & Fact-Checking Skill

## Objective
Audit deliverable artifacts against ingested sources, compute hallucination compliance scores, and record formal validation reports.

## Domain Guidelines
1. **Verification Metrics**:
   - Confidence Score (0.0 to 1.0): Measure proportion of verifiable claims against source text.
   - Threshold: Deliverables must achieve a score >= 0.70 to pass validation.
   - Hallucination Flag: Any fabricated statistic or ungrounded attribution immediately triggers `hallucination_check_passed = False`.
2. **Audit Checklist**:
   - Numerical Consistency: Verify that all figures, currency numbers, and dates match source files exactly.
   - Citation Integrity: Confirm that attributed source filenames and IDs exist in the active project.
   - Formatting Compliance: Verify that output matches intended structure and extension.
3. **Execution Pattern**:
   - Inspect artifact metadata via `artifact_tool(action='get_artifact')`.
   - Read content via `storage_tool`.
   - Cross-check against sources via `source_read`.
   - Record formal result via `artifact_tool(action='record_validation')`.
