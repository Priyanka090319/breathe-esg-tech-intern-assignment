# Breathe ESG Tech Intern Assignment - Data Ingestion & Normalization Engine

[cite_start]A production-grade prototype built with **Django REST Framework** and **React** designed to ingest, normalize, and audit enterprise sustainability data streams[cite: 9, 17]. 

[cite_start]Every enterprise client stores emissions data in different shapes, formats, and systems[cite: 5]. [cite_start]This application provides a centralized, multi-tenant pipeline that normalizes three distinct real-world source streams into an audit-ready format, giving sustainability analysts a dedicated review dashboard to sign off on data before it is locked for auditors[cite: 9, 17, 39].

---

## 📂 Project Structure & Deliverables

[cite_start]This repository is strictly organized to meet the core evaluation requirements[cite: 36, 53, 54, 55]:

* [cite_start]**`/backend`**: Custom Django REST Framework application containing zero placeholder "CRUD slop"[cite: 12, 17]. [cite_start]Focuses entirely on raw data persistence, tenant isolation, and normalization services[cite: 17, 39].
* [cite_start]**`/frontend`**: React data analyst dashboard built with dense, high-clarity data grids for review, anomaly detection, and data sign-off[cite: 17, 56].
* [cite_start]**`MODEL.md`**: Outlines the relational database design, handling multi-tenancy, Scope 1/2/3 tracking, unit normalization, and immutable audit trails[cite: 39].
* [cite_start]**`SOURCES.md`**: Technical analysis of real-world data shapes for SAP, Utility providers, and corporate travel platforms[cite: 45].
* [cite_start]**`DECISIONS.md`**: Production-level assumptions made to resolve data ambiguities, what was ignored, and explicit questions for the PM[cite: 42, 43].
* [cite_start]**`TRADEOFFS.md`**: Documentation of exactly three complex engineering features deliberately left unbuilt during this 4-day sprint[cite: 44].

---

## ⚙️ Core Ingestion & Normalization Pipelines

[cite_start]The architecture handles three highly realistic, non-toy data sources[cite: 20]:

1. [cite_start]**SAP Fuel & Procurement (Scope 1):** Processes a simulated flat-file CSV extract[cite: 24, 25]. [cite_start]Handles localized German column headers natively (`Materialnummer`, `Menge`, `Einheit`, `Werk`, `Buchungsdatum`), translates inconsistent raw units, and resolves plant codes through an internal organization lookup map[cite: 26].
2. [cite_start]**Utility Portal Electricity (Scope 2):** Parses multi-month electricity billing cycle exports[cite: 28, 29]. [cite_start]Accounts for unaligned billing dates and dynamically flags consumption spikes exceeding >150% of historical baselines as `FLAGGED_SUSPICIOUS`[cite: 30].
3. [cite_start]**Corporate Travel API (Scope 3):** Simulates a Concur/Navan JSON platform payload[cite: 31]. [cite_start]Because explicit distances are often missing, it extracts IATA airport origin/destination codes, calculates geodesic distance via the Haversine equation, and maps emissions against cabin-class multipliers[cite: 32, 33].

---

## 🔒 State Machine Lifecycle

[cite_start]Data rows progress through explicit database-validated transitions managed by the analyst frontend[cite: 17, 39]:
`INGESTED` / `FLAGGED_SUSPICIOUS` / `FAILED_VALIDATION` ➔ `ANALYST_APPROVED` ➔ `LOCKED_FOR_AUDIT`

[cite_start]Once rows are locked for audit, they become completely immutable to prevent compliance tampering[cite: 17, 39].