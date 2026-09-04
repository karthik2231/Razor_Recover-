/**
 * RazorRecover AI — Dashboard SPA
 *
 * Premium FinTech UI with Real-Time State, Live Metrics,
 * Human-in-the-Loop Review Queue & Developer Simulation.
 */

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  NavLink,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart2,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  FlaskConical,
  HelpCircle,
  Layers,
  LayoutDashboard,
  Link as LinkIcon,
  ListChecks,
  Percent,
  PieChart,
  PlusCircle,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import { api } from "./api";

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

const money = (n) =>
  n == null
    ? "—"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 0,
      }).format(n);

const label = (value) => (value ? value.replaceAll("_", " ") : "—");

// ---------------------------------------------------------------------------
// DataContext — Shared State Provider
// ---------------------------------------------------------------------------

const DataContext = createContext(null);

function DataProvider({ children }) {
  const [state, setState] = useState({
    loading: true,
    error: "",
    cases: [],
    metrics: {},
    audit: [],
  });

  const load = async () => {
    setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const [c, m, a] = await Promise.all([
        api.cases(),
        api.metrics(),
        api.audit(),
      ]);
      setState({
        loading: false,
        error: "",
        cases: c.cases || [],
        metrics: m,
        audit: a.entries || [],
      });
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: e.message }));
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <DataContext.Provider value={{ ...state, load }}>
      {children}
    </DataContext.Provider>
  );
}

function useAppData() {
  return useContext(DataContext);
}

// ---------------------------------------------------------------------------
// Shared Components & Badges
// ---------------------------------------------------------------------------

function Badge({ value }) {
  const v = value || "—";
  const cls = /CAPTURED|CREATED|APPROVED|ALLOW/.test(v)
    ? "good"
    : /BLOCK|DENY|FAILED|REJECT/.test(v)
    ? "bad"
    : /REVIEW|PENDING/.test(v)
    ? "warn"
    : "neutral";
  return <span className={`badge ${cls}`}>{label(v)}</span>;
}

