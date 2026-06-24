"use client";
import { useEffect, useState, useCallback } from "react";
import { useServerEvents } from "../useServerEvents";

export default function Actions() {
  const [actions, setActions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState("ALL");

  const fetchActions = useCallback(async () => {
    try {
      const res = await fetch(`http://localhost:8000/api/actions?action_type=${filterType}`);
      if (!res.ok) throw new Error(`Actions API error: ${res.status}`);
      const data = await res.json();
      setActions(Array.isArray(data) ? data : []);
      setLoading(false);
    } catch (err) {
      console.error(err);
      setLoading(false);
    }
  }, [filterType]);

  useServerEvents(fetchActions);

  useEffect(() => {
    fetchActions();
    const interval = setInterval(fetchActions, 60000);
    return () => clearInterval(interval);
  }, [fetchActions]);

  const totalActions = actions.length;
  const succeededActions = actions.filter((a) => a.success).length;
  const failedActions = totalActions - succeededActions;

  return (
    <div>
      <div className="header">
        <div>
          <h1>Remediation Actions</h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.5rem" }}>
            Automated actions taken when instances fall below the efficiency threshold.
          </p>
        </div>
        <button className="btn-primary" onClick={() => { setLoading(true); fetchActions(); }}>
          Refresh
        </button>
      </div>

      <div className="panel" style={{ display: "flex", gap: "1.5rem", alignItems: "flex-end", marginBottom: "2rem" }}>
        <div>
          <label style={{ display: "block", marginBottom: "0.5rem", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
            Filter by action type
          </label>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            style={{
              background: "var(--bg-color)",
              border: "1px solid var(--border-color)",
              color: "var(--text-primary)",
              padding: "0.5rem 1rem",
              borderRadius: "4px",
              fontSize: "1rem",
              outline: "none",
              cursor: "pointer",
              minWidth: "180px",
            }}
          >
            <option value="ALL">ALL</option>
            <option value="REALLOCATE">REALLOCATE</option>
            <option value="RECREATE">RECREATE</option>
            <option value="RESTART">RESTART</option>
          </select>
        </div>
        <div style={{ color: "var(--text-secondary)", fontSize: "0.9rem", alignSelf: "center", marginTop: "1.5rem" }}>
          Showing {totalActions} action(s)
        </div>
      </div>

      <div className="panel">
        <h2 className="panel-title">Action Logs</h2>
        <div className="table-container">
          {loading && actions.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
              Loading remediation logs...
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Timestamp (UTC)</th>
                  <th>Result</th>
                  <th>Action</th>
                  <th>Account</th>
                  <th>Organization</th>
                  <th>Group</th>
                  <th>Instance ID</th>
                  <th>Machine ID</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {actions.map((a) => (
                  <tr key={a.id}>
                    <td style={{ fontSize: "0.9rem", whiteSpace: "nowrap" }}>{a.created_at}</td>
                    <td>
                      <span className={a.success ? "badge health-good" : "badge health-bad"}>
                        {a.success ? "Success" : "Failed"}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600, color: "var(--accent-cyan)" }}>{a.action_type}</td>
                    <td>{a.account_name}</td>
                    <td>{a.org_name}</td>
                    <td>{a.group_name}</td>
                    <td style={{ fontFamily: "monospace", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                      {a.instance_id ? `${a.instance_id.substring(0, 8)}...` : "—"}
                    </td>
                    <td style={{ fontFamily: "monospace", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                      {a.machine_id ? `${a.machine_id.substring(0, 8)}...` : "—"}
                    </td>
                    <td style={{ fontSize: "0.9rem" }}>{a.reason || "—"}</td>
                  </tr>
                ))}
                {actions.length === 0 && (
                  <tr>
                    <td colSpan="9" style={{ textAlign: "center", padding: "2rem", color: "var(--text-secondary)" }}>
                      No remediation actions recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="metrics-grid" style={{ marginTop: "2rem" }}>
        <div className="metric-card">
          <div className="metric-label">Total Actions</div>
          <div className="metric-value">{totalActions}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Succeeded</div>
          <div className="metric-value" style={{ color: "var(--accent-cyan)" }}>{succeededActions}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Failed</div>
          <div className="metric-value" style={{ color: "var(--accent-red)" }}>{failedActions}</div>
        </div>
      </div>
    </div>
  );
}
