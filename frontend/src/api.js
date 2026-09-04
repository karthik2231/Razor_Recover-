const base = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const token = import.meta.env.VITE_REVIEW_API_TOKEN;
async function request(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 45_000);
  try {
    const response = await fetch(`${base}${path}`, { ...options, signal: controller.signal, headers: { "Content-Type": "application/json", ...(token ? { "X-Review-Token": token } : {}), ...options.headers } });
    if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `Backend request failed (${response.status})`); }
    return response.json();
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Backend request timed out after 45 seconds. Check FastAPI and Gemini/Razorpay connectivity.");
    if (error instanceof TypeError) throw new Error("Cannot reach the backend. Start FastAPI on port 8000, then restart Vite.");
    throw error;
  } finally { clearTimeout(timer); }
}
export const api = {
  cases: () => request("/webhook-cases"),
  metrics: () => request("/recovery-metrics"),
  audit: () => request("/audit-trail?limit=500"),
  reviewCase: (caseId, decision) => request(`/webhook-cases/${encodeURIComponent(caseId)}/review`, { method: "POST", body: JSON.stringify({ decision, ...(decision === "approve" ? { approved_action: "CREATE_PAYMENT_LINK" } : {}) }) }),
  executeCase: (caseId) => request(`/webhook-cases/${encodeURIComponent(caseId)}/execute`, { method: "POST" }),
  recoveryLink: (caseId) => request(`/webhook-cases/${encodeURIComponent(caseId)}/payment-link`),
  syncRecoveryPayment: (caseId) => request(`/webhook-cases/${encodeURIComponent(caseId)}/sync-payment`, { method: "POST" }),
  createNormalPayment: (payload) => request("/payments/normal-link", { method: "POST", body: JSON.stringify(payload) }),
  simulateFailure: (payload) => request("/test/simulate-failure", { method: "POST", body: JSON.stringify(payload) }),
};
