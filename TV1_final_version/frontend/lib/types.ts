export type SearchHit = {
  code: number;
  name: string;
  sector: string | null;
  industry: string | null;
  revenue: number | null;
  valuation_grade: boolean;
};

export type SectorNode = {
  sector: string;
  n: number;
  industries: { industry: string; n: number }[];
};

export type Method = {
  method: string;
  status: string;
  reason?: string;
  target_driver?: number;
  n_peers?: number;
  n_outliers_dropped?: number;
  multiple_low?: number;
  multiple_mid?: number;
  multiple_high?: number;
  peer_multiple_median?: number;
  dispersion_cv?: number;
  ev_mid?: number;
  equity_low?: number;
  equity_mid?: number;
  equity_high?: number;
  equity_requires?: string[];
};

export type Peer = {
  code: number;
  name: string;
  sector: string;
  industry: string;
  revenue: number | null;
  ebitda: number | null;
  pat: number | null;
  net_worth: number | null;
  total_debt: number | null;
  cash: number | null;
  market_cap: number | null;
  enterprise_value: number | null;
  ebitda_margin: number | null;
  pat_margin: number | null;
  pe: number | null;
  ev_ebitda: number | null;
  ev_revenue: number | null;
  mktcap_sales: number | null;
  score: number;
  selected_because: string[];
  differences: string[];
};

export type PeerStats = {
  n: number;
  min?: number;
  max?: number;
  median?: number;
  values?: number[];
};

export type Calculation = {
  ratio: string;
  applies: boolean;
  reason?: string;
  peer_stats?: PeerStats;
  multiple_used?: number;
  multiple_source?: string;
  driver_label?: string;
  driver_value?: number;
  enterprise_value?: number | null;
  net_debt?: number | null;
  equity_value?: number | null;
  formula?: string;
};

export type LlmCheck = {
  estimate_cr: number;
  confidence: "high" | "medium" | "low";
  verdict: "low" | "fair" | "high";
  comment: string;
  model: string;
  weight_applied: number;
  engine_equity_mid: number;
};

export type Valuation = {
  headline_method: string | null;
  blended_equity_mid: number | null;
  equity_low: number | null;
  equity_mid: number | null;
  equity_high: number | null;
  ev_low: number | null;
  ev_mid: number | null;
  ev_high: number | null;
  net_debt: number | null;
  equity_requires: string[] | null;
  quality_percentile: number;
  methods: Method[];
  market_cross_check: {
    own_market_cap: number;
    implied_equity_mid: number;
    delta_pct: number;
    within_25pct: boolean;
  } | null;
  confidence: {
    score: number;
    label: "HIGH" | "MEDIUM" | "LOW";
    n_peers: number;
    dispersion: "tight" | "moderate" | "wide";
    dispersion_cv: number;
    method_agreement: number;
  };
};

export type Approach = {
  approach: string;
  status: string;
  reason?: string;
  equity_low?: number;
  equity_mid?: number;
  equity_high?: number;
  ev_mid?: number;
  headline?: {
    multiple_kind: string;
    multiple: number;
    multiple_basis?: {
      method: string;
      r2?: number;
      regression_multiple?: number;
      peer_median?: number;
      n?: number;
    };
  };
  supporting?: { multiple_kind: string; multiple: number; equity_mid?: number }[];
  calculations?: Calculation[];
  assumptions?: Record<string, unknown>;
  components?: Record<string, number>;
};

export type Conclusion = {
  status: string;
  reason?: string;
  weights?: Record<string, number>;
  approach_equity_mid?: Record<string, number>;
  equity_low?: number;
  equity_mid?: number;
  equity_high?: number;
  dlom?: number;
  control_premium?: number;
  adjustments?: string[];
  ev_mid?: number;
  equity_requires?: string[];
};

export type LiveMarket = {
  source: string;
  matched_name: string;
  url: string;
  market_cap_cr: number;
  pe: number | null;
  vs_conclusion_pct?: number;
  stored_market_cap_cr?: number;
  snapshot_staleness_pct?: number;
};

export type ProResult = {
  status: string;
  message?: string;
  target: Result["target"];
  live_market: LiveMarket | null;
  peer_discovery?: { tier?: string; pool?: number };
  peers: Peer[];
  approaches: Approach[];
  conclusion: Conclusion;
  llm_check: LlmCheck | null;
  market_cross_check: {
    own_market_cap: number;
    conclusion_equity_mid: number;
    delta_pct: number;
    within_25pct: boolean;
  } | null;
  caveats: string[];
  intake_inputs?: Record<string, number | string>;
};

export type IntakeQuestion = {
  question: string;
  key: string;
  kind: "pct" | "cr" | "yn";
  default: number | string;
  step: number;
  total: number;
};

export type IntakeResponse = {
  thread_id: string;
  done: boolean;
  question?: IntakeQuestion;
  result?: ProResult;
};

export type Result = {
  status: string;
  message?: string;
  target: Record<string, unknown> & {
    name: string;
    code?: number;
    sector: string | null;
    industry: string | null;
    revenue: number | null;
    ebitda: number | null;
    pat: number | null;
    ebitda_margin: number | null;
    net_debt_effective: number | null;
    listed?: boolean;
  };
  peer_discovery?: { tier?: string; pool?: number; sector_pool?: number };
  peers: Peer[];
  valuation?: Valuation;
  caveats: string[];
};
