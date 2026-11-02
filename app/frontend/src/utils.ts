/** The build stores amounts in INR; the app shows them in US dollars at this fixed rate. */
export const INR_PER_USD = 88;

/** Format a US-dollar amount: $1.23M, $45.6K or $789. */
export function formatUSD(value: number | string | null | undefined): string {
  if (value == null) return "---";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "---";
  const sign = num < 0 ? "-" : "";
  const abs = Math.abs(num);
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`;
  return `${sign}$${abs.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

/** Format an INR amount from the data layer as US dollars. */
export function usd(value: number | string | null | undefined): string {
  if (value == null) return "---";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "---";
  return formatUSD(num / INR_PER_USD);
}

/** Format an INR amount as exact US dollars with cents. */
export function usdExact(value: number | null | undefined): string {
  if (value == null || isNaN(value)) return "—";
  return `$${(value / INR_PER_USD).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Format number with commas. */
export function formatNum(value: number | string | null | undefined): string {
  if (value == null) return "0";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "0";
  return num.toLocaleString("en-US");
}

/** Status color mapping. */
export function matchStatusColor(status: string): string {
  switch (status) {
    case "THREE_WAY_MATCHED": return "text-db-green";
    case "TWO_WAY_MATCHED": return "text-db-blue";
    case "AMOUNT_MISMATCH": return "text-db-red";
    case "NO_PO_REFERENCE": return "text-db-amber";
    default: return "text-text-secondary";
  }
}

export function matchStatusBg(status: string): string {
  switch (status) {
    case "THREE_WAY_MATCHED": return "bg-db-green/15 border-db-green/30";
    case "TWO_WAY_MATCHED": return "bg-db-blue/15 border-db-blue/30";
    case "AMOUNT_MISMATCH": return "bg-db-red/15 border-db-red/30";
    case "NO_PO_REFERENCE": return "bg-db-amber/15 border-db-amber/30";
    default: return "bg-bg-card border-border-subtle";
  }
}

export function matchStatusLabel(status: string): string {
  switch (status) {
    case "THREE_WAY_MATCHED": return "3-Way Matched";
    case "TWO_WAY_MATCHED": return "2-Way Matched";
    case "AMOUNT_MISMATCH": return "Amount Mismatch";
    case "NO_PO_REFERENCE": return "No PO Reference";
    default: return status;
  }
}

export function severityColor(severity: string): string {
  switch (severity) {
    case "critical": return "border-db-red bg-db-red/10";
    case "high": return "border-db-amber bg-db-amber/10";
    case "medium": return "border-db-blue bg-db-blue/10";
    default: return "border-border-subtle bg-bg-card";
  }
}

export function severityBadge(severity: string): string {
  switch (severity) {
    case "critical": return "bg-db-red/20 text-db-red";
    case "high": return "bg-db-amber/20 text-db-amber";
    case "medium": return "bg-db-blue/20 text-db-blue";
    default: return "bg-bg-card text-text-secondary";
  }
}

export function agingColor(bucket: string): string {
  if (bucket.includes("0-30")) return "#22C55E";
  if (bucket.includes("31-60")) return "#FF7033";
  if (bucket.includes("61-90")) return "#FF3621";
  if (bucket.includes("90+")) return "#DC2626";
  return "#6B7280";
}

/** KPI display helper: "—" when the backend is not serving live rows. */
export function dash<T>(value: T | null | undefined, fmt: (v: T) => string = (v) => String(v)): string {
  return value === null || value === undefined ? "—" : fmt(value);
}
