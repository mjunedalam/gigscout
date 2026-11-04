import type {
  AgencyProfile,
  Analytics,
  AskResponse,
  AuditEntry,
  CronPreview,
  LeadPage,
  LeadQuery,
  LeadView,
  LiveEvent,
  MapPoint,
  Overview,
  ProfileRecord,
  Run,
  DigestConfig,
  DigestConfigInput,
  ProfileSuggestion,
  ProfileTemplate,
  RunActivity,
  AskStreamEvent,
  RunDetail,
  RunMode,
  Schedule,
  ScheduleInput,
  SourceHealth,
  ConnectorLeadKind,
  LibrarySource,
  IntegrationStatus,
  Learning,
  CrmSync,
  Outreach,
  OutreachConfig,
  OutreachInput,
  SourceTestResult,
  SystemInfo,
  User,
  Member,
  WorkspaceDetail,
  SetupStep,
  LeadChange,
  Billing,
  BillingPlan,
  WorkspaceRole,
  WorkspaceSummary,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type Fetch = typeof fetch;
type Params = Record<string, string | number | boolean | readonly (string | number)[] | undefined | null>;

export function toQuery(params: Params = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, String(v)));
    else search.append(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/** FastAPI errors come as {detail: string} or {detail: [{msg, loc}]}; turn either into one readable line. */
export function errorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object" || !("detail" in body)) return fallback;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
        return field ? `${field}: ${d.msg}` : (d.msg ?? "");
      })
      .join("; ");
  }
  return fallback;
}

