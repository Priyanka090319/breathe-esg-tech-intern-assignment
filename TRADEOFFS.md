# TRADEOFFS

This sprint intentionally prioritized a trustworthy ingestion core (multi-tenant data integrity, lineage, validation states, and analyst workflow controls) over breadth.  
Below are the **three deliberate non-builds** and why excluding them was the correct 4-day decision.

## 1) Asynchronous Ingestion Architecture (Celery/Redis) — Not Built

### What we built instead

- Parsing runs synchronously in Django request/response flow (`/api/ingest/file/`).
- Each row is validated and persisted with explicit status outcomes (`INGESTED`, `FLAGGED_SUSPICIOUS`, `FAILED_VALIDATION`).
- Failures are captured as data, not process crashes.

### Why this is correct for a prototype

- Synchronous execution is simpler to reason about and faster to implement/debug in a short sprint.
- It keeps ingestion behavior transparent during early validation with reviewers and analysts.
- Current sample payload sizes are small enough that synchronous processing is operationally acceptable.

### Why this must change for production scale

- Large files and concurrent uploads will push request duration beyond safe HTTP timeouts.
- Worker queues are required for backpressure, retry policies, and predictable throughput.
- Production architecture should move parsing to Celery workers backed by Redis (or equivalent), with job status tracking and idempotency controls.

### Exclusion rationale (4-day scope)

- Building queue infrastructure, retry semantics, dead-letter handling, and observability would consume substantial sprint capacity.
- That work is high value, but not required to prove correctness of schema, lineage, and parser logic in this phase.

---

## 2) Complete Automated GHG Protocol Factor Mapping API — Not Built

### What we built instead

- Static local lookup maps for units, plant taxonomies, and emission factors.
- Conversion provenance is persisted (`conversion_factor`, `conversion_reference`) for auditability.

### Why this is correct for a prototype

- Static mappings give deterministic outputs during development and review.
- They remove dependency risk from third-party API availability, quotas, schema/version drift, and auth setup.
- This allowed us to verify end-to-end ingestion and state-machine behavior first.

### Why this must change for production scale

- Real deployments need governed factor lifecycles (versioning, effective dates, jurisdiction-specific factors).
- Integrations with catalogs (e.g., Climatiq/DEFRA or internal factor services) are necessary for coverage and compliance updates.
- Without centralized factor governance, historical reproducibility and regulatory defensibility become fragile over time.

### Exclusion rationale (4-day scope)

- A full factor API integration requires contract design, caching strategy, fallback logic, and governance workflows.
- Implementing that now would have reduced quality in foundational controls (tenancy, lineage, validation, audit states), which were higher priority for this sprint objective.

---

## 3) Granular Field-Level Data Editing UI — Not Built

### What we built instead

- Analysts can review, approve, and lock records through explicit workflow actions.
- Suspicious/failed records are visible with reasons, and state transitions remain controlled.
- Raw payload remains immutable, preserving source truth.

### Why this is correct for a prototype

- Approve/flag workflow validates the core operational loop without introducing high-risk client-side editing complexity.
- It keeps the audit model clean: ingestion data stays immutable; downstream corrections can be handled as controlled events.
- This approach aligns with governance-first design for ESG systems.

### Why this must evolve later

- Analysts will eventually need efficient correction tools for high-volume exception handling.
- A production editing surface should be permissioned, field-scoped, and fully audit-logged (before/after values, actor, timestamp, reason).
- UX should support bulk operations safely without compromising lineage and approval controls.

### Exclusion rationale (4-day scope)

- Building an Excel-like grid with validation, optimistic updates, conflict handling, and audit-safe write paths is a major feature on its own.
- Deferring it protected the integrity model and ensured the sprint delivered a dependable ingestion baseline instead of a partially reliable editing system.

---

## Final Position

These exclusions were intentional, not omissions.  
In 4 days, the highest-leverage decision was to ship **correctness, traceability, and governance primitives first**, then layer scale automation and editing ergonomics in subsequent iterations.
