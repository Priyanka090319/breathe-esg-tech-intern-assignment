# DECISIONS

## Context

This document records the implementation decisions made while building the ESG ingestion core:

- Django data model with strict multi-tenancy boundaries
- Immutable raw payload lineage
- Status-driven audit workflow (`INGESTED`, `FLAGGED_SUSPICIOUS`, `FAILED_VALIDATION`, `ANALYST_APPROVED`, `LOCKED_FOR_AUDIT`)
- Parser services for SAP fuel/procurement CSV, utility billing CSV, and Concur-style travel JSON

No curated mock dataset was provided by product/design. We therefore designed realistic, production-shaped inputs that represent high-frequency operational failure points seen in enterprise ESG ingestion.

## Ambiguities Resolved

### 1) Input data realism vs synthetic placeholders

Decision:
- We modeled real-world edge shapes instead of toy payloads:
  - SAP parser uses German headers: `Materialnummer`, `Menge`, `Einheit`, `Werk`, `Buchungsdatum`
  - Utility parser supports off-cycle billing windows (`Start_Date`, `End_Date`) and anomaly detection for overlap + spikes
  - Travel parser consumes Concur-like records with IATA airports and cabin class, estimating distance via geolocation

Why:
- These are not theoretical edge cases; they are common integration pain points in multinational environments.
- Building around realistic failure modes early is lower risk than retrofitting validation after downstream analytics have already coupled to bad assumptions.

### 2) Validation behavior when rows are malformed

Decision:
- Parser never hard-crashes the ingestion run due to a single malformed row.
- Invalid rows are persisted as `FAILED_VALIDATION` in `NormalizedDataRow` with a concrete `status_note` reason.
- Raw payload remains immutable and queryable for replay/debug.

Why:
- In production, partial ingestion with traceable failures is operationally safer than all-or-nothing behavior.
- Audit and incident response require lineage retention even for rejected records.

### 3) Scope and normalization model shape

Decision:
- We store both original and normalized fields:
  - `original_value`, `original_unit`
  - `normalized_value`, `normalized_unit`
  - `conversion_factor`, `conversion_reference`
- Scope classification is explicit (`SCOPE_1`, `SCOPE_2`, `SCOPE_3`) at row level.

Why:
- ESG auditors challenge methodology and conversion basis. Storing both sides and factor provenance is mandatory for defensibility.
- Computed-only pipelines without source-level unit/factor persistence are difficult to certify.

### 4) State machine strictness

Decision:
- Status transitions are restricted and validated.
- `LOCKED_FOR_AUDIT` is terminal; locked rows are immutable.
- Approval and lock actions stamp actor + timestamp.

Why:
- Governance workflows fail when status writes are unconstrained.
- A terminal lock state is required for reproducible period-close reporting.

## Explicitly Out of Scope (Ignored to ship high-integrity core in 4 days)

The following were intentionally deferred:

- Multi-currency conversion for spend-based emissions calculations
- Region-specific utility tariff decomposition beyond meter usage normalization
- Complex hotel-night or rail-class tier factors in travel calculations
- Supplier-specific custom unit dictionaries beyond current SAP/utility/travel core
- Full external factor catalog management lifecycle (versioning UI, approvals, rollback tooling)
- Automated backfill/replay orchestration for historical payload migrations

Reason for deferral:
- These are valid requirements, but not blockers for a robust ingestion substrate.
- Delivering strict tenancy, lineage, validation semantics, and auditable status control first gives the team a stable base for iterative domain expansion.

## Trade-offs Accepted

- Utility overlap detection is robust for current model but constrained by available period fields in normalized rows.
- Travel distance estimation uses a curated airport coordinate map; unknown airports fail validation intentionally.
- SAP plant-code interpretation relies on internal lookup dictionary and will fail closed on unknown codes.

These trade-offs were accepted because fail-closed + visible validation failure is safer than silent, incorrect emissions math.

## Strategic PM Questions

1. How should we handle retroactively updated utility readings from providers after a reporting period is already approved or locked?
2. What is the authoritative source and governance process for emission factor updates (owner, approval chain, effective date policy)?
3. Should analysts be allowed to unlock `LOCKED_FOR_AUDIT` records under controlled exception workflows, or must corrections flow only via compensating entries?

## Implementation Principle

The guiding principle was: **ingest imperfect enterprise data without losing provenance, and fail rows safely instead of failing pipelines silently**.  
This keeps the system auditable under operational pressure and avoids downstream analytics contamination.
