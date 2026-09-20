export const usd = (v: number | null | undefined): string => {
  if (!v) return "n/a";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${Math.round(v / 1e3)}K`;
  return `$${v}`;
};

export const cap = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

export const pct = (v: number): string => `${Math.round(v * 100)}%`;

export const when = (iso: string): string =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

export const words = (s: string): string => s.replace(/[_-]/g, " ");
