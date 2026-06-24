"use client";
import { useEffect, useState, useCallback } from "react";
import { useServerEvents } from "./useServerEvents";

export default function Home() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch("http://localhost:8000/api/stats");
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data = await res.json();
      setStats(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  // SSE: re-fetch instantly when the backend signals a sync completed
  useServerEvents(fetchStats);

  const forceSync = async () => {
    setSyncing(true);
    try {
      await fetch("http://localhost:8000/api/sync", { method: "POST" });
      setTimeout(fetchStats, 3000);
    } catch (err) {
      console.error(err);
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    fetchStats();
    // Keep a slow fallback poll in case SSE disconnects
    const interval = setInterval(fetchStats, 60000);
    return () => clearInterval(interval);
  }, [fetchStats]);

  return (
    <div>
      <div className="header">
        <div>
          <h1>Fleet Overview</h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.5rem" }}>
            Real-time Salad fleet monitoring and health status.
          </p>
        </div>
        <button className="btn-primary" onClick={forceSync} disabled={syncing}>
          {syncing ? "Syncing..." : "Force Sync Now"}
        </button>
      </div>

      {loading && !stats ? (
        <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
          Loading data...
        </div>
      ) : stats ? (
        <>
          <div className="overview-hero">
            <div className="primary-card">
              <div className="metric-label">Fleet Hashrate</div>
              <div className="fleet-hashrate-value">
                {stats.total_hashrate ? stats.total_hashrate.toFixed(2) : "0.00"}<span className="unit">H/s</span>
              </div>
              <div className="fleet-hashrate-subtext">
                Active Workers: <span style={{ color: "var(--accent-cyan)", fontWeight: 600 }}>{stats.good_count}</span> / {stats.total_instances}
              </div>
            </div>
            
            <div className="secondary-grid">
              <div className="metric-card">
                <div className="metric-label">Total Instances</div>
                <div className="metric-value">{stats.total_instances}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Health Ratio</div>
                <div className="metric-value" style={{ color: "var(--accent-cyan)" }}>
                  {stats.total_instances ? Math.round((stats.good_count / stats.total_instances) * 100) : 0}%
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Container Groups</div>
                <div className="metric-value">{stats.total_container_groups}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Active GPU Types</div>
                <div className="metric-value">{stats.total_gpu_types}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Total Cost / Hr</div>
                <div className="metric-value">${stats.total_cost_per_hour ? stats.total_cost_per_hour.toFixed(2) : "0.00"}</div>
              </div>
            </div>
          </div>

          <div className="panel">
            <h2 className="panel-title">System Health Summary</h2>
            <div style={{ display: 'flex', gap: '2rem', alignItems: 'center' }}>
              <div style={{ flex: 1, height: '8px', backgroundColor: 'var(--border-color)', borderRadius: '4px', overflow: 'hidden', display: 'flex' }}>
                <div style={{ width: `${(stats.good_count / (stats.total_instances || 1)) * 100}%`, backgroundColor: 'var(--accent-cyan)' }}></div>
                <div style={{ width: `${(stats.warning_count / (stats.total_instances || 1)) * 100}%`, backgroundColor: 'var(--accent-orange)' }}></div>
                <div style={{ width: `${(stats.bad_count / (stats.total_instances || 1)) * 100}%`, backgroundColor: 'var(--accent-red)' }}></div>
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                {stats.total_instances ? Math.round((stats.good_count / stats.total_instances) * 100) : 0}%
              </div>
            </div>
            <div style={{ marginTop: '1.25rem', display: 'flex', gap: '2rem', fontSize: '0.85rem' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--accent-cyan)' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--accent-cyan)', display: 'inline-block' }}></span>
                {stats.good_count} Good
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--accent-orange)' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--accent-orange)', display: 'inline-block' }}></span>
                {stats.warning_count} Warning
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--accent-red)' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--accent-red)', display: 'inline-block' }}></span>
                {stats.bad_count} Bad
              </span>
            </div>
          </div>
        </>
      ) : (
        <div style={{ padding: "2rem", textAlign: "center", color: "var(--accent-red)" }}>
          Error loading stats.
        </div>
      )}
    </div>
  );
}
