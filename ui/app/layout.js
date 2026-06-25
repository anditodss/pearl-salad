"use client";
import { Inter } from "next/font/google";
import "./globals.css";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const inter = Inter({ subsets: ["latin"] });

const NAV_ITEMS = [
  { href: "/",                 label: "Overview",            icon: "◈" },
  { href: "/instances",        label: "Instances",           icon: "⬡" },
  { href: "/auto-reallocate",  label: "Auto Reallocate",     icon: "⚠" },
  { href: "/gpu-summary",      label: "GPU Summary",         icon: "▦" },
  { href: "/actions",          label: "Remediation Actions", icon: "⟳" },
  { href: "/settings",         label: "Settings",            icon: "⚙" },
];

function useNextSync() {
  const [secondsUntil, setSecondsUntil] = useState(null);

  useEffect(() => {
    let nextRunMs = null;

    const fetchStatus = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/scheduler-status");
        const data = await res.json();
        const syncJob = data.jobs?.find((j) => j.id === "sync_job");
        if (syncJob?.next_run) {
          nextRunMs = new Date(syncJob.next_run).getTime();
        }
      } catch (_) {}
    };

    fetchStatus();
    const fetchInterval = setInterval(fetchStatus, 15000);

    const ticker = setInterval(() => {
      if (nextRunMs !== null) {
        const diff = Math.max(0, Math.round((nextRunMs - Date.now()) / 1000));
        setSecondsUntil(diff);
      }
    }, 1000);

    return () => {
      clearInterval(fetchInterval);
      clearInterval(ticker);
    };
  }, []);

  return secondsUntil;
}

export default function RootLayout({ children }) {
  const pathname = usePathname();
  const nextSync = useNextSync();

  return (
    <html lang="en" className={inter.className} suppressHydrationWarning>
      <head>
        <title>Veayra — Fleet Dashboard</title>
        <meta name="description" content="Salad GPU fleet monitoring and remediation dashboard." />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body suppressHydrationWarning>
        <div className="app-container">
          <aside className="sidebar">
            <div className="sidebar-logo">
              <span>●</span> Veayra
            </div>

            <div className="nav-section-label">ANALYTICS</div>

            <nav className="nav-menu">
              {NAV_ITEMS.map(({ href, label, icon }) => (
                <Link href={href} key={href}>
                  <div className={`nav-item ${pathname === href ? "active" : ""}`}>
                    <span className="nav-icon">{icon}</span>
                    {label}
                  </div>
                </Link>
              ))}
            </nav>

            <div className="sidebar-footer">
              <div className="sidebar-version">v1.0</div>
              {nextSync !== null && (
                <div style={{ fontSize: "0.7rem", color: "var(--text-secondary)", opacity: 0.5, marginTop: "0.25rem" }}>
                  {nextSync === 0 ? "Syncing…" : `Next sync in ${nextSync}s`}
                </div>
              )}
            </div>
          </aside>

          <main className="main-content">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}

