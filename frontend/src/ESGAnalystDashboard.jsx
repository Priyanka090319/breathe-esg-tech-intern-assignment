import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleX,
  Database,
  Eye,
  FileUp,
  Lock,
  ShieldCheck,
} from "lucide-react";

const API_BASE = "/api/ingestion";

const SOURCE_TYPES = [
  { value: "sap_export", label: "SAP CSV Export" },
  { value: "utility_portal", label: "Utility Portal CSV" },
  { value: "concur_flight_json", label: "Concur Flight JSON" },
];

const STATUS = {
  INGESTED: "INGESTED",
  FLAGGED_SUSPICIOUS: "FLAGGED_SUSPICIOUS",
  FAILED_VALIDATION: "FAILED_VALIDATION",
  ANALYST_APPROVED: "ANALYST_APPROVED",
  LOCKED_FOR_AUDIT: "LOCKED_FOR_AUDIT",
};

const MOCK_ROWS = [
  {
    id: 101,
    organization: 1,
    ingestion_source: { id: 1, name: "SAP Export - DE_Plant", source_type: "SAP" },
    raw_payload_id: 8801,
    scope: "SCOPE_1",
    scope_display: "Scope 1 (Direct)",
    category: "Stationary Combustion | Plant:DE_01",
    original_value: "5000.00000000",
    original_unit: "L",
    normalized_value: "13.40000000",
    normalized_unit: "MTCO2E",
    status: STATUS.INGESTED,
    status_display: "Ingested",
    status_note: "Parsed successfully from SAP export",
    activity_date: "2026-05-20",
    approved_by: null,
    approved_at: null,
    locked_by: null,
    locked_at: null,
    created_at: "2026-05-27T10:00:00Z",
    updated_at: "2026-05-27T10:00:00Z",
  },
  {
    id: 102,
    organization: 1,
    ingestion_source: { id: 2, name: "Utility Portal - Meter Batch", source_type: "UTILITY" },
    raw_payload_id: 8802,
    scope: "SCOPE_2",
    scope_display: "Scope 2 (Energy Indirect)",
    category: "ELECTRICITY_METER:MTR-77A",
    original_value: "93200.00000000",
    original_unit: "KWH",
    normalized_value: "93200.00000000",
    normalized_unit: "KWH",
    status: STATUS.FLAGGED_SUSPICIOUS,
    status_display: "Flagged Suspicious",
    status_note: "consumption spike >150% of historical average",
    activity_date: "2026-05-22",
    approved_by: null,
    approved_at: null,
    locked_by: null,
    locked_at: null,
    created_at: "2026-05-27T10:03:00Z",
    updated_at: "2026-05-27T10:03:00Z",
  },
  {
    id: 103,
    organization: 1,
    ingestion_source: { id: 3, name: "Concur Flights - API", source_type: "TRAVEL" },
    raw_payload_id: 8803,
    scope: "SCOPE_3",
    scope_display: "Scope 3 (Value Chain)",
    category: "Business Travel | Employee:E0922",
    original_value: "0.00000000",
    original_unit: "KM",
    normalized_value: "0.00000000",
    normalized_unit: "MTCO2E",
    status: STATUS.FAILED_VALIDATION,
    status_display: "Failed Validation",
    status_note: "unparseable date in upstream payload",
    activity_date: "2026-05-23",
    approved_by: null,
    approved_at: null,
    locked_by: null,
    locked_at: null,
    created_at: "2026-05-27T10:06:00Z",
    updated_at: "2026-05-27T10:06:00Z",
  },
  {
    id: 104,
    organization: 1,
    ingestion_source: { id: 1, name: "SAP Export - DE_Plant", source_type: "SAP" },
    raw_payload_id: 8804,
    scope: "SCOPE_1",
    scope_display: "Scope 1 (Direct)",
    category: "Mobile Combustion | Plant:DE_02",
    original_value: "1400.00000000",
    original_unit: "KG",
    normalized_value: "4.20000000",
    normalized_unit: "MTCO2E",
    status: STATUS.LOCKED_FOR_AUDIT,
    status_display: "Locked For Audit",
    status_note: "Approved and locked",
    activity_date: "2026-05-15",
    approved_by: 7,
    approved_at: "2026-05-26T14:30:00Z",
    locked_by: 7,
    locked_at: "2026-05-27T11:00:00Z",
    created_at: "2026-05-26T11:00:00Z",
    updated_at: "2026-05-27T11:00:00Z",
  },
];

