"use client";
import { useEffect, useState, useRef, useCallback, Fragment } from "react";
import { useServerEvents } from "../useServerEvents";

function Toast({ toasts }) {
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.type}`}>{t.message}</div>
      ))}
    </div>
  );
}

function ConfirmModal({ message, onConfirm, onCancel }) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Confirm Action</h3>
        <p>{message}</p>
        <div className="modal-actions">
          <button className="btn-ghost" onClick={onCancel}>Cancel</button>
          <button className="btn-primary" onClick={onConfirm}>Confirm</button>
        </div>
      </div>
    </div>
  );
}

const TRANSIENT_STATES = ["allocating", "downloading", "extracting", "creating", "starting", "deploying", "reallocating"];

export default function Instances() {
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [confirm, setConfirm] = useState(null);
  const [search, setSearch] = useState("");
  const [gpuFilter, setGpuFilter] = useState("ALL");
  const [collapsedAccounts, setCollapsedAccounts] = useState({});
  const fastPollRef = useRef(null);

  const toggleAccount = (accountName) => {
    setCollapsedAccounts(prev => ({ ...prev, [accountName]: !prev[accountName] }));
  };

  const addToast = (message, type = "success") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  };

  const fetchInstances = useCallback(async (sseData) => {
    if (sseData && Array.isArray(sseData)) {
      setInstances(sseData);
      setLoading(false);
      return;
    }
    try {
      const res = await fetch("http://localhost:8000/api/instances");
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data = await res.json();
      setInstances(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  // SSE: instant update when backend sync completes
  useServerEvents(fetchInstances);

  // Start fast polling (every 3s) for a short burst after a reallocate
  const startFastPoll = () => {
    if (fastPollRef.current) clearInterval(fastPollRef.current);
    let ticks = 0;
    fastPollRef.current = setInterval(() => {
      fetchInstances();
      ticks++;
      if (ticks >= 10) { // 10 × 3s = 30s of fast polling
        clearInterval(fastPollRef.current);
        fastPollRef.current = null;
      }
    }, 3000);
  };

  useEffect(() => {
    fetchInstances();
    // Fallback poll — SSE handles real-time, this is just a safety net
    const interval = setInterval(fetchInstances, 60000);
    return () => {
      clearInterval(interval);
      if (fastPollRef.current) clearInterval(fastPollRef.current);
    };
  }, [fetchInstances]);

  const handleReallocate = (id) => {
    setConfirm({ id, message: "Reallocate this instance to a new node?" });
  };

  const doReallocate = async () => {
    const id = confirm.id;
    setConfirm(null);
    setActionLoadingId(id);
    try {
      const res = await fetch(`http://localhost:8000/api/instances/${id}/reallocate`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        addToast(`Error: ${data.detail || "Failed to reallocate"}`, "error");
      } else {
        addToast("Reallocation requested.");
        // Poll fast so state transitions (allocating → downloading → running) show up quickly
        startFastPoll();
      }
    } catch (err) {
      console.error(err);
      addToast("Could not reach the API.", "error");
    } finally {
      setActionLoadingId(null);
    }
  };

  const getStateBadge = (state) => {
    const s = (state || "unknown").toLowerCase();
    if (s === "running") return { class: "badge state-running", icon: "🟢", label: "Running" };
    if (s === "failed" || s === "stopped") return { class: "badge state-stopped", icon: "🔴", label: s };
    if (TRANSIENT_STATES.includes(s)) return { class: "badge state-creating", icon: "⏳", label: s };
    return { class: "badge state-unknown", icon: "⚪", label: s };
  };

  const getHealthBadge = (status) => {
    const s = (status || "unknown").toUpperCase();
    if (s === "GOOD") return { class: "badge health-good", icon: "✓", label: "GOOD" };
    if (s === "BAD") return { class: "badge health-bad", icon: "✗", label: "BAD" };
    if (s === "WARNING") return { class: "badge health-warning", icon: "⚠", label: "WARN" };
    return { class: "badge health-unknown", icon: "?", label: "UNK" };
  };

  const isTransient = (state) => TRANSIENT_STATES.includes((state || "").toLowerCase());

  const gpuTypes = ["ALL", ...Array.from(new Set(instances.map((i) => i.gpu_type).filter(Boolean)))];

  const filtered = instances.filter((inst) => {
    const q = search.toLowerCase();
    const matchSearch =
      !q ||
      (inst.account_name || "").toLowerCase().includes(q) ||
      (inst.container_group_name || "").toLowerCase().includes(q) ||
      (inst.salad_id || "").toLowerCase().includes(q) ||
      (inst.machine_id || "").toLowerCase().includes(q);
    const matchGpu = gpuFilter === "ALL" || inst.gpu_type === gpuFilter;
    return matchSearch && matchGpu;
  });

  // Counts for summary row
  const runningCount = filtered.filter(i => (i.state || "").toLowerCase() === "running").length;
  const transientCount = filtered.filter(i => isTransient(i.state)).length;

  const groupedInstances = filtered.reduce((acc, inst) => {
    const key = inst.account_name || "Unknown";
    if (!acc[key]) acc[key] = [];
    acc[key].push(inst);
    return acc;
  }, {});

  return (
    <div>
      {confirm && (
        <ConfirmModal
          message={confirm.message}
          onConfirm={doReallocate}
          onCancel={() => setConfirm(null)}
        />
      )}

      <div className="header">
        <div>
          <h1>Instances</h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.25rem", fontSize: "0.9rem" }}>
            Monitor and manage individual GPU instances.
          </p>
        </div>
      </div>

      <div className="panel">
        <div className="filter-bar">
          <input
            className="input-search"
            placeholder="Search account, group, ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            value={gpuFilter}
            onChange={(e) => setGpuFilter(e.target.value)}
            style={{
              background: "var(--bg-color)",
              border: "1px solid var(--border-color)",
              color: "var(--text-primary)",
              padding: "0.5rem 0.875rem",
              borderRadius: "4px",
              fontSize: "0.875rem",
              outline: "none",
              cursor: "pointer",
            }}
          >
            {gpuTypes.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
          <div style={{ display: "flex", gap: "1rem", alignSelf: "center", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
            <span style={{ color: "var(--accent-green)" }}>{runningCount} running</span>
            {transientCount > 0 && (
              <span style={{ color: "var(--accent-orange)" }}>{transientCount} transitioning</span>
            )}
            <span>{filtered.length} total</span>
          </div>
        </div>

        <div className="table-container">
          {loading && instances.length === 0 ? (
            <div style={{ padding: "1rem 0" }}>
              {[...Array(6)].map((_, i) => (
                <div key={i} className="skeleton skeleton-line" style={{ width: `${75 + (i % 3) * 8}%`, marginBottom: "0.75rem" }} />
              ))}
            </div>
          ) : (
            <table className="instances-table">
              <thead>
                <tr>
                  <th>Account / Group</th>
                  <th>Instance ID</th>
                  <th>GPU</th>
                  <th>Created</th>
                  <th>Hashrate</th>
                  <th>State</th>
                  <th>Health</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(groupedInstances).map(([accountName, accountInstances]) => {
                  const isCollapsed = collapsedAccounts[accountName];
                  return (
                    <Fragment key={accountName}>
                      <tr 
                        className="group-header-row"
                        onClick={() => toggleAccount(accountName)} 
                      >
                        <td colSpan="8" style={{ padding: 0 }}>
                          <div className="group-header-cell">
                            <span 
                              className="group-header-icon" 
                              style={{ transform: isCollapsed ? 'rotate(-90deg)' : 'rotate(0)' }}
                            >
                              ▼
                            </span>
                            {accountName} 
                            <span className="group-header-count">
                              {accountInstances.length} {accountInstances.length === 1 ? 'instance' : 'instances'}
                            </span>
                          </div>
                        </td>
                      </tr>
                      {!isCollapsed && accountInstances.map((inst) => {
                        const transitioning = isTransient(inst.state);
                        return (
                          <tr
                            key={inst.id}
                            className={transitioning ? "row-transitioning" : ""}
                          >
                            <td>
                              <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                                {inst.account_name || "—"}
                              </div>
                              <div style={{ fontSize: "0.75rem", color: "var(--text-primary)", opacity: 0.8, marginTop: "0.15rem" }}>
                                {inst.container_group_name || "—"}
                              </div>
                            </td>
                            <td>
                              <span className="id-tag" title={inst.machine_id}>
                                {inst.machine_id ? inst.machine_id.substring(0, 12) + "…" : "—"}
                              </span>
                            </td>
                            <td style={{ color: "var(--accent-cyan)", fontSize: "0.8rem", fontWeight: 600 }}>
                              {inst.gpu_type || (
                                <span className="badge-detecting">
                                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <line x1="12" y1="2" x2="12" y2="6"></line>
                                    <line x1="12" y1="18" x2="12" y2="22"></line>
                                    <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
                                    <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
                                    <line x1="2" y1="12" x2="6" y2="12"></line>
                                    <line x1="18" y1="12" x2="22" y2="12"></line>
                                    <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line>
                                    <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line>
                                  </svg>
                                  Detecting...
                                </span>
                              )}
                            </td>
                            <td style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                              {inst.api_create_time ? new Date(inst.api_create_time + 'Z').toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : "—"}
                            </td>
                            <td>
                              {transitioning ? (
                                <span style={{ color: "var(--accent-orange)", fontSize: "0.75rem" }}>{inst.state}</span>
                              ) : inst.latest_hashrate ? (
                                <span className="hashrate-neon">
                                  {inst.latest_hashrate.toFixed(2)}
                                  <span className="unit">TH/s</span>
                                </span>
                              ) : (
                                <span style={{ color: "var(--text-secondary)" }}>—</span>
                              )}
                            </td>
                            <td>
                              <span className={getStateBadge(inst.state).class}>
                                <span style={{ fontSize: "0.6rem" }}>{getStateBadge(inst.state).icon}</span>
                                {getStateBadge(inst.state).label}
                              </span>
                            </td>
                            <td>
                              {!transitioning && (
                                <span className={getHealthBadge(inst.status).class}>
                                  <span style={{ fontSize: "0.65rem" }}>{getHealthBadge(inst.status).icon}</span>
                                  {getHealthBadge(inst.status).label}
                                </span>
                              )}
                            </td>
                            <td>
                              <button
                                className="btn-primary"
                                onClick={() => handleReallocate(inst.id)}
                                disabled={actionLoadingId === inst.id || (inst.state || "").toLowerCase() === "reallocating"}
                                style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem", whiteSpace: "nowrap" }}
                              >
                                {actionLoadingId === inst.id ? "…" : "Reallocate"}
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </Fragment>
                  );
                })}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan="8" style={{ textAlign: "center", padding: "2rem", color: "var(--text-secondary)" }}>
                      {instances.length === 0 ? "No instances found." : "No instances match your filter."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <Toast toasts={toasts} />
    </div>
  );
}
