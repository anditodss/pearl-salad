"use client";
import { useEffect, useState } from "react";

export default function Settings() {
  const [config, setConfig] = useState({ accounts: [], has_env_override: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  // Form states
  const [newName, setNewName] = useState("");
  const [newApiKey, setNewApiKey] = useState("");
  const [newProjects, setNewProjects] = useState("");

  // Expander states for accounts
  const [expandedAccounts, setExpandedAccounts] = useState({});

  const fetchConfig = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/config");
      if (!res.ok) throw new Error(`Config API error: ${res.status}`);
      const data = await res.json();
      setConfig(data);
      setLoading(false);
    } catch (err) {
      console.error(err);
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const toggleExpander = (name) => {
    setExpandedAccounts((prev) => ({
      ...prev,
      [name]: !prev[name],
    }));
  };

  const handleAddAccount = async (e) => {
    e.preventDefault();
    setError("");
    setSuccessMsg("");

    if (!newName || !newApiKey || !newProjects) {
      setError("All fields are required!");
      return;
    }

    // Split projects by comma and trim whitespaces
    const projList = newProjects
      .split(",")
      .map((p) => p.trim())
      .filter((p) => p.length > 0);

    try {
      const res = await fetch("http://localhost:8000/api/config/accounts/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName,
          api_key: newApiKey,
          organizations: projList,
        }),
      });

      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || "Failed to add account");
      }

      setSuccessMsg(result.message || "Account added successfully!");
      setNewName("");
      setNewApiKey("");
      setNewProjects("");
      fetchConfig();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeleteAccount = async (name) => {
    setError("");
    setSuccessMsg("");
    if (!confirm(`Are you sure you want to delete account "${name}"?`)) return;

    try {
      const res = await fetch("http://localhost:8000/api/config/accounts/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });

      const result = await res.json();
      if (!res.ok) {
        throw new Error(result.detail || "Failed to delete account");
      }

      setSuccessMsg(result.message || "Account deleted successfully!");
      fetchConfig();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div style={{ maxWidth: "800px" }}>
      <div className="header">
        <div>
          <h1>Settings</h1>
          <p style={{ color: "var(--text-secondary)", marginTop: "0.5rem" }}>
            Manage Salad Cloud accounts and API monitoring.
          </p>
        </div>
      </div>

      {config.has_env_override && (
        <div
          style={{
            backgroundColor: "rgba(245, 158, 11, 0.1)",
            border: "1px solid var(--accent-orange)",
            borderRadius: "6px",
            padding: "1rem",
            color: "var(--accent-orange)",
            marginBottom: "2rem",
            lineHeight: "1.5",
          }}
        >
          <strong style={{ display: "block", marginBottom: "0.5rem" }}>
            Environment Variables Detected
          </strong>
          You have configuration defined in your <code>.env</code> file. The <code>.env</code> file
          takes priority over the settings configured here. To manage accounts through this UI,
          please delete or clear your <code>.env</code> file and restart the backend.
        </div>
      )}

      {error && (
        <div
          style={{
            backgroundColor: "rgba(239, 68, 68, 0.1)",
            border: "1px solid var(--accent-red)",
            borderRadius: "6px",
            padding: "1rem",
            color: "var(--accent-red)",
            marginBottom: "1.5rem",
          }}
        >
          {error}
        </div>
      )}

      {successMsg && (
        <div
          style={{
            backgroundColor: "rgba(0, 229, 255, 0.1)",
            border: "1px solid var(--accent-cyan)",
            borderRadius: "6px",
            padding: "1rem",
            color: "var(--accent-cyan)",
            marginBottom: "1.5rem",
          }}
        >
          {successMsg}
        </div>
      )}

      <div className="panel">
        <h2 className="panel-title">Configured Salad Accounts</h2>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginBottom: "1.5rem" }}>
          Add or remove Salad Cloud accounts to monitor. Project Format:{" "}
          <code>organization_name/project_name</code>
        </p>

        {loading ? (
          <div style={{ padding: "1rem 0", color: "var(--text-secondary)" }}>Loading settings...</div>
        ) : config.accounts.length === 0 ? (
          <div
            style={{
              padding: "1.5rem",
              border: "1px dashed var(--border-color)",
              borderRadius: "6px",
              textAlign: "center",
              color: "var(--text-secondary)",
            }}
          >
            No accounts configured yet.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {config.accounts.map((acc, idx) => {
              const isExpanded = !!expandedAccounts[acc.name];
              return (
                <div
                  key={idx}
                  style={{
                    border: "1px solid var(--border-color)",
                    borderRadius: "6px",
                    overflow: "hidden",
                    background: "rgba(255,255,255,0.01)",
                  }}
                >
                  <div
                    onClick={() => toggleExpander(acc.name)}
                    style={{
                      padding: "1rem",
                      cursor: "pointer",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      background: "rgba(255,255,255,0.02)",
                      userSelect: "none",
                    }}
                  >
                    <div style={{ fontWeight: 600, display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      {acc.name}
                    </div>
                    <div style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                      {isExpanded ? "▲ Hide" : "▼ Show Details"}
                    </div>
                  </div>

                  {isExpanded && (
                    <div style={{ padding: "1.25rem", borderTop: "1px solid var(--border-color)", fontSize: "0.95rem" }}>
                      <div style={{ marginBottom: "0.75rem" }}>
                        <strong style={{ color: "var(--text-secondary)" }}>API Key:</strong>{" "}
                        <code style={{ background: "rgba(0,0,0,0.2)", padding: "0.2rem 0.4rem", borderRadius: "3px" }}>
                          {acc.api_key}
                        </code>
                      </div>
                      <div style={{ marginBottom: "1.25rem" }}>
                        <strong style={{ color: "var(--text-secondary)" }}>Projects:</strong>{" "}
                        {acc.organizations && acc.organizations.length > 0 ? (
                          acc.organizations.map((org, oIdx) => (
                            <code
                              key={oIdx}
                              style={{
                                background: "rgba(0, 229, 255, 0.05)",
                                color: "var(--accent-cyan)",
                                padding: "0.2rem 0.4rem",
                                borderRadius: "3px",
                                marginRight: "0.5rem",
                                display: "inline-block",
                                marginTop: "0.25rem",
                                border: "1px solid rgba(0, 229, 255, 0.2)",
                              }}
                            >
                              {org}
                            </code>
                          ))
                        ) : (
                          <span style={{ color: "var(--accent-red)" }}>None</span>
                        )}
                      </div>
                      <button
                        onClick={() => handleDeleteAccount(acc.name)}
                        style={{
                          background: "rgba(239, 68, 68, 0.1)",
                          border: "1px solid var(--accent-red)",
                          color: "var(--accent-red)",
                          padding: "0.4rem 0.8rem",
                          borderRadius: "4px",
                          fontSize: "0.85rem",
                          cursor: "pointer",
                          transition: "all 0.2s",
                        }}
                        onMouseEnter={(e) => {
                          e.target.style.background = "rgba(239, 68, 68, 0.2)";
                        }}
                        onMouseLeave={(e) => {
                          e.target.style.background = "rgba(239, 68, 68, 0.1)";
                        }}
                      >
                        Delete Account
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="panel">
        <h2 className="panel-title">Add New Account</h2>
        <form onSubmit={handleAddAccount} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              Account Name
            </label>
            <input
              type="text"
              placeholder="e.g. MainAccount"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              style={{
                width: "100%",
                background: "var(--bg-color)",
                border: "1px solid var(--border-color)",
                color: "var(--text-primary)",
                padding: "0.6rem 0.8rem",
                borderRadius: "4px",
                outline: "none",
                fontSize: "1rem",
              }}
              required
            />
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.5rem", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              Salad API Key
            </label>
            <input
              type="password"
              placeholder="Enter Salad API Key"
              value={newApiKey}
              onChange={(e) => setNewApiKey(e.target.value)}
              style={{
                width: "100%",
                background: "var(--bg-color)",
                border: "1px solid var(--border-color)",
                color: "var(--text-primary)",
                padding: "0.6rem 0.8rem",
                borderRadius: "4px",
                outline: "none",
                fontSize: "1rem",
              }}
              required
            />
          </div>

          <div>
            <label style={{ display: "block", marginBottom: "0.25rem", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              Projects
            </label>
            <span style={{ display: "block", fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.5rem" }}>
              Comma-separated list of organization/project names. Example: <code>my-org/my-project, my-org/project-2</code>
            </span>
            <input
              type="text"
              placeholder="e.g. organization_name/project_name"
              value={newProjects}
              onChange={(e) => setNewProjects(e.target.value)}
              style={{
                width: "100%",
                background: "var(--bg-color)",
                border: "1px solid var(--border-color)",
                color: "var(--text-primary)",
                padding: "0.6rem 0.8rem",
                borderRadius: "4px",
                outline: "none",
                fontSize: "1rem",
              }}
              required
            />
          </div>

          <button
            type="submit"
            className="btn-primary"
            style={{
              alignSelf: "flex-start",
              padding: "0.6rem 1.2rem",
              marginTop: "0.5rem",
            }}
          >
            Save Account
          </button>
        </form>
      </div>
    </div>
  );
}
