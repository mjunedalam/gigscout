import type {
  AgencyProfile,
  Analytics,
  AskResponse,
  AuditEntry,
  CronPreview,
  LeadPage,
  LeadQuery,
  LeadStatus,
  LeadView,
  LiveEvent,
  MapPoint,
  Overview,
  ProfileRecord,
  Role,
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
  SourceTestResult,
  SystemInfo,
  User,
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
  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await fetchImpl(`${baseUrl}${path}`, {
      method,
      credentials: "include",
      headers: body === undefined ? undefined : { "content-type": "application/json" },
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
      headers: { "content-type": "application/json" },
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
    auth: {
      login: (email: string, password: string) => request<{ user: User }>("POST", "/api/auth/login", { email, password }),
      logout: () => request<void>("POST", "/api/auth/logout"),
      me: () => get<User>("/api/auth/me"),
    },
    leads: {
      list: (query: LeadQuery = {}) => get<LeadPage>("/api/leads", { ...query }),
      get: (id: string) => get<LeadView>(`/api/leads/${encodeURIComponent(id)}`),
      update: (id: string, change: { status?: LeadStatus; notes?: string }) =>
        request<LeadView>("PATCH", `/api/leads/${encodeURIComponent(id)}`, change),
      ask: (question: string, k = 8) => request<AskResponse>("POST", "/api/leads/ask", { question, k }),
      askStream: (question: string, onEvent: (event: AskStreamEvent) => void, options: { k?: number; signal?: AbortSignal } = {}) =>
        stream<AskStreamEvent>("/api/leads/ask/stream", { question, k: options.k ?? 8 }, onEvent, options.signal),
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
    },
    events: {
      recent: (limit = 50) => get<LiveEvent[]>("/api/events/recent", { limit }),
      streamUrl: `${baseUrl}/api/events/stream`,
    },
    admin: {
      users: () => get<User[]>("/api/admin/users"),
      createUser: (input: { email: string; name: string; role: Role; password: string }) =>
        request<User>("POST", "/api/admin/users", input),
      updateUser: (id: number, change: { name?: string; role?: Role; is_active?: boolean; password?: string }) =>
        request<User>("PATCH", `/api/admin/users/${id}`, change),
      system: () => get<SystemInfo>("/api/admin/system"),
      settings: () => get<Record<string, unknown>>("/api/admin/settings"),
      sources: () => get<SourceHealth[]>("/api/admin/sources"),
      testSource: (name: string) => request<SourceTestResult>("POST", `/api/admin/sources/${encodeURIComponent(name)}/test`),
      addConnector: (name: string, url: string) => request<SourceHealth>("POST", "/api/admin/connectors", { name, url }),
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
