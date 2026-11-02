import { Fragment, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle2, AlertTriangle, ArrowLeftRight, RefreshCw, ChevronDown, ChevronRight } from "lucide-react";
import { usd } from "../utils";

type ReconItem = {
  document_id: string;
  document_type: string;
  amount: number;
  reason: string;
  gl_je_id: string | null;
  gl_je_status: string | null;
};

type ReconRow = {
  account_code: string;
  account_name: string;
  subledger_source: string | null;
  subledger_amount: number;
  gl_amount: number;
  delta: number;
  reconciling_items_amount: number;
  reconciling_items_count: number;
  unexplained_delta: number;
  tied: boolean;
  cutoff_date: string | null;
  items: ReconItem[];
};

/**
 * Sub-ledger ↔ GL reconciliation at the GL cut-off (/api/recon).
 * Three numbers per control account: sub-ledger, GL, and the documented
 * reconciling items that explain the difference. "Tied" is shown only when the
 * UNEXPLAINED delta is zero (|Δ| below one rupee).
 */
export default function GLReconCard() {
  const [rows, setRows] = useState<ReconRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch("/api/recon");
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        setErr(j.message || j.error || `HTTP ${r.status}`);
        setRows(null);
        return;
      }
      const j = await r.json();
      setRows(j.rows as ReconRow[]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const allTied = !!rows && rows.length > 0 && rows.every((r) => Math.abs(r.unexplained_delta) < 1);
  const totalItems = rows?.reduce((n, r) => n + (r.reconciling_items_count || 0), 0) ?? 0;
  const cutoff = rows?.find((r) => r.cutoff_date)?.cutoff_date;

  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border-subtle bg-bg-card/80 backdrop-blur-sm shadow-sm p-4"
      data-testid="gl-recon-card"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={`p-1.5 rounded-md ${allTied ? "bg-db-green/15" : "bg-db-red/15"}`}>
            {allTied ? (
              <CheckCircle2 className="w-4 h-4 text-db-green" />
            ) : (
              <ArrowLeftRight className="w-4 h-4 text-db-red" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-bold text-text-primary leading-tight">
              Sub-ledger ↔ GL reconciliation
            </h3>
            <p className="text-[10px] text-text-muted leading-tight">
              {loading
                ? "Loading…"
                : err
                ? `Data unavailable: ${err}`
                : allTied
                ? `Tied · ${totalItems} item${totalItems === 1 ? "" : "s"} explained${cutoff ? ` · cut-off ${cutoff}` : ""}`
                : "Unexplained difference — investigate red rows"}
            </p>
          </div>
        </div>
        <button
          onClick={load}
          className="opacity-60 hover:opacity-100 transition p-1 rounded hover:bg-bg-hover"
          aria-label="Refresh reconciliation"
          disabled={loading}
        >
          <RefreshCw className={`w-3.5 h-3.5 text-text-muted ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {rows && rows.length > 0 ? (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-muted border-b border-border-subtle">
              <th className="text-left font-normal py-1.5">Account</th>
              <th className="text-right font-normal">Sub-ledger</th>
              <th className="text-right font-normal">GL</th>
              <th className="text-right font-normal">Explained items</th>
              <th className="text-right font-normal">Unexplained</th>
              <th className="text-center font-normal w-14">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const tied = Math.abs(r.unexplained_delta) < 1;
              const isOpen = !!open[r.account_code];
              return (
                <Fragment key={r.account_code}>
                  <tr
                    className={`${tied ? "" : "bg-db-red/5 ring-1 ring-db-red/30"} cursor-pointer hover:bg-bg-hover/40`}
                    onClick={() => setOpen((o) => ({ ...o, [r.account_code]: !o[r.account_code] }))}
                  >
                    <td className="text-text-primary py-2">
                      {r.items.length > 0 ? (
                        isOpen ? <ChevronDown className="w-3 h-3 inline mr-1" /> : <ChevronRight className="w-3 h-3 inline mr-1" />
                      ) : null}
                      <span className="font-mono text-text-secondary mr-1.5">{r.account_code}</span>
                      {r.account_name}
                    </td>
                    <td className="text-right tabular-nums">{usd(r.subledger_amount)}</td>
                    <td className="text-right tabular-nums">{usd(r.gl_amount)}</td>
                    <td className="text-right tabular-nums" data-testid={`recon-explained-${r.account_code}`}>
                      {usd(r.reconciling_items_amount)}
                      <span className="ml-1 text-[9px] text-text-muted">({r.reconciling_items_count})</span>
                    </td>
                    <td className={`text-right tabular-nums ${tied ? "text-db-green" : "text-db-red font-semibold"}`}>
                      {tied ? "$0" : usd(r.unexplained_delta)}
                    </td>
                    <td className="text-center">
                      {tied ? (
                        <span className="text-[10px] font-bold text-db-green">Tied</span>
                      ) : (
                        <AlertTriangle className="w-3.5 h-3.5 text-db-red inline" />
                      )}
                    </td>
                  </tr>
                  {isOpen &&
                    r.items.map((it) => (
                      <tr key={`${r.account_code}-${it.document_id}`} className="text-[10px] text-text-muted">
                        <td className="pl-6 py-1 font-mono">{it.document_id}</td>
                        <td colSpan={3} className="">
                          {it.document_type} — {it.reason}
                          {it.gl_je_id ? ` (GL: ${it.gl_je_id}${it.gl_je_status ? `, ${it.gl_je_status}` : ""})` : ""}
                        </td>
                        <td className="text-right tabular-nums">{usd(it.amount)}</td>
                        <td />
                      </tr>
                    ))}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      ) : loading ? (
        <div className="space-y-1.5">
          <div className="h-3 bg-bg-hover/50 rounded animate-pulse" />
          <div className="h-3 bg-bg-hover/50 rounded animate-pulse" />
        </div>
      ) : (
        <p className="text-[12px] text-text-muted italic">—</p>
      )}

      {rows && rows.length > 0 && (
        <p className="mt-2 text-[10px] text-text-muted">
          Sources: <code className="text-text-secondary">gold_recon_subledger_vs_gl</code> and{" "}
          <code className="text-text-secondary">gold_recon_reconciling_items</code>. Click a row for the items.
        </p>
      )}
    </motion.div>
  );
}