const scopeBadgeClass = {
  SCOPE_1: "bg-slate-100 text-slate-700 border-slate-200",
  SCOPE_2: "bg-blue-50 text-blue-700 border-blue-200",
  SCOPE_3: "bg-purple-50 text-purple-700 border-purple-200",
};

const statusBadgeClass = {
  INGESTED: "bg-slate-100 text-slate-700 border-slate-200",
  FLAGGED_SUSPICIOUS: "bg-amber-50 text-amber-700 border-amber-200",
  FAILED_VALIDATION: "bg-rose-50 text-rose-700 border-rose-200",
  ANALYST_APPROVED: "bg-emerald-50 text-emerald-700 border-emerald-200",
  LOCKED_FOR_AUDIT: "bg-teal-50 text-teal-700 border-teal-200",
};

function formatValue(value, unit) {
  const numeric = Number(value || 0);
  return `${numeric.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${unit}`;
}

function SummaryCard({ title, value, icon: Icon, tone }) {
  const toneClass =
    tone === "warning"
      ? "bg-amber-50 border-amber-100 text-amber-800"
      : tone === "danger"
        ? "bg-rose-50 border-rose-100 text-rose-800"
        : tone === "success"
          ? "bg-emerald-50 border-emerald-100 text-emerald-800"
          : "bg-slate-50 border-slate-200 text-slate-800";

  return (
    <div className={`rounded-xl border px-4 py-3 ${toneClass}`}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide">{title}</p>
        <Icon className="h-4 w-4" />
      </div>
      <p className="mt-3 text-2xl font-semibold">{value}</p>
    </div>
  );
}

