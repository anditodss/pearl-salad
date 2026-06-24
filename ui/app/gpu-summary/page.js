"use client";
import { useEffect, useState, useCallback } from "react";
import { useServerEvents } from "../useServerEvents";

export default function GpuSummary() {
  const [gpuSummary, setGpuSummary] = useState([]);
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedGpu, setSelectedGpu] = useState("");

  const fetchData = useCallback(async () => {
    try {
      const [summaryRes, instancesRes] = await Promise.all([
        fetch("http://localhost:8000/api/gpu-summary"),
        fetch("http://localhost:8000/api/instances"),
      ]);
      if (!summaryRes.ok) throw new Error(`Summary API error: ${summaryRes.status}`);
      if (!instancesRes.ok) throw new Error(`Instances API error: ${instancesRes.status}`);

      const [summaryData, instancesData] = await Promise.all([
        summaryRes.json(),
        instancesRes.json(),
      ]);

      setGpuSummary(Array.isArray(summaryData) ? summaryData : []);
      setInstances(Array.isArray(instancesData) ? instancesData : []);

      if (summaryData.length > 0 && !selectedGpu) {
        setSelectedGpu(summaryData[0].gpu_type);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useServerEvents(fetchData);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const getStatusBadge = (state) => {
    const s = state ? state.toLowerCase() : 'unknown';
    if (s === 'running') return 'badge state-running';
    if (s === 'failed' || s === 'stopped') return 'badge state-stopped';
    if (['allocating', 'downloading', 'extracting', 'creating', 'starting', 'deploying'].includes(s)) {
      return 'badge state-creating';
    }
    return 'badge state-unknown';
  };

  const getHealthBadge = (status) => {
    const s = status ? status.toUpperCase() : 'UNKNOWN';
    if (s === 'GOOD') return 'badge health-good';
    if (s === 'BAD') return 'badge health-bad';
    if (s === 'WARNING') return 'badge health-warning';
    return 'badge health-unknown';
  };

  const filteredInstances = selectedGpu
    ? instances.filter((i) => i.gpu_type === selectedGpu)
    : [];

  return (
    <div>
      <div className="header">
        <div>
          <h1>GPU Summary</h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.5rem" }}>
            Per-GPU-type performance breakdown and drilldown.
          </p>
        </div>
        <button className="btn-primary" onClick={() => { setLoading(true); fetchData(); }}>
          Refresh
        </button>
      </div>

      {loading && gpuSummary.length === 0 ? (
        <div className="panel" style={{ padding: "1.75rem" }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} className="skeleton skeleton-line" style={{ width: `${70 + (i % 3) * 10}%` }} />
          ))}
        </div>
      ) : (
        <>
          <div className="panel">
            <h2 className="panel-title">Aggregated Stats per GPU Type</h2>
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>GPU Type</th>
                    <th>Total Instances</th>
                    <th>Bad Instances</th>
                    <th>Health %</th>
                    <th>Median Hashrate</th>
                    <th>Avg Hashrate</th>
                    <th>Min Hashrate</th>
                    <th>Max Hashrate</th>
                  </tr>
                </thead>
                <tbody>
                  {gpuSummary.map((g, idx) => {
                    const healthPct = g.instance_count
                      ? ((g.instance_count - g.bad_count) / g.instance_count) * 100
                      : 0;
                    return (
                      <tr key={idx}>
                        <td style={{ color: "var(--accent-cyan)", fontWeight: 600 }}>{g.gpu_type}</td>
                        <td>{g.instance_count}</td>
                        <td style={{ color: g.bad_count > 0 ? "var(--accent-red)" : "inherit" }}>
                          {g.bad_count}
                        </td>
                        <td style={{ fontWeight: 600, color: healthPct === 100 ? "var(--accent-cyan)" : healthPct > 50 ? "var(--accent-orange)" : "var(--accent-red)" }}>
                          {healthPct.toFixed(1)}%
                        </td>
                        <td>{g.median_hashrate != null ? g.median_hashrate.toFixed(2) : "N/A"}</td>
                        <td>{g.avg_hashrate != null ? g.avg_hashrate.toFixed(2) : "N/A"}</td>
                        <td>{g.min_hashrate != null ? g.min_hashrate.toFixed(2) : "N/A"}</td>
                        <td>{g.max_hashrate != null ? g.max_hashrate.toFixed(2) : "N/A"}</td>
                      </tr>
                    );
                  })}
                  {gpuSummary.length === 0 && (
                    <tr>
                      <td colSpan="8" style={{ textAlign: "center", padding: "2rem" }}>
                        No GPU data available.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <h2 className="panel-title" style={{ marginBottom: "1.5rem" }}>Drilldown by GPU Type</h2>
            <div style={{ marginBottom: "1.5rem" }}>
              <label style={{ display: "block", marginBottom: "0.5rem", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                Select GPU Type
              </label>
              <select
                value={selectedGpu}
                onChange={(e) => setSelectedGpu(e.target.value)}
                style={{
                  background: "var(--bg-color)",
                  border: "1px solid var(--border-color)",
                  color: "var(--text-primary)",
                  padding: "0.5rem 1rem",
                  borderRadius: "4px",
                  fontSize: "1rem",
                  outline: "none",
                  cursor: "pointer",
                }}
              >
                {gpuSummary.map((g, idx) => (
                  <option key={idx} value={g.gpu_type}>
                    {g.gpu_type}
                  </option>
                ))}
              </select>
            </div>

            <div className="table-container">
              {filteredInstances.length === 0 ? (
                <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                  No instances found for this GPU type.
                </div>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Instance ID</th>
                      <th>Account</th>
                      <th>Group</th>
                      <th>State</th>
                      <th>Hashrate</th>
                      <th>Efficiency</th>
                      <th>Health</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredInstances.map((i) => (
                      <tr key={i.id}>
                        <td style={{ fontFamily: "monospace", color: "var(--text-secondary)" }}>
                          {i.salad_id ? `${i.salad_id.substring(0, 8)}...` : "—"}
                        </td>
                        <td>{i.account_name || "—"}</td>
                        <td>{i.container_group_name || "—"}</td>
                        <td>
                          <span className={getStatusBadge(i.state)}>{i.state || "unknown"}</span>
                        </td>
                        <td style={{ fontWeight: 600 }}>
                          {i.latest_hashrate != null ? i.latest_hashrate.toFixed(2) : "Wait..."}
                        </td>
                        <td>
                          {i.efficiency != null ? `${(i.efficiency * 100).toFixed(1)}%` : "N/A"}
                        </td>
                        <td>
                          <span className={getHealthBadge(i.status)}>{i.status || "UNKNOWN"}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