function Shell({ children }) {
  return (
    <div className="shell">
      <aside>
        <div className="brand">
          <div className="brand-icon">
            <Zap size={20} />
          </div>
          <span>
            RazorRecover
            <small>AI PAYMENT RECOVERY</small>
          </span>
        </div>
        <nav>
          <NavLink to="/">
            <LayoutDashboard size={18} />
            <span>Dashboard</span>
          </NavLink>
          <NavLink to="/analytics">
            <BarChart2 size={18} />
            <span>Analytics</span>
          </NavLink>
          <NavLink to="/create">
            <PlusCircle size={18} />
            <span>Create Payment</span>
          </NavLink>
          <NavLink to="/cases">
            <ListChecks size={18} />
            <span>Webhook Cases</span>
          </NavLink>
          <NavLink to="/test">
            <FlaskConical size={18} />
            <span>Developer Test</span>
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          <div className="mode-badge">
            <span className="mode-dot"></span>
            <span>Razorpay Test Mode</span>
          </div>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <strong>Recovery Operations Control</strong>
            <p>AI recommends · Policy controls · Razorpay confirms</p>
          </div>
          <div className="header-status">
            <span className="status-pill">
              <ShieldCheck size={14} /> Active Engine
            </span>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}

function Notice({ error }) {
  if (!error) return null;
  return (
    <div className="error">
      <AlertTriangle size={16} style={{ display: "inline", verticalAlign: "middle", marginRight: 6 }} />
      Unable to load backend data: {error}. Check if FastAPI is running on port 8000.
    </div>
  );
}

function CasesTable({ cases, compact = false }) {
  const nav = useNavigate();
  const rows = compact ? cases.slice(0, 6) : cases;

  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th>Case ID</th>
            <th>Source</th>
            <th>Order ID</th>
            <th>Amount</th>
            <th>Failure Reason</th>
            <th>Score</th>
            <th>AI Action</th>
            <th>Policy</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.case_id}>
              <td>
                <strong style={{ fontFamily: "monospace", fontSize: 12 }}>{c.case_id}</strong>
              </td>
              <td>
                <Badge value={c.source === "simulation" ? "SIMULATED" : "WEBHOOK"} />
              </td>
              <td>{c.order_id || "—"}</td>
              <td>
                <strong>{money(c.amount_rupees)}</strong>
                {c.amount_rupees > 25000 && (
                  <span style={{ marginLeft: 6, fontSize: 10, padding: "2px 6px", background: "rgba(139, 92, 246, 0.15)", color: "#7c3aed", borderRadius: 4, fontWeight: 700 }}>
                    HIGH VALUE
                  </span>
                )}
              </td>
              <td>{label(c.failure_reason)}</td>
              <td>
                <span style={{ fontWeight: 700, color: c.recovery_score >= 70 ? "#059669" : "#d97706" }}>
                  {c.recovery_score ?? "—"}
                </span>
              </td>
              <td>{label(c.recommended_action)}</td>
              <td>
                <Badge value={c.policy_decision} />
              </td>
              <td>
                <Badge value={c.lifecycle_status} />
              </td>
              <td>
                <button
                  className="link"
                  onClick={() => nav(`/cases/${c.case_id}`)}
                >
                  View Details →
                </button>
              </td>
            </tr>
          ))}
          {!cases.length && (
            <tr>
              <td colSpan="10" className="empty">
                No cases matching criteria found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard Page
// ---------------------------------------------------------------------------

function Dashboard() {
  const d = useAppData();

  // All stats derived from d.cases (SQLite DB) for consistency
  const pendingReview = d.cases.filter((c) => c.lifecycle_status === "PENDING_REVIEW").length;
  const linksCreated = d.cases.filter((c) =>
    ["LINK_CREATED", "PAYMENT_CAPTURED"].includes(c.lifecycle_status)
  ).length;
  const capturedCount = d.cases.filter((c) => c.lifecycle_status === "PAYMENT_CAPTURED").length;

  const cards = [
    { title: "Total Cases", value: d.cases.length, icon: Layers, color: "indigo" },
    { title: "Failed Payments", value: d.cases.length, icon: AlertTriangle, color: "rose" },
    { title: "AI Auto-Approved", value: d.cases.filter((c) => c.review_status === "APPROVE").length, icon: Sparkles, color: "emerald" },
    { title: "Pending Review", value: pendingReview, icon: Clock, color: "amber" },
    { title: "Payment Links", value: linksCreated, icon: LinkIcon, color: "cyan" },
    { title: "Confirmed Captured", value: capturedCount, icon: CheckCircle2, color: "emerald" },
  ];

  return (
    <section>
      <div className="pagehead">
        <div>
          <h1>Revenue Recovery Dashboard</h1>
          <p>Real-time analytics and autonomous agent recovery status.</p>
        </div>
        <button onClick={d.load}>
          <RefreshCw size={14} />
          <span>Refresh Data</span>
        </button>
      </div>
      <Notice error={d.error} />
      <div className="stats">
        {cards.map((c) => {
          const Icon = c.icon;
          return (
            <div className="card" key={c.title}>
              <div className="card-header">
                <span>{c.title}</span>
                <div className={`card-icon-wrap ${c.color}`}>
                  <Icon size={18} />
                </div>
              </div>
              <strong>{c.value ?? "—"}</strong>
            </div>
          );
        })}
      </div>
      <h2>Recent Live Cases</h2>
      {d.loading ? (
        <p style={{ color: "#64748b" }}>Loading recovery cases…</p>
      ) : (
        <CasesTable cases={d.cases} compact />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Cases List Page
// ---------------------------------------------------------------------------

function Cases() {
  const d = useAppData();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("ALL");

  const FILTER_OPTIONS = [
    "ALL",
    "AUTO APPROVED",
    "HUMAN REVIEW",
    "BLOCKED",
    "LINK CREATED",
    "PAYMENT CAPTURED",
  ];

  const filtered = useMemo(() => {
    return d.cases.filter((c) => {
      const text = Object.values(c).join(" ").toLowerCase();
      const matchesSearch = !q || text.includes(q.toLowerCase());

      const filterMap = {
        "AUTO APPROVED": c.review_status === "APPROVE",
        "HUMAN REVIEW": c.lifecycle_status === "PENDING_REVIEW",
        BLOCKED: c.lifecycle_status === "POLICY_BLOCKED",
        "LINK CREATED": c.lifecycle_status === "LINK_CREATED",
        "PAYMENT CAPTURED": c.lifecycle_status === "PAYMENT_CAPTURED",
      };

      return matchesSearch && (filter === "ALL" || filterMap[filter]);
    });
  }, [d.cases, q, filter]);

  return (
    <section>
      <div className="pagehead">
        <div>
          <h1>Webhook Recovery Cases</h1>
          <p>Transaction cases ingested via Razorpay webhooks and developer simulation.</p>
        </div>
        <button onClick={d.load}>
          <RefreshCw size={14} />
          <span>Refresh</span>
        </button>
      </div>
      <Notice error={d.error} />
      <div className="filters">
        <div className="search-input-wrap">
          <Search size={16} />
          <input
            placeholder="Search by Case ID, Order ID, or Failure reason…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          {FILTER_OPTIONS.map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
      </div>
      {d.loading ? <p style={{ color: "#64748b" }}>Loading cases…</p> : <CasesTable cases={filtered} />}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Case Details & Action View
// ---------------------------------------------------------------------------

function Details() {
  const { id } = useParams();
  const d = useAppData();
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [link, setLink] = useState(null);
  const [sync, setSync] = useState(null);

  const c = d.cases.find((x) => x.case_id === id);
  const audit = d.audit.find(
    (x) => x.transaction_id === id && x.event_type === "RECOVERY_ANALYSIS"
  );

  const run = async (action) => {
    setWorking(true);
    setError("");
    try {
      if (action === "link") {
        setLink(await api.recoveryLink(id));
      } else if (action === "sync") {
        setSync(await api.syncRecoveryPayment(id));
      } else if (action === "execute") {
        await api.executeCase(id);
      } else {
        await api.reviewCase(id, action);
      }
      await d.load();
    } catch (e) {
      setError(e.message);
    } finally {
      setWorking(false);
    }
  };

  if (d.loading) return <section>Loading case details…</section>;
  if (!c)
    return (
      <section>
        <h1>Case Unavailable</h1>
        <p className="sub">This case ID was not found in the SQLite database.</p>
      </section>
    );

  const canReview = c.lifecycle_status === "PENDING_REVIEW";
  const canExecute =
    c.lifecycle_status === "APPROVED" &&
    c.recovery_link_status === "NOT_REQUESTED";

  const opportunityLevel =
    c.opportunity ||
    (c.recovery_score >= 70 ? "HIGH" : c.recovery_score >= 40 ? "MEDIUM" : c.recovery_score != null ? "LOW" : "—");

  const steps = [
    ["1. Payment Failure Triggered", label(c.failure_reason)],
    ["2. Opportunity Scoring", `Score: ${c.recovery_score ?? "—"} / 100 · Opportunity: ${opportunityLevel}`],
    [
      "3. Gemini AI Analysis",
      `Recommended: ${audit?.recommendation?.action || c.recommended_action || "—"} (Confidence: ${
        Math.round((audit?.recommendation?.confidence || 0) * 100)
      }%)`,
    ],
    ["4. Policy Engine Verdict", c.policy_reason || c.policy_decision],
    [
      "5. Review & Authorization Gate",
      c.review_status === "APPROVE"
        ? (c.lifecycle_status === "LINK_CREATED" && !c.reviewed_at
          ? "Approved via AI Auto-Approval"
          : "Approved by Reviewer")
        : c.review_status === "REJECT" || c.lifecycle_status === "REJECTED"
        ? `Rejected by Reviewer${c.review_note ? `: "${c.review_note}"` : ""}`
        : c.lifecycle_status === "POLICY_BLOCKED"
        ? "Blocked by Policy Engine"
        : "Pending Reviewer Action",
    ],
    [
      "6. Razorpay Link Execution",
      `${label(c.recovery_link_status)}${c.recovery_link_id ? ` · Link ID: ${c.recovery_link_id}` : ""}`,
    ],
  ];

  return (
    <section>
      <div className="pagehead">
        <div>
          <h1>
            Case {id}{" "}
            <Badge value={c.source === "simulation" ? "SIMULATED" : "WEBHOOK"} />
          </h1>
          <p>
            {c.source === "simulation"
              ? "Developer simulation through standard recovery pipeline."
              : canReview
              ? "Action required: Human review authorization queue."
              : "Full case state and audit history."}
          </p>
        </div>

        <div style={{ display: "flex", gap: 10 }}>
          {canReview && (
            <>
              <button className="btn-success" onClick={() => run("approve")} disabled={working}>
                <CheckCircle2 size={16} /> Approve
              </button>
              <button className="btn-danger" onClick={() => run("reject")} disabled={working}>
                <ShieldAlert size={16} /> Reject
              </button>
            </>
          )}

          {canExecute && (
            <button className="btn-primary" onClick={() => run("execute")} disabled={working}>
              <LinkIcon size={16} /> {working ? "Creating Link…" : "Create Recovery Link"}
            </button>
          )}

          {c.lifecycle_status === "LINK_CREATED" && (
            <>
              <button onClick={() => run("link")} disabled={working}>
                <LinkIcon size={16} /> {working ? "Fetching…" : "Get Link URL"}
              </button>
              <button className="btn-primary" onClick={() => run("sync")} disabled={working}>
                <RefreshCw size={16} /> Sync Status
              </button>
            </>
          )}
        </div>
      </div>

      <Notice error={error} />

      {sync && (
        <div className="result">
          <strong>
            {sync.synced ? "✓ Payment captured and synced successfully" : "Payment not captured yet on Razorpay"}
          </strong>
          <p>{sync.payment_link_status || sync.detail}</p>
        </div>
      )}

      {link?.payment_link_url && (
        <div className="result">
          <strong>Razorpay Test Mode Recovery Link</strong>
          <p>Link ID: {link.payment_link_id}</p>
          <a
            className="openlink"
            href={link.payment_link_url}
            target="_blank"
            rel="noreferrer"
          >
            Open Recovery Payment Link <ExternalLink size={14} />
          </a>
        </div>
      )}

      <div className="detailgrid">
        <div className="card">
          <span>Current Lifecycle State</span>
          <div style={{ marginTop: 8 }}>
            <Badge value={c.lifecycle_status} />
          </div>
        </div>
        <div className="card">
          <span>Transaction Amount</span>
          <strong>{money(c.amount_rupees)}</strong>
        </div>
      </div>

      <div className="timeline">
        <h3 style={{ marginBottom: 16, fontSize: 16, fontWeight: 800 }}>Recovery Pipeline Milestones</h3>
        {steps.map(([title, body], i) => (
          <div className="step" key={title}>
            <div className="step-node">{i + 1}</div>
            <div>
              <strong>{title}</strong>
              <p>{body}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Create Initial Payment
// ---------------------------------------------------------------------------

function Create() {
  const [form, setForm] = useState({
    amount: "500",
    customer_name: "Demo Customer",
    customer_email: "demo@example.com",
    customer_contact: "8610169138",
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const change = (e) => setForm({ ...form, [e.target.name]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(
        await api.createNormalPayment({ ...form, amount: Number(form.amount) })
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section>
      <h1>Create Initial Test Payment</h1>
      <p className="sub">
        Generates a standard Razorpay Test Mode payment link to simulate initial customer checkout.
      </p>
      <form className="form" onSubmit={submit}>
        <label>
          Amount (INR)
          <input
            name="amount"
            type="number"
            min="1"
            step="0.01"
            value={form.amount}
            onChange={change}
            required
          />
        </label>
        <label>
          Customer Name
          <input
            name="customer_name"
            value={form.customer_name}
            onChange={change}
            required
          />
        </label>
        <label>
          Customer Email
          <input
            name="customer_email"
            type="email"
            value={form.customer_email}
            onChange={change}
            required
          />
        </label>
        <label>
          Customer Contact Number
          <input
            name="customer_contact"
            value={form.customer_contact}
            onChange={change}
            required
          />
        </label>
        <button className="btn-primary" disabled={loading}>
          {loading ? "Generating Link…" : "Create Test Payment Link"}
        </button>
        <Notice error={error} />
        {result && (
          <div className="result">
            <strong>Initial Test Mode Payment Link Created</strong>
            <p>Transaction ID: {result.transaction_id}</p>
            <p>Reference ID: {result.reference_id}</p>
            {result.payment_link_url && (
              <a
                className="openlink"
                href={result.payment_link_url}
                target="_blank"
                rel="noreferrer"
              >
                Open Checkout Link <ExternalLink size={14} />
              </a>
            )}
          </div>
        )}
      </form>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Developer Simulation Page
// ---------------------------------------------------------------------------

const FAILURE_REASONS = [
  "payment_failed",
  "bank_timeout",
  "upi_failure",
  "network_error",
  "card_declined",
  "authentication_failed",
  "insufficient_funds",
];

function Test() {
  const [amount, setAmount] = useState(500);
  const [reason, setReason] = useState("bank_timeout");
  const [firstAttempt, setFirstAttempt] = useState(true);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const data = await api.simulateFailure({
        amount: Number(amount),
        failure_reason: reason,
        previous_recovery_attempts: firstAttempt ? 0 : 1,
      });
      setResult(JSON.stringify(data, null, 2));
    } catch (e) {
      setResult(`Simulation failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section>
      <h1>Developer Failure Simulation</h1>
      <p className="sub">
        Injects a synthetic failed transaction into the live pipeline to test Gemini AI reasoning and policy guardrails.
      </p>
      <div className="form">
        <label>
          Transaction Amount (INR)
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </label>
        <label>
          Failure Reason Code
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            {FAILURE_REASONS.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={firstAttempt}
            onChange={(e) => setFirstAttempt(e.target.checked)}
          />
          First Recovery Attempt (Required for AI Auto-Approval)
        </label>
        <button className="btn-primary" onClick={run} disabled={loading}>
          <Zap size={16} />
          {loading ? "Running AI Pipeline…" : "Simulate Failed Payment"}
        </button>
        {result && (
          <div style={{ marginTop: 14 }}>
            <h4 style={{ fontSize: 13, marginBottom: 8, color: "#475569" }}>Pipeline Execution Payload:</h4>
            <pre>{result}</pre>
          </div>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Analytics Page
// ---------------------------------------------------------------------------

const DIST_COLORS = [
  "#6366f1", "#06b6d4", "#f59e0b", "#10b981", "#f43f5e",
  "#8b5cf6", "#ec4899", "#14b8a6", "#ef4444", "#3b82f6",
];

function Analytics() {
  const d = useAppData();
  const m = d.metrics;

  // ---- ALL stats derived from d.cases (SQLite DB — single source of truth) ----
  const totalCases = d.cases.length;
  const autoApproved = d.cases.filter((c) => c.review_status === "APPROVE").length;
  const pendingReview = d.cases.filter((c) => c.lifecycle_status === "PENDING_REVIEW").length;
  const linkCreated = d.cases.filter((c) => c.lifecycle_status === "LINK_CREATED").length;
  const capturedCases = d.cases.filter((c) => c.lifecycle_status === "PAYMENT_CAPTURED");
  const captured = capturedCases.length;
  const blocked = d.cases.filter((c) => c.lifecycle_status === "POLICY_BLOCKED" || c.lifecycle_status === "REJECTED").length;

  // Revenue: compute directly from case amounts (amount_rupees field)
  const totalRevAtRisk = useMemo(
    () => d.cases.reduce((sum, c) => sum + (c.amount_rupees || 0), 0),
    [d.cases]
  );
  const recoveredAmt = useMemo(
    () => capturedCases.reduce((sum, c) => sum + (c.amount_rupees || 0), 0),
    [capturedCases]
  );
  const recoveryRate = totalRevAtRisk > 0 ? Math.round((recoveredAmt / totalRevAtRisk) * 10000) / 100 : 0;

  // Approved vs blocked amounts from case data
  const approvedAmt = useMemo(
    () => d.cases
      .filter((c) => ["APPROVED", "LINK_CREATED", "PAYMENT_CAPTURED"].includes(c.lifecycle_status))
      .reduce((sum, c) => sum + (c.amount_rupees || 0), 0),
    [d.cases]
  );
  const blockedAmt = useMemo(
    () => d.cases
      .filter((c) => ["POLICY_BLOCKED", "REJECTED"].includes(c.lifecycle_status))
      .reduce((sum, c) => sum + (c.amount_rupees || 0), 0),
    [d.cases]
  );

  // ---- Funnel data (all from cases) ----
  const approvedTotal = d.cases.filter((c) =>
    ["APPROVED", "LINK_CREATED", "PAYMENT_CAPTURED"].includes(c.lifecycle_status)
  ).length;
  const linksTotal = d.cases.filter((c) =>
    ["LINK_CREATED", "PAYMENT_CAPTURED"].includes(c.lifecycle_status)
  ).length;

  const funnel = [
    { label: "Total Cases", count: totalCases, color: "indigo" },
    { label: "Policy Approved", count: approvedTotal, color: "cyan" },
    { label: "Links Created", count: linksTotal, color: "amber" },
    { label: "Payments Captured", count: captured, color: "emerald" },
  ];
  const funnelMax = Math.max(...funnel.map((f) => f.count), 1);

  // ---- Failure reason distribution (from cases) ----
  const reasonCounts = useMemo(() => {
    const map = {};
    d.cases.forEach((c) => {
      const r = c.failure_reason || "unknown";
      map[r] = (map[r] || 0) + 1;
    });
    return Object.entries(map)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
  }, [d.cases]);

  // ---- AI recommendation action distribution (from cases) ----
  const aiActions = useMemo(() => {
    const map = {};
    d.cases.forEach((c) => {
      const a = c.recommended_action || "UNKNOWN";
      map[a] = (map[a] || 0) + 1;
    });
    return Object.entries(map).sort((a, b) => b[1] - a[1]);
  }, [d.cases]);

  // ---- Policy decision distribution (from cases) ----
  const policyDist = useMemo(() => {
    const map = {};
    d.cases.forEach((c) => {
      const p = c.policy_decision || "UNKNOWN";
      map[p] = (map[p] || 0) + 1;
    });
    return Object.entries(map).sort((a, b) => b[1] - a[1]);
  }, [d.cases]);

  // ---- Lifecycle distribution (from cases) ----
  const lifecycleDist = useMemo(() => {
    const map = {};
    d.cases.forEach((c) => {
      const s = c.lifecycle_status || "UNKNOWN";
      map[s] = (map[s] || 0) + 1;
    });
    return Object.entries(map).sort((a, b) => b[1] - a[1]);
  }, [d.cases]);

  // ---- Recent audit activity (last 12) ----
  const recentAudit = useMemo(() => {
    return (d.audit || []).slice(0, 12);
  }, [d.audit]);

  // ---- Amount-range breakdown (from cases) ----
  const amountBuckets = useMemo(() => {
    const buckets = [
      { label: "₹0 – ₹500", min: 0, max: 500, count: 0 },
      { label: "₹501 – ₹1,000", min: 501, max: 1000, count: 0 },
      { label: "₹1,001 – ₹5,000", min: 1001, max: 5000, count: 0 },
      { label: "₹5,001+", min: 5001, max: Infinity, count: 0 },
    ];
    d.cases.forEach((c) => {
      const amt = c.amount_rupees || 0;
      const b = buckets.find((b) => amt >= b.min && amt <= b.max);
      if (b) b.count++;
    });
    return buckets;
  }, [d.cases]);

  const eventTypeLabel = (t) => {
    const map = {
      RECOVERY_ANALYSIS: "AI Analysis",
      RECOVERY_EXECUTED: "Link Created",
      RECOVERY_SIMULATED: "Simulated",
      WEBHOOK_PAYMENT_CAPTURED: "Payment Captured",
      REVIEWER_DECISION: "Review Decision",
      EXECUTION_FAILED: "Execution Failed",
      BATCH_ANALYSIS: "Batch Analysis",
    };
    return map[t] || label(t);
  };

  const eventTypeColor = (t) => {
    if (/CAPTURED/.test(t)) return "#10b981";
    if (/EXECUTED|SIMULATED/.test(t)) return "#06b6d4";
    if (/FAILED/.test(t)) return "#f43f5e";
    if (/REVIEWER/.test(t)) return "#f59e0b";
    return "#6366f1";
  };

  if (d.loading) {
    return (
      <section>
        <h1>Analytics</h1>
        <p style={{ color: "#64748b", marginTop: 12 }}>Loading analytics data…</p>
      </section>
    );
  }

  return (
    <section>
      <div className="pagehead">
        <div>
          <h1>Recovery Analytics</h1>
          <p>
            Pipeline performance and revenue impact — all data from live recovery cases.
          </p>
        </div>
        <button onClick={d.load}>
          <RefreshCw size={14} />
          <span>Refresh</span>
        </button>
      </div>
      <Notice error={d.error} />

      {/* ---- Hero Banner ---- */}
      <div className="analytics-hero">
        <div className="hero-left">
          <h3>Revenue Recovery</h3>
          <div className="big-stat">{money(recoveredAmt)}</div>
          <p>
            captured from {money(totalRevAtRisk)} across {totalCases} cases
          </p>
          <div className="hero-progress-wrap">
            <div className="progress-labels">
              <span>Recovery Rate</span>
              <span>{recoveryRate}%</span>
            </div>
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{ width: `${Math.min(recoveryRate, 100)}%` }}
              />
            </div>
          </div>
        </div>
        <div className="hero-right">
          <div className="hero-subcard">
            <span>Total Cases</span>
            <strong>{totalCases}</strong>
          </div>
          <div className="hero-subcard">
            <span>Auto-Approved</span>
            <strong>{autoApproved}</strong>
          </div>
          <div className="hero-subcard">
            <span>Approved Value</span>
            <strong>{money(approvedAmt)}</strong>
          </div>
          <div className="hero-subcard">
            <span>Blocked Value</span>
            <strong>{money(blockedAmt)}</strong>
          </div>
        </div>
      </div>

      {/* ---- Recovery Funnel + Failure Reasons ---- */}
      <div className="analytics-grid">
        <div className="chart-card">
          <div className="chart-card-header">
            <h3>
              <TrendingUp size={18} color="#6366f1" />
              Recovery Funnel
            </h3>
            <span>Pipeline stages</span>
          </div>
          <div className="funnel-list">
            {funnel.map((f) => (
              <div className="funnel-row" key={f.label}>
                <div className="funnel-label">{f.label}</div>
                <div className="funnel-bar-bg">
                  <div
                    className={`funnel-bar-fill ${f.color}`}
                    style={{ width: `${(f.count / funnelMax) * 100}%` }}
                  />
                </div>
                <div className="funnel-count">{f.count}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="chart-card">
          <div className="chart-card-header">
            <h3>
              <AlertTriangle size={18} color="#f59e0b" />
              Failure Reasons
            </h3>
            <span>Top failure causes</span>
          </div>
          <div className="dist-list">
            {reasonCounts.length === 0 && (
              <p style={{ color: "#94a3b8", fontSize: 13 }}>No cases to analyze.</p>
            )}
            {reasonCounts.map(([name, count], i) => (
              <div className="dist-item" key={name}>
                <div className="dist-item-left">
                  <div
                    className="dist-dot"
                    style={{ background: DIST_COLORS[i % DIST_COLORS.length] }}
                  />
                  <span className="dist-name">{label(name)}</span>
                </div>
                <div className="dist-item-right">
                  <span className="dist-count">{count}</span>
                  <span className="dist-pct">
                    {totalCases > 0 ? Math.round((count / totalCases) * 100) : 0}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ---- AI Actions + Policy Decisions ---- */}
      <div className="analytics-grid">
        <div className="chart-card">
          <div className="chart-card-header">
            <h3>
              <Sparkles size={18} color="#06b6d4" />
              AI Recommendations
            </h3>
            <span>Action distribution</span>
          </div>
          <div className="dist-list">
            {aiActions.length === 0 && (
              <p style={{ color: "#94a3b8", fontSize: 13 }}>No AI recommendations yet.</p>
            )}
            {aiActions.map(([name, count], i) => (
              <div className="dist-item" key={name}>
                <div className="dist-item-left">
                  <div
                    className="dist-dot"
                    style={{ background: DIST_COLORS[i % DIST_COLORS.length] }}
                  />
                  <span className="dist-name">{label(name)}</span>
                </div>
                <div className="dist-item-right">
                  <span className="dist-count">{count}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="chart-card">
          <div className="chart-card-header">
            <h3>
              <ShieldCheck size={18} color="#10b981" />
              Policy Decisions
            </h3>
            <span>Guardrail outcomes</span>
          </div>
          <div className="dist-list">
            {policyDist.length === 0 && (
              <p style={{ color: "#94a3b8", fontSize: 13 }}>No policy data.</p>
            )}
            {policyDist.map(([name, count], i) => (
              <div className="dist-item" key={name}>
                <div className="dist-item-left">
                  <Badge value={name} />
                </div>
                <div className="dist-item-right">
                  <span className="dist-count">{count}</span>
                  <span className="dist-pct">
                    {totalCases > 0 ? Math.round((count / totalCases) * 100) : 0}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ---- Lifecycle Status + Amount Buckets ---- */}
      <div className="analytics-grid">
        <div className="chart-card">
          <div className="chart-card-header">
            <h3>
              <Activity size={18} color="#8b5cf6" />
              Lifecycle Status
            </h3>
            <span>Current case states</span>
          </div>
          <div className="dist-list">
            {lifecycleDist.length === 0 && (
              <p style={{ color: "#94a3b8", fontSize: 13 }}>No lifecycle data.</p>
            )}
            {lifecycleDist.map(([name, count], i) => (
              <div className="dist-item" key={name}>
                <div className="dist-item-left">
                  <Badge value={name} />
                </div>
                <div className="dist-item-right">
                  <span className="dist-count">{count}</span>
                  <span className="dist-pct">
                    {totalCases > 0 ? Math.round((count / totalCases) * 100) : 0}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="chart-card">
          <div className="chart-card-header">
            <h3>
              <PieChart size={18} color="#f59e0b" />
              Amount Distribution
            </h3>
            <span>Transaction value ranges</span>
          </div>
          <div className="funnel-list">
            {amountBuckets.map((b, i) => (
              <div className="funnel-row" key={b.label}>
                <div className="funnel-label">{b.label}</div>
                <div className="funnel-bar-bg">
                  <div
                    className={`funnel-bar-fill ${["indigo", "cyan", "amber", "emerald"][i]}`}
                    style={{
                      width: `${totalCases > 0 ? (b.count / totalCases) * 100 : 0}%`,
                    }}
                  />
                </div>
                <div className="funnel-count">{b.count}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ---- KPI Summary Cards ---- */}
      <h2>Key Performance Indicators</h2>
      <div className="stats">
        {[
          { title: "Webhook Cases", value: d.cases.filter((c) => c.source === "webhook").length, icon: Zap, color: "indigo" },
          { title: "Simulation Cases", value: d.cases.filter((c) => c.source === "simulation").length, icon: FlaskConical, color: "cyan" },
          { title: "Pending Review", value: pendingReview, icon: Clock, color: "amber" },
          { title: "Links Created", value: linksTotal, icon: LinkIcon, color: "emerald" },
          { title: "Payments Captured", value: captured, icon: CheckCircle2, color: "emerald" },
          { title: "Blocked Cases", value: blocked, icon: ShieldAlert, color: "rose" },
        ].map((c) => {
          const Icon = c.icon;
          return (
            <div className="card" key={c.title}>
              <div className="card-header">
                <span>{c.title}</span>
                <div className={`card-icon-wrap ${c.color}`}>
                  <Icon size={18} />
                </div>
              </div>
              <strong>{c.value}</strong>
            </div>
          );
        })}
      </div>

      {/* ---- Recent Audit Timeline ---- */}
      <h2>Recent Activity</h2>
      <div className="chart-card" style={{ marginBottom: 32 }}>
        <div className="chart-card-header">
          <h3>
            <Clock size={18} color="#64748b" />
            Audit Trail
          </h3>
          <span>Last {recentAudit.length} events</span>
        </div>
        {recentAudit.length === 0 ? (
          <p style={{ color: "#94a3b8", fontSize: 13, padding: "8px 0" }}>
            No audit entries recorded yet. Trigger a webhook or simulation to start tracking.
          </p>
        ) : (
          <div className="audit-timeline">
            {recentAudit.map((entry) => (
              <div className="audit-event" key={entry.audit_id}>
                <div
                  className="audit-event-dot"
                  style={{ background: eventTypeColor(entry.event_type) }}
                />
                <div className="audit-event-body">
                  <div className="audit-event-header">
                    <strong>{eventTypeLabel(entry.event_type)}</strong>
                    <span className="audit-event-time">
                      {entry.timestamp
                        ? new Date(entry.timestamp).toLocaleString("en-IN", {
                            dateStyle: "medium",
                            timeStyle: "short",
                          })
                        : "—"}
                    </span>
                  </div>
                  <p>
                    {entry.transaction_id && (
                      <span style={{ fontFamily: "monospace", fontSize: 12, marginRight: 8 }}>
                        {entry.transaction_id}
                      </span>
                    )}
                    {entry.amount_rupees > 0 && <span>{money(entry.amount_rupees)}</span>}
                    {entry.final_action && (
                      <span style={{ marginLeft: 8 }}>
                        → <Badge value={entry.final_action} />
                      </span>
                    )}
                    {entry.decision && (
                      <span style={{ marginLeft: 8 }}>
                        <Badge value={entry.decision.toUpperCase()} />
                      </span>
                    )}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// App Entry
// ---------------------------------------------------------------------------

export default function App() {
  return (
    <DataProvider>
      <Shell>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/create" element={<Create />} />
          <Route path="/cases" element={<Cases />} />
          <Route path="/cases/:id" element={<Details />} />
          <Route path="/test" element={<Test />} />
        </Routes>
      </Shell>
    </DataProvider>
  );
}

