// Mirrors apps/api/src/gigscout/models.py and web/schemas.py. Keep the two in step.

export type LeadKind = "project" | "contract" | "hiring" | "inbound";
export type LeadStatus = "new" | "contacted" | "proposal" | "won" | "lost" | "archived";
export type Role = "admin" | "member";
export type RunMode = "auto" | "team" | "pipeline";
export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export const LEAD_KINDS: readonly LeadKind[] = ["project", "contract", "hiring", "inbound"];
export const LEAD_STATUSES: readonly LeadStatus[] = ["new", "contacted", "proposal", "won", "lost", "archived"];

export interface Budget {
  minimum: number | null;
  maximum: number | null;
  currency: string | null;
  usd_rate: number | null;
  kind: "fixed" | "hourly" | "salary" | "unknown";
}

export interface Client {
  name: string | null;
  country: string | null;
  email: string | null;
  phone: string | null;
}

export interface Lead {
  id: string;
  source: string;
  title: string;
  description: string;
  url: string;
  kind: LeadKind;
  skills: string[];
  budget: Budget | null;
  posted_at: string | null;
  client: Client | null;
  bid_count: number | null;
}

export interface LeadView {
  lead: Lead;
  seen_at: string | null;
  status: LeadStatus;
  notes: string;
  score: number | null;
  reasons: string;
  red_flags: string;
  pitch: string;
  similarity: number | null;
}

export interface LeadPage {
  items: LeadView[];
  total: number;
  page: number;
  page_size: number;
}

export interface LeadQuery {
  q?: string;
  kind?: LeadKind[];
  source?: string[];
  status?: LeadStatus[];
  min_score?: number;
  sort?: "score" | "recent" | "budget";
  page?: number;
  page_size?: number;
}

export interface AgencyProfile {
  name: string;
  /** What kind of company: "Software agency", "Marketing agency", "Law firm"… (free text). */
  company_type: string;
  pitch: string;
  services: string[];
  skills: string[];
  keywords: string[];
  industries: string[];
  exclude: string[];
  min_budget_usd: number | null;
  target_countries: string[];
  kinds: LeadKind[];
  sources: string[] | null;
}

/** A starting point for a common kind of company. */
export interface ProfileTemplate {
  company_type: string;
  description: string;
  services: string[];
  skills: string[];
  keywords: string[];
  exclude: string[];
  kinds: LeadKind[];
}

/** What the model (or the closest template) suggests for a company described in a sentence. */
export interface ProfileSuggestion {
  source: "ai" | "template" | "none";
  services: string[];
  skills: string[];
  keywords: string[];
  exclude: string[];
  industries: string[];
}

