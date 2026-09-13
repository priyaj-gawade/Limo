---
name: spreadsheet
description: Structured data tables, financial models, formulas, and schema definitions.
category: deliverable
triggers:
  - spreadsheet
  - excel
  - xlsx
  - csv
  - table
  - financial model
  - ledger
deliverables:
  - xlsx
  - csv
modes:
  - sheets
  - spreadsheet
intents:
  - generate_spreadsheet
  - build_model
  - export_tabular_data
required_tools:
  - source_read
  - transform_contract
  - artifact_tool
---

# Spreadsheet & Tabular Modeling Skill

## Objective
Guide the agent in structuring tabular data, calculation models, and clear spreadsheet architectures.

## Domain Guidelines
1. **Schema & Layout**:
   - Header Row: Distinct, capitalized, standardized column headers without special symbols.
   - Type Consistency: Ensure numeric columns contain exclusively numbers, dates follow ISO format (`YYYY-MM-DD`), and currency values have defined unit labels.
   - Formula Integrity: Use uppercase standard formulas (e.g. `SUM()`, `AVERAGE()`, `VLOOKUP()`, `IF()`).
2. **Tabular Organization**:
   - Summary / Dashboard Sheet: Key aggregate figures, KPI totals, and assumptions.
   - Raw Data Sheet: Clean, normalized tabular records without merged cells in data columns.
3. **Execution Pattern**:
   - Extract numerical facts from ingested sources via `source_read`.
   - Organize columns and rows cleanly.
   - Queue transformation contract using `transform_contract` with `requested_formats=['spreadsheet']`.