export default function ESGAnalystDashboard() {
  const [rows, setRows] = useState(MOCK_ROWS);
  const [selectedSourceType, setSelectedSourceType] = useState("sap_export");
  const [selectedFile, setSelectedFile] = useState(null);
  const [pastePayload, setPastePayload] = useState("");
  const [selectedRow, setSelectedRow] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [ingestionMessage, setIngestionMessage] = useState("");

  const summary = useMemo(() => {
    const pendingReview = rows.filter(
      (row) => row.status === STATUS.INGESTED || row.status === STATUS.FLAGGED_SUSPICIOUS
    ).length;
    const flagged = rows.filter((row) => row.status === STATUS.FLAGGED_SUSPICIOUS).length;
    const failed = rows.filter((row) => row.status === STATUS.FAILED_VALIDATION).length;
    const approvedLocked = rows.filter(
      (row) => row.status === STATUS.ANALYST_APPROVED || row.status === STATUS.LOCKED_FOR_AUDIT
    ).length;
    return { pendingReview, flagged, failed, approvedLocked };
  }, [rows]);

  async function refreshRows() {
    // DRF wiring: GET /api/ingestion/normalized-rows/?organization_id=1
    const response = await fetch(`${API_BASE}/normalized-rows/?organization_id=1`, {
      credentials: "include",
    });
    if (!response.ok) throw new Error("Unable to fetch normalized rows");
    const data = await response.json();
    setRows(Array.isArray(data) ? data : data.results || []);
  }

  async function approveRow(rowId) {
    setRows((prev) =>
      prev.map((row) =>
        row.id === rowId
          ? {
              ...row,
              status: STATUS.ANALYST_APPROVED,
              status_display: "Analyst Approved",
              approved_by: 999,
              approved_at: new Date().toISOString(),
            }
          : row
      )
    );

    // DRF wiring: POST /api/ingestion/normalized-rows/{id}/approve_row/
    await fetch(`${API_BASE}/normalized-rows/${rowId}/approve_row/?organization_id=1`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
  }

  async function lockApprovedRows() {
    setRows((prev) =>
      prev.map((row) =>
        row.status === STATUS.ANALYST_APPROVED
          ? {
              ...row,
              status: STATUS.LOCKED_FOR_AUDIT,
              status_display: "Locked For Audit",
              locked_by: 999,
              locked_at: new Date().toISOString(),
            }
          : row
      )
    );

    // DRF wiring: POST /api/ingestion/normalized-rows/lock_dataset/
    await fetch(`${API_BASE}/normalized-rows/lock_dataset/?organization_id=1`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
  }

  async function uploadIngestionFile() {
    if (!selectedFile && !pastePayload.trim()) {
      setIngestionMessage("Please select a file or paste payload text.");
      return;
    }

    setIsSubmitting(true);
    setIngestionMessage("");

    try {
      if (selectedSourceType === "concur_flight_json" && pastePayload.trim()) {
        // Example layout for custom JSON endpoint if added later.
        await fetch(`${API_BASE}/ingest/json/`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            organization_id: 1,
            source_type: "concur_flight_json",
            ingestion_source_id: 3,
            payload: JSON.parse(pastePayload),
          }),
        });
      } else {
        const formData = new FormData();
        formData.append("organization_id", "1");
        formData.append("ingestion_source_id", selectedSourceType === "sap_export" ? "1" : "2");
        formData.append("file_type", selectedSourceType);
        if (selectedFile) formData.append("file", selectedFile);
        if (pastePayload.trim()) {
          const blob = new Blob([pastePayload], { type: "text/plain" });
          formData.append("file", blob, "pasted_payload.txt");
        }

        // DRF wiring: POST /api/ingestion/ingest/file/
        const response = await fetch(`${API_BASE}/ingest/file/`, {
          method: "POST",
          credentials: "include",
          body: formData,
        });
        if (!response.ok) throw new Error("Ingestion upload failed");
      }

      setIngestionMessage("Ingestion submitted successfully.");
      await refreshRows();
    } catch (error) {
      setIngestionMessage(error.message || "Upload failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 p-6 text-slate-900">
      <div className="mx-auto max-w-7xl space-y-5">
        <header className="rounded-2xl border border-slate-200 bg-white px-6 py-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">ESG Analyst Audit Console</h1>
              <p className="mt-1 text-sm text-slate-500">
                Monitor, validate, approve, and lock emissions data with full lineage.
              </p>
            </div>
            <button
              type="button"
              onClick={lockApprovedRows}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <Lock className="h-4 w-4" />
              Lock Approved Rows for Audit
            </button>
          </div>
        </header>

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <SummaryCard title="Pending Review" value={summary.pendingReview} icon={Database} />
          <SummaryCard
            title="Flagged Suspicious"
            value={summary.flagged}
            icon={AlertTriangle}
            tone="warning"
          />
          <SummaryCard
            title="Failed Validation"
            value={summary.failed}
            icon={CircleX}
            tone="danger"
          />
          <SummaryCard
            title="Approved & Locked"
            value={summary.approvedLocked}
            icon={ShieldCheck}
            tone="success"
          />
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Multi-Source Ingestion</h2>
            <p className="text-xs text-slate-500">Routes to Django parser endpoints</p>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-1">
              <label className="mb-1 block text-xs font-medium text-slate-600">Source Type</label>
              <select
                value={selectedSourceType}
                onChange={(e) => setSelectedSourceType(e.target.value)}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none ring-0 focus:border-slate-400"
              >
                {SOURCE_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
              <label className="mt-4 block rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-center text-sm text-slate-600 hover:bg-slate-100">
                <FileUp className="mx-auto mb-2 h-5 w-5 text-slate-500" />
                <span className="font-medium">Drop file or browse</span>
                <input
                  type="file"
                  className="hidden"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                  accept=".csv,.json,.txt"
                />
                <p className="mt-1 text-xs text-slate-500">{selectedFile?.name || "No file selected"}</p>
              </label>
            </div>

            <div className="lg:col-span-2">
              <label className="mb-1 block text-xs font-medium text-slate-600">
                Paste payload (optional)
              </label>
              <textarea
                value={pastePayload}
                onChange={(e) => setPastePayload(e.target.value)}
                rows={9}
                placeholder="Paste CSV content or JSON payload here..."
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
              />
              <div className="mt-3 flex items-center justify-between">
                <p className="text-xs text-slate-500">{ingestionMessage}</p>
                <button
                  type="button"
                  disabled={isSubmitting}
                  onClick={uploadIngestionFile}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSubmitting ? "Submitting..." : "Ingest Data"}
                </button>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Audit Table</h2>
            <p className="text-xs text-slate-500">Inline actions are fully accessible</p>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
                <tr>
                  <th className="px-4 py-3">Source Lineage</th>
                  <th className="px-4 py-3">Scope</th>
                  <th className="px-4 py-3">Original - Normalized</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const canApprove =
                    row.status === STATUS.INGESTED || row.status === STATUS.FLAGGED_SUSPICIOUS;
                  return (
                    <tr key={row.id} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-800">{row.ingestion_source.name}</p>
                        <p className="text-xs text-slate-500">Payload #{row.raw_payload_id}</p>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex rounded-full border px-2 py-1 text-xs font-medium ${scopeBadgeClass[row.scope]}`}
                        >
                          {row.scope_display}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-slate-800">
                          {formatValue(row.original_value, row.original_unit)}
                        </p>
                        <p className="text-xs text-slate-500">
                          {formatValue(row.normalized_value, row.normalized_unit)}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          title={
                            row.status === STATUS.FLAGGED_SUSPICIOUS ? row.status_note : undefined
                          }
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs font-medium ${statusBadgeClass[row.status]}`}
                        >
                          {row.status === STATUS.ANALYST_APPROVED ||
                          row.status === STATUS.LOCKED_FOR_AUDIT ? (
                            <CheckCircle2 className="h-3.5 w-3.5" />
                          ) : row.status === STATUS.FLAGGED_SUSPICIOUS ? (
                            <AlertTriangle className="h-3.5 w-3.5" />
                          ) : row.status === STATUS.FAILED_VALIDATION ? (
                            <CircleX className="h-3.5 w-3.5" />
                          ) : null}
                          {row.status_display}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            disabled={!canApprove}
                            onClick={() => approveRow(row.id)}
                            className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            onClick={() => setSelectedRow(row)}
                            className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            <Eye className="h-3.5 w-3.5" />
                            Review
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {selectedRow ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-slate-900/35 p-4">
          <div className="w-full max-w-2xl rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-semibold text-slate-900">Row Metadata Review</h3>
              <button
                type="button"
                onClick={() => setSelectedRow(null)}
                className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-slate-500">Record ID</dt>
              <dd className="font-medium text-slate-800">{selectedRow.id}</dd>
              <dt className="text-slate-500">Source</dt>
              <dd className="font-medium text-slate-800">{selectedRow.ingestion_source.name}</dd>
              <dt className="text-slate-500">Category</dt>
              <dd className="font-medium text-slate-800">{selectedRow.category}</dd>
              <dt className="text-slate-500">Status Note</dt>
              <dd className="font-medium text-slate-800">{selectedRow.status_note || "-"}</dd>
              <dt className="text-slate-500">Approved At</dt>
              <dd className="font-medium text-slate-800">{selectedRow.approved_at || "-"}</dd>
              <dt className="text-slate-500">Locked At</dt>
              <dd className="font-medium text-slate-800">{selectedRow.locked_at || "-"}</dd>
            </dl>
          </div>
        </div>
      ) : null}
    </div>
  );
}
