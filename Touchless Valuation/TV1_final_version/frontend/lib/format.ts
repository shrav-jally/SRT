export const cr = (v: number | null | undefined): string =>
  v == null || Number.isNaN(v)
    ? "—"
    : `₹${Math.round(v).toLocaleString("en-IN")} Cr`;

export const mult = (v: number | null | undefined): string =>
  v == null ? "—" : `${v.toFixed(1)}×`;

export const pct = (v: number | null | undefined): string =>
  v == null ? "—" : `${(v * 100).toFixed(1)}%`;