export interface ProfileRecord {
  id: number;
  name: string;
  data: AgencyProfile;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Run {
  id: string;
  profile_id: number | null;
  profile_name: string;
  mode_requested: RunMode;
  mode: "team" | "pipeline" | null;
  status: RunStatus;
  trigger: "manual" | "schedule";
  triggered_by: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  fetched_count: number;
  new_count: number;
  match_count: number;
  top_score: number;
  errors: string[];
}

export interface RunDetail extends Run {
  report: string;
  queries: string[];
  trace: string[];
}

/** Steps of a run, in order. A broadened pipeline run can revisit earlier steps. */
export type RunStage = "plan" | "search" | "qualify" | "write" | "report";
export type AgentKey = "head" | "prospector" | "qualifier" | "writer";

export interface ActivityLead {
  id: string;
  title: string;
  source: string;
  budget: number | null;
}

interface ActivityBase {
  /** Seconds since the run started. */
  t: number;
}

/** Structured run activity that drives the agent cockpit (streamed as `run.activity`, kept for replay). */
export type RunActivity = ActivityBase &
  (
    | { kind: "stage"; stage: RunStage; agent: AgentKey }
    | { kind: "act"; agent: AgentKey; what: string }
    | { kind: "progress"; agent: AgentKey; stage: RunStage | null; done: number; total: number; label: string }
    | { kind: "found"; source: string; leads: ActivityLead[] }
    | { kind: "reviewed"; lead: ActivityLead; score: number; qualified: boolean; reason: string | null }
    | { kind: "pitched"; lead: ActivityLead }
  );

export interface ScheduleInput {
  name: string;
  profile_id: number;
  cron: string;
  mode: RunMode;
  enabled: boolean;
}

export interface Schedule extends ScheduleInput {
  id: number;
  created_by: string;
  created_at: string;
  last_run_at: string | null;
  last_run_id: string | null;
  next_run_at: string | null;
}

export interface CronPreview {
  cron: string;
  valid: boolean;
  error: string | null;
  next_runs: string[];
}

export interface Overview {
  total_leads: number;
  new_last_24h: number;
  inbound_last_7d: number;
  qualified: number;
  by_kind: Partial<Record<LeadKind, number>>;
  by_source: Record<string, number>;
  by_status: Record<LeadStatus, number>;
  runs_total: number;
  runs_succeeded_7d: number;
  runs_failed_7d: number;
  avg_run_seconds: number | null;
  last_run_at: string | null;
  active_runs: { id: string; status: RunStatus; profile_name: string }[];
  live_clients: number;
}

export type TimeseriesRow = { date: string } & Record<LeadKind, number>;

export interface Analytics {
  timeseries: TimeseriesRow[];
  score_histogram: { from: number; to: number; count: number }[];
  competition: { id: string; title: string; kind: LeadKind; bids: number; budget_usd: number; score: number | null }[];
  funnel: { stage: string; count: number }[];
  runs: {
    id: string;
    at: string;
    status: RunStatus;
    mode: string;
    duration_seconds: number | null;
    fetched: number;
    new: number;
    matches: number;
    top_score: number;
  }[];
}

export interface MapPoint {
  id: string;
  title: string;
  kind: LeadKind;
  source: string;
  x: number;
  y: number;
  z: number;
  score: number | null;
}

export interface AskResponse {
  answer: string;
  sources: LeadView[];
}

/** One step of a streamed answer: what it is doing, which leads it read, the answer as it is written. */
export type AskStreamEvent =
  | { type: "status"; text: string }
  | { type: "sources"; sources: LeadView[]; elapsed: number }
  | { type: "token"; text: string }
  | { type: "done"; elapsed: number }
  | { type: "error"; message: string };

export interface SystemInfo {
  version: string;
  python: string;
  uptime_seconds: number;
  llm: { provider: string; model: string; available: boolean; reachable_now: boolean };
  embedding_model: string;
  vector_store: { leads: number; path: string };
  database: { url: string; users: number; runs: number };
  scheduler: { running: boolean; jobs: number; timezone: string };
  inbound: { google_ads_webhook: boolean };
  live_clients: number;
  mlflow: { enabled: boolean; tracking_uri: string };
}

export interface DigestConfig {
  enabled: boolean;
  /** Hour of day (0-23) in `timezone` it is sent at. */
  hour: number;
  timezone: string;
  emails: string[];
  /** A Slack webhook is saved (the URL itself is never returned). */
  slack_configured: boolean;
  min_score: number;
  max_leads: number;
  last_sent_at: string | null;
  last_result: string;
  /** SMTP is configured on the server, so email can be sent. */
  email_ready: boolean;
}

export interface DigestConfigInput {
  enabled: boolean;
  hour: number;
  emails: string[];
  /** null keeps the saved webhook; "" removes it. */
  slack_webhook: string | null;
  min_score: number;
  max_leads: number;
}

export interface SourceHealth {
  name: string;
  channel: "pull" | "push";
  enabled: boolean;
  recent_failures: number;
  last_error: string | null;
  /** A website an admin added (the rest are built in). */
  custom: boolean;
  id: number | null;
  label: string | null;
  url: string | null;
  /** How we read it: its RSS/Atom feed, or listing links on the page. */
  kind: "feed" | "page" | null;
  /** blocked = its robots.txt no longer allows automated access. */
  status: "ok" | "blocked" | "error" | null;
  /** What its listings are: someone wanting work done, a contract, or a company hiring. */
  lead_kind: ConnectorLeadKind | null;
}

/** A message to a lead: drafted (by the AI or a template), edited, sent, then tracked. */
export interface Outreach {
  id: number;
  lead_id: string;
  /** email = sent from your SMTP server; bid = pasted into the marketplace's proposal form. */
  channel: "email" | "bid";
  to: string | null;
  subject: string;
  body: string;
  status: "draft" | "sent" | "replied" | "no_reply";
  source: "ai" | "template";
  created_by: string;
  created_at: string;
  sent_at: string | null;
}

export interface OutreachInput {
  channel: "email" | "bid";
  to: string | null;
  subject: string;
  body: string;
}

export interface OutreachConfig {
  email_ready: boolean;
  /** Connected CRMs, e.g. ["hubspot"]. */
  crms: string[];
}

export interface CrmLink {
  crm: string;
  external_id: string;
  url: string | null;
  created_at: string;
}

export interface CrmSync {
  links: CrmLink[];
  errors: string[];
}

export type ConnectorLeadKind = "project" | "contract" | "hiring";

/** A checked public website from the source library, suggested per company type. */
export interface LibrarySource {
  name: string;
  url: string;
  description: string;
  region: string;
  lead_kind: ConnectorLeadKind;
  company_types: string[];
  /** Already connected. */
  added: boolean;
}

export interface SourceTestResult {
  name: string;
  ok: boolean;
  count: number;
  latency_ms: number;
  sample: string[];
  error: string | null;
}

export interface AuditEntry {
  id: number;
  at: string;
  actor: string;
  action: string;
  target: string;
  detail: Record<string, unknown>;
}

export interface LiveEvent<T = Record<string, unknown>> {
  id: number;
  type: string;
  at: string;
  data: T;
}
