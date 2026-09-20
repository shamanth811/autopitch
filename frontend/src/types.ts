// Mirrors autopitch.report.Report (see src/autopitch/schema.py and report.py).
export type SectionName = "problem" | "market" | "traction" | "team" | "moat" | "financials";

export interface CriterionScore { criterion: string; score: number; reasoning: string }
export interface SectionScore {
  section: SectionName;
  score: number;
  criteria: CriterionScore[];
  summary: string;
  missing_data: string[];
}
export interface TraceLine {
  section: SectionName;
  criterion: string;
  score: number;
  effective_weight: number;
  reasoning: string;
}
export interface Composite {
  score: number;
  weights: Partial<Record<SectionName, number>>;
  contributions: Partial<Record<SectionName, number>>;
  excluded: SectionName[];
  trace: TraceLine[];
}
export interface FundingPattern {
  id: string;
  company: string;
  sector: string;
  stage: string | null;
  round_amount_usd: number | null;
  year: number | null;
  source_url: string;
}
export interface Match { pattern: FundingPattern; similarity: number }
export interface FormDStats {
  industries: string[];
  sector_recognised: boolean;
  peers: number;
  p25_usd: number | null;
  median_usd: number | null;
  p75_usd: number | null;
  p90_usd: number | null;
  ask_percentile: number | null;
  period_start: string | null;
  period_end: string | null;
  flags: string[];
}
export interface Benchmark {
  formd: FormDStats | null;
  comparables: Match[];
  sector_matched: boolean;
  stage_comparables: number;
  median_raise_usd: number | null;
  raise_ratio: number | null;
  flags: string[];
}
export interface Objection {
  section: SectionName;
  question: string;
  basis: string;
  suggested_response: string;
}
export interface Deck {
  company: string;
  sector: string;
  stage: string | null;
  one_liner: string | null;
  financials: { raise_amount_usd: number | null };
}
export interface Report {
  version: string;
  generated_at: string;
  deck: Deck;
  composite: Composite;
  sections: SectionScore[];
  weak_sections: SectionName[];
  benchmark: Benchmark | null;
  objections: Objection[];
  disclaimer: string;
}

export type JobStatus = "queued" | "running" | "done" | "failed";
export type Stage = "queued" | "extract" | "score" | "benchmark" | "objections" | "done" | "failed";

export interface JobSummary {
  id: string;
  status: JobStatus;
  stage: Stage;
  filename: string;
  company: string | null;
  score: number | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}
export interface Job extends JobSummary {
  report: Report | null;
}

export interface Rubric {
  sections: { name: SectionName; criteria: { name: string; description: string }[] }[];
  weights_by_stage: Record<string, Partial<Record<SectionName, number>>>;
  weak_threshold: number;
}