export function createClient(baseUrl = "", fetchImpl: Fetch = (...args) => fetch(...args)) {
  let workspace: number | null = null; // sent with every request; the server falls back to the user's first
  const scope = (): Record<string, string> => (workspace === null ? {} : { "x-workspace": String(workspace) });

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await fetchImpl(`${baseUrl}${path}`, {
      method,
      credentials: "include",
      headers: body === undefined ? scope() : { ...scope(), "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 204) return undefined as T;
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) throw new ApiError(response.status, errorMessage(payload, response.statusText));
    return payload as T;
  }

  const get = <T>(path: string, params?: Params) => request<T>("GET", path + toQuery(params));

  /** POST and read a newline-delimited JSON stream, one event per line, until it ends or is aborted. */
  async function stream<E>(path: string, body: unknown, onEvent: (event: E) => void, signal?: AbortSignal) {
    const response = await fetchImpl(`${baseUrl}${path}`, {
      method: "POST",
      credentials: "include",
      headers: { ...scope(), "content-type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (!response.ok || !response.body) {
      const payload: unknown = await response.json().catch(() => null);
      throw new ApiError(response.status, errorMessage(payload, response.statusText));
    }
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? ""; // a line split across chunks waits for the rest
      for (const line of lines) if (line.trim()) onEvent(JSON.parse(line) as E);
    }
    if (buffer.trim()) onEvent(JSON.parse(buffer) as E);
  }

  return {
    /** Which workspace every following request works in. */
    setWorkspace: (id: number | null) => {
      workspace = id;
    },
    workspaces: {
      list: () => get<WorkspaceSummary[]>("/api/workspaces"),
      create: (name: string) => request<WorkspaceSummary>("POST", "/api/workspaces", { name }),
      current: () => get<WorkspaceDetail>("/api/workspaces/current"),
      rename: (name: string) => request<WorkspaceDetail>("PATCH", "/api/workspaces/current", { name }),
      rotateFormKey: () => request<WorkspaceDetail>("POST", "/api/workspaces/current/form-key"),
      setup: () => get<SetupStep[]>("/api/workspaces/current/setup"),
      members: () => get<{ id: number; name: string; email: string }[]>("/api/workspaces/current/members"),
    },
    billing: {
      get: () => get<Billing>("/api/billing"),
      /** Stripe Checkout's address; the plan starts when Stripe confirms the payment. */
      checkout: (plan: BillingPlan["id"]) => request<{ url: string }>("POST", "/api/billing/checkout", { plan }),
      portal: () => request<{ url: string }>("POST", "/api/billing/portal"),
    },
    auth: {
      login: (email: string, password: string) => request<{ user: User }>("POST", "/api/auth/login", { email, password }),
      logout: () => request<void>("POST", "/api/auth/logout"),
      me: () => get<User>("/api/auth/me"),
    },
    leads: {
      list: (query: LeadQuery = {}) => get<LeadPage>("/api/leads", { ...query }),
      get: (id: string) => get<LeadView>(`/api/leads/${encodeURIComponent(id)}`),
      update: (id: string, change: LeadChange) =>
        request<LeadView>("PATCH", `/api/leads/${encodeURIComponent(id)}`, change),
      ask: (question: string, k = 8) => request<AskResponse>("POST", "/api/leads/ask", { question, k }),
      askStream: (question: string, onEvent: (event: AskStreamEvent) => void, options: { k?: number; signal?: AbortSignal } = {}) =>
        stream<AskStreamEvent>("/api/leads/ask/stream", { question, k: options.k ?? 8 }, onEvent, options.signal),
    },
    outreach: {
      config: () => get<OutreachConfig>("/api/outreach/config"),
      list: (leadId: string) => get<Outreach[]>("/api/outreach", { lead_id: leadId }),
      draft: (leadId: string, profileId?: number) =>
        request<Outreach>("POST", "/api/outreach", { lead_id: leadId, profile_id: profileId ?? null }),
      edit: (id: number, change: OutreachInput) => request<Outreach>("PUT", `/api/outreach/${id}`, change),
      send: (id: number) => request<Outreach>("POST", `/api/outreach/${id}/send`),
      setStatus: (id: number, status: "replied" | "no_reply") =>
        request<Outreach>("POST", `/api/outreach/${id}/status`, { status }),
      crmLinks: (leadId: string) => get<CrmSync>("/api/outreach/crm", { lead_id: leadId }),
      pushToCrm: (leadId: string) => request<CrmSync>("POST", "/api/outreach/crm", { lead_id: leadId }),
    },
    profiles: {
      list: () => get<ProfileRecord[]>("/api/profiles"),
      create: (profile: AgencyProfile) => request<ProfileRecord>("POST", "/api/profiles", profile),
      update: (id: number, profile: AgencyProfile) => request<ProfileRecord>("PUT", `/api/profiles/${id}`, profile),
      remove: (id: number) => request<void>("DELETE", `/api/profiles/${id}`),
      templates: () => get<ProfileTemplate[]>("/api/profiles/templates"),
      suggest: (company_type: string, description: string) =>
        request<ProfileSuggestion>("POST", "/api/profiles/suggest", { company_type, description }),
    },
    runs: {
      list: (limit = 50) => get<Run[]>("/api/runs", { limit }),
      get: (id: string) => get<RunDetail>(`/api/runs/${id}`),
      start: (profile_id: number, mode: RunMode) => request<Run>("POST", "/api/runs", { profile_id, mode }),
      cancel: (id: string) => request<{ status: string }>("POST", `/api/runs/${id}/cancel`),
      activity: (id: string) => get<RunActivity[]>(`/api/runs/${id}/activity`),
    },
    schedules: {
      list: () => get<Schedule[]>("/api/schedules"),
      preview: (cron: string) => get<CronPreview>("/api/schedules/preview", { cron }),
      create: (input: ScheduleInput) => request<Schedule>("POST", "/api/schedules", input),
      update: (id: number, input: ScheduleInput) => request<Schedule>("PUT", `/api/schedules/${id}`, input),
      remove: (id: number) => request<void>("DELETE", `/api/schedules/${id}`),
      trigger: (id: number) => request<{ run_id: string }>("POST", `/api/schedules/${id}/trigger`),
    },
    metrics: {
      overview: () => get<Overview>("/api/metrics/overview"),
      analytics: (days = 14) => get<Analytics>("/api/metrics/analytics", { days }),
      map: () => get<MapPoint[]>("/api/metrics/map"),
      learning: () => get<Learning>("/api/metrics/learning"),
    },
    events: {
      recent: (limit = 50) => get<LiveEvent[]>("/api/events/recent", { limit }),
      /** EventSource cannot send headers, so the workspace travels in the query string. */
      get streamUrl() {
        return `${baseUrl}/api/events/stream${toQuery({ workspace })}`;
      },
    },
    admin: {
      users: () => get<Member[]>("/api/admin/users"),
      /** A new email creates the account (password required); an existing account just joins the workspace. */
      createUser: (input: { email: string; name: string; role: WorkspaceRole; password?: string }) =>
        request<Member>("POST", "/api/admin/users", input),
      updateUser: (id: number, change: { name?: string; role?: WorkspaceRole; is_active?: boolean; password?: string }) =>
        request<Member>("PATCH", `/api/admin/users/${id}`, change),
      removeUser: (id: number) => request<void>("DELETE", `/api/admin/users/${id}`),
      system: () => get<SystemInfo>("/api/admin/system"),
      settings: () => get<Record<string, unknown>>("/api/admin/settings"),
      sources: () => get<SourceHealth[]>("/api/admin/sources"),
      testSource: (name: string) => request<SourceTestResult>("POST", `/api/admin/sources/${encodeURIComponent(name)}/test`),
      addConnector: (name: string, url: string, lead_kind: ConnectorLeadKind = "project") =>
        request<SourceHealth>("POST", "/api/admin/connectors", { name, url, lead_kind }),
      upwork: () => get<IntegrationStatus>("/api/admin/upwork"),
      connectUpwork: () => request<{ url: string }>("POST", "/api/admin/upwork/connect"),
      disconnectUpwork: () => request<void>("DELETE", "/api/admin/upwork"),
      connectorLibrary: (companyType?: string) =>
        get<LibrarySource[]>("/api/admin/connectors/library", companyType ? { company_type: companyType } : undefined),
      removeConnector: (id: number) => request<void>("DELETE", `/api/admin/connectors/${id}`),
      setSourceEnabled: (name: string, enabled: boolean) =>
        request<{ name: string; enabled: boolean }>("PUT", `/api/admin/sources/${encodeURIComponent(name)}/enabled`, { enabled }),
      audit: (limit = 100) => get<AuditEntry[]>("/api/admin/audit", { limit }),
      digest: () => get<DigestConfig>("/api/admin/digest"),
      saveDigest: (input: DigestConfigInput) => request<DigestConfig>("PUT", "/api/admin/digest", input),
      previewDigest: () => request<{ count: number; markdown: string }>("POST", "/api/admin/digest/preview"),
      sendDigest: () => request<{ sent: string[]; count: number; errors: string[] }>("POST", "/api/admin/digest/send"),
    },
  };
}

export type GigScoutClient = ReturnType<typeof createClient>;
