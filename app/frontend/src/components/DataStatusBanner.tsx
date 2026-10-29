import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";

type DataStatus = {
  demo_mode: boolean;
  live: boolean | null;
  banner: string | null;
  last_error: string | null;
  auth_mode: string | null;
};

/**
 * Visible whenever the backend is NOT serving live lakehouse rows:
 *   "Warehouse starting — data unavailable"  (live !== true)
 *   "Demo data — not connected to the lakehouse"  (DEMO_MODE=true)
 * Polls /api/data-status; the banner clears itself when the warehouse answers.
 */
export default function DataStatusBanner() {
  const [status, setStatus] = useState<DataStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const r = await fetch("/api/data-status");
        const j = (await r.json()) as DataStatus;
        if (!cancelled) setStatus(j);
      } catch {
        if (!cancelled)
          setStatus({ demo_mode: false, live: false, banner: "Backend unreachable — data unavailable", last_error: null, auth_mode: null });
      }
    }
    poll();
    const id = setInterval(poll, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (!status?.banner) return null;
  const demo = status.demo_mode;
  return (
    <div
      role="status"
      data-testid="data-status-banner"
      className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b ${
        demo ? "bg-db-amber/15 border-db-amber/40 text-db-amber" : "bg-db-red/15 border-db-red/40 text-db-red"
      }`}
    >
      <AlertTriangle className="w-4 h-4 flex-shrink-0" />
      <span>{status.banner}</span>
      {!demo && <span className="text-xs opacity-75">KPIs show "—" until live rows return. Retrying automatically.</span>}
    </div>
  );
}
