"use client";
import { useEffect } from "react";

/**
 * useServerEvents
 * Subscribes to the /api/events SSE stream.
 * Calls onUpdate() immediately when the server signals a sync completed.
 * Falls back gracefully if the connection drops (auto-reconnects after 3s).
 *
 * Usage:
 *   useServerEvents(fetchData);  // fetchData is called on every server push
 */
export function useServerEvents(onUpdate) {
  useEffect(() => {
    let es;
    let reconnectTimer;

    const connect = () => {
      es = new EventSource("http://localhost:8000/api/events");

      const handleEvent = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (Array.isArray(data) || typeof data === 'object') {
            onUpdate(data);
            return;
          }
        } catch (e) {
          // Fallback to fetch if data is not JSON or is just "1"
        }
        onUpdate();
      };

      es.addEventListener("sync_complete", handleEvent);
      es.addEventListener("monitor_complete", handleEvent);

      es.onerror = () => {
        es.close();
        // Auto-reconnect after 3s if connection drops
        reconnectTimer = setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (es) es.close();
    };
  }, []); // onUpdate intentionally not in deps — callers pass a stable ref
}
