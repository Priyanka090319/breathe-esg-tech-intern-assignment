# SOURCES

## Scope of This Document

This file describes the real-world technical input shapes assumed by the ingestion services and why those shapes were selected. It also documents failure modes that can break parsing in enterprise-scale deployments.

## Source 1: SAP Fuel / Procurement Flat File (CSV)

### Assumed operational shape

- Transport: scheduled export from SAP (ECC/S4) as CSV
- Typical content profile: material movement or procurement quantities mapped to fuel/activity categories
- Language/regionalization: German headers are common in EU subsidiaries

### Required fields used by parser

- `Materialnummer` (material identifier)
- `Menge` (quantity)
- `Einheit` (unit)
- `Werk` (plant/site code)
- `Buchungsdatum` (posting date)

### Parser interpretation logic

- `Einheit` mapped via unit dictionary (currently `L`, `KG` variants)
- `Werk` mapped via internal plant-code taxonomy to scope/category
- `Menge` parsed as decimal (supports comma decimal normalization)
- `Buchungsdatum` parsed into activity date
- Normalized emissions derived using deterministic factor chain and persisted with factor provenance

### Why this shape was selected

- It matches common SAP export patterns in global manufacturing/energy footprints.
- German field keys represent a realistic multilingual integration challenge.
- Plant-code mapping mirrors how many organizations classify Scope 1 activities by operational site.

## Source 2: Utility Portal Billing Export (CSV)

### Assumed operational shape

- Transport: provider portal CSV download or automated feed
- Data semantics: meter-period usage and tariff metadata

### Required fields used by parser

- `Meter_ID`
- `Start_Date`
- `End_Date`
- `Usage_kWh`
- `Tariff_Code`

### Parser interpretation logic

- Validates chronological billing window (`End_Date >= Start_Date`)
- Parses kWh usage as decimal
- Flags suspicious rows when:
  - billing periods overlap (in-batch or against existing rows)
  - usage exceeds 150% of historical average for same meter
- Persists suspicious rows as `FLAGGED_SUSPICIOUS` (not dropped), preserving analyst workflow

### Why this shape was selected

- Meter-level period data is the standard baseline for Scope 2 ingestion.
- Off-cycle and irregular billing windows are common in utility operations and must be modeled explicitly.
- Overlap/spike checks are low-cost, high-value controls for first-line anomaly detection.

## Source 3: Corporate Travel (Concur-style JSON)

### Assumed operational shape

- Transport: API payload from travel platform (Concur-like)
- Data semantics: trip segments with origin/destination and cabin class

### Required fields used by parser

- `employee_id`
- `trip_purpose`
- `origin_airport` (IATA)
- `destination_airport` (IATA)
- `cabin_class` (`Economy`/`Business`, normalized in parser)

### Parser interpretation logic

- Validates required keys and non-identical origin/destination
- Maps IATA codes to geocoordinates
- Estimates distance using haversine
- Applies cabin multiplier over base emission factor to produce normalized MTCO2E
- Unknown airports or unsupported cabin classes fail validation with explicit reason

### Why this shape was selected

- Captures the practical minimum fields most enterprises receive from travel APIs.
- IATA-based distance estimation is a common baseline when carrier-level fuel data is unavailable.
- Cabin multiplier is a pragmatic approximation aligned with standard travel emissions modeling practice.

## Sample Data Logic (and why it is realistic)

The sample records were intentionally designed to reflect operational stress cases:

- SAP:
  - valid fuel quantities with German headers
  - unknown plant codes
  - unsupported units
  - malformed posting dates
- Utility:
  - clean monthly usage
  - overlapping billing periods
  - outlier spikes relative to meter baseline
  - negative/invalid usage inputs
- Travel:
  - valid long-haul routes (`JFK` -> `LHR`)
  - unknown IATA codes
  - unsupported cabin strings
  - structurally invalid trip items

This is deliberate: production readiness is primarily about behavior on bad data, not ideal data.

## Known Break Risks in High-Stakes Deployments

The following can break or degrade parser reliability in multi-million-dollar deployments if unmanaged:

1. SAP structural shifts during ERP upgrades
   - Header renames, delimiter changes, encoding changes, additional preamble rows
   - Custom company-code extracts diverging from global template

2. Utility provider layout drift
   - Municipal/co-op utilities often change CSV column names/order with little notice
   - Regional date formats and decimal separators vary unpredictably

3. Travel API schema versioning
   - Upstream vendor introduces nested itinerary model, deprecates flat keys
   - Airport code anomalies (rail stations, city pseudo-codes, private terminals)

4. Taxonomy drift in internal mappings
   - Plant codes added/retired without synchronized mapping updates
   - New units introduced without conversion rules

5. Factor governance gaps
   - Emission factor updates applied inconsistently across ingestion windows
   - No controlled effective-date policy, leading to non-reproducible historical reruns

6. Volume and concurrency stress
   - Large bulk files + concurrent analyst actions can expose lock/contention and throughput bottlenecks
   - If not monitored, anomaly checks can become expensive on large historical windows

## Operational Guardrails Recommended

- Contract tests for each upstream source schema (header/key validation before parse)
- Parser versioning with explicit compatibility matrix per source
- Mapping dictionaries managed as governed configuration, not ad hoc code edits
- Replay-safe ingestion with idempotency keys/checksums
- Monitoring for validation-failure rates, suspicious-rate drift, and parser error spikes

## Bottom Line

The chosen source shapes are intentionally realistic and biased toward auditability over optimistic assumptions.  
The current parser set provides a defensible ingestion core, but long-term reliability depends on strict schema-contract governance with source owners.
