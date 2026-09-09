/**
 * Cliente del backend FastAPI.
 * Se ejecuta SOLO en servidor: el token vive en una cookie httpOnly y nunca
 * llega al JavaScript del navegador.
 */

export type Role = "ADMIN" | "SUPERVISOR" | "EMPLOYEE";
export type ShiftId = "SHIFT_1" | "SHIFT_2" | "SHIFT_3" | "SHIFT_4";
export type ShiftColor = "green" | "blue" | "red" | "yellow" | "purple";
export type ShiftSource = "FIXED" | "ROTATION" | "APPROVED_CHANGE";
export type ChangeStatus = "PENDING" | "APPROVED" | "REJECTED" | "SUPERSEDED";
export type Weekday =
  | "MONDAY" | "TUESDAY" | "WEDNESDAY" | "THURSDAY" | "FRIDAY" | "SATURDAY" | "SUNDAY";

export interface ApiUser {
  id: number;
  name: string;
  email: string;
  role: Role;
  shift: ShiftId;
}

export interface UserBrief {
  id: number;
  name: string;
  role: Role;
}

export interface ShiftInfo {
  id: ShiftId;
  name: string;
  color: ShiftColor;
}

export interface ShiftDefinition {
  id: string; // incluye "HOLIDAY" en el catálogo
  name: string;
  color: ShiftColor;
  start: string;
  end: string;
}

export interface DaySchedule {
source: unknown;
  date: string;
  weekday: Weekday;
  day_name: string;
  start: string | null;
  end: string | null;
  is_holiday: boolean;
  holiday_name: string | null;
  is_custom: boolean;
  custom_shift: ShiftInfo | null;
}

export interface DayOverrideEntry {
  id: number;
  user: UserBrief;
  date: string;
  shift: ShiftInfo | null;
  start: string | null;
  end: string | null;
  reason: string | null;
  created_by: UserBrief;
  created_at: string;
}

export interface WeekSchedule {
  week_start: string;
  today: string; // «hoy» en la zona del negocio (marcador «Hoy»)
  shift: ShiftInfo;
  source: ShiftSource;
  days: DaySchedule[];
}

export interface TodaySchedule {
  date: string;
  weekday: Weekday;
  day_name: string;
  start: string | null;
  end: string | null;
  is_holiday: boolean;
  holiday_name: string | null;
  shift: ShiftInfo;
  source: ShiftSource;
}

export interface RotationEntry {
  week_start: string;
  shift: ShiftInfo;
  source: ShiftSource;
}

export interface TeamMember {
  user: UserBrief;
  shift: ShiftInfo;
  source: ShiftSource;
  override_change_id: number | null;
  days: DaySchedule[];
  day_overrides: DayOverrideEntry[];
}

export interface TeamWeek {
  week_start: string;
  today: string;
  members: TeamMember[];
}

export interface ScheduleChange {
  id: number;
  user: UserBrief;
  week_start: string;
  requested_shift: ShiftInfo;
  reason: string | null;
  status: ChangeStatus;
  review_note: string | null;
  requested_by: UserBrief;
  reviewed_by: UserBrief | null;
  created_at: string;
  reviewed_at: string | null;
  current_shift: ShiftInfo | null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const API_URL = import.meta.env.API_URL ?? "http://localhost:8000";

interface RequestOptions {
  method?: string;
  token?: string;
  body?: unknown;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    let detail = `Error ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* respuesta sin JSON */
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// ---------- Autenticación ----------

export function login(email: string, password: string) {
  return request<{ access_token: string; token_type: string; user: ApiUser }>(
    "/api/v1/auth/login",
    { method: "POST", body: { email, password } },
  );
}

export function fetchMe(token: string) {
  return request<ApiUser>("/api/v1/auth/me", { token });
}

// ---------- Horarios ----------

export function fetchTodaySchedule(token: string) {
  return request<TodaySchedule>("/api/v1/schedules/me", { token });
}

export function fetchWeekSchedule(token: string, weekStart?: string) {
  const query = weekStart ? `?week_start=${weekStart}` : "";
  return request<WeekSchedule>(`/api/v1/schedules/week${query}`, { token });
}

export function fetchShifts(token: string) {
  return request<ShiftDefinition[]>("/api/v1/schedules/shifts", { token });
}

export function fetchRotationPreview(token: string, weeks = 4) {
  return request<{ weeks: RotationEntry[] }>(
    `/api/v1/schedules/me/rotation?weeks=${weeks}`,
    { token },
  );
}

export function fetchTeamWeek(token: string, weekStart?: string) {
  const query = weekStart ? `?week_start=${weekStart}` : "";
  return request<TeamWeek>(`/api/v1/schedules/team/week${query}`, { token });
}

// ---------- Novedades ----------

export function fetchMyChanges(token: string) {
  return request<ScheduleChange[]>("/api/v1/changes/me", { token });
}

export function fetchPendingChanges(token: string, weekStart?: string) {
  const query = weekStart ? `?week_start=${weekStart}` : "";
  return request<ScheduleChange[]>(`/api/v1/changes/pending${query}`, { token });
}

export function fetchChanges(token: string, status?: string) {
  const query = status ? `?status=${status}` : "";
  return request<ScheduleChange[]>(`/api/v1/changes${query}`, { token });
}

export function createChange(
  token: string,
  payload: { week_start: string; requested_shift: string; reason?: string; user_id?: number },
) {
  return request<ScheduleChange>("/api/v1/changes", { method: "POST", token, body: payload });
}

export function reviewChange(
  token: string,
  changeId: number,
  decision: "approve" | "reject",
  note?: string,
) {
  return request<ScheduleChange>(`/api/v1/changes/${changeId}/${decision}`, {
    method: "POST",
    token,
    body: { note: note ?? null },
  });
}

export function revertChange(token: string, changeId: number) {
  return request<void>(`/api/v1/changes/${changeId}`, { method: "DELETE", token });
}

// ---------- Usuarios (admin) ----------

export interface UserAdmin {
  id: number;
  name: string;
  email: string;
  role: Role;
  shift: ShiftId;
  rotation_position: number | null;
  is_active: boolean;
  created_at: string;
}

export interface UserList {
  total: number;
  items: UserAdmin[];
}


export function fetchUsers(
  token: string,
  filters?: { role?: string; active?: string; page?: number; limit?: number },
) {
  const params = new URLSearchParams();
  if (filters?.role) params.set("role", filters.role);
  if (filters?.active) params.set("active", filters.active);
  if (filters?.limit) params.set("limit", String(filters.limit));
  if (filters?.page) params.set("offset", String((filters.page - 1) * (filters.limit ?? 50)));
  const query = params.toString() ? `?${params.toString()}` : "";
  return request<UserList>(`/api/v1/users${query}`, { token });
}

export function createUser(token: string, payload: Record<string, unknown>) {
  return request<UserAdmin>("/api/v1/users", { method: "POST", token, body: payload });
}

export function updateUser(token: string, userId: number, payload: Record<string, unknown>) {
  return request<UserAdmin>(`/api/v1/users/${userId}`, { method: "PATCH", token, body: payload });
}

export function deactivateUser(token: string, userId: number) {
  return request<void>(`/api/v1/users/${userId}`, { method: "DELETE", token });
}

// ---------- Festivos ----------

export interface HolidayItem {
  date: string; // "YYYY-MM-DD"
  name: string;
}

export interface HolidaysYear {
  year: number;
  provider: "google" | "local" | string;
  holidays: HolidayItem[];
}

export function fetchHolidays(token: string, year?: number) {
  const query = year ? `?year=${year}` : "";
  return request<HolidaysYear>(`/api/v1/schedules/holidays${query}`, { token });
}


// ---------- Perfil ----------

export function changePassword(token: string, currentPassword: string, newPassword: string) {
  return request<void>("/api/v1/auth/change-password", {
    method: "POST",
    token,
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

// ---------- Auditoría (admin) ----------

export interface AuditEntry {
  id: number;
  event: string;
  actor: UserBrief | null;
  target_user: UserBrief | null;
  detail: string | null;
  created_at: string;
}

export interface AuditList {
  total: number;
  items: AuditEntry[];
}

export function fetchAuditLogs(
  token: string,
  params?: { event?: string; page?: number; limit?: number },
) {
  const search = new URLSearchParams();
  if (params?.event) search.set("event", params.event);
  if (params?.limit) search.set("limit", String(params.limit));
  if (params?.page) search.set("offset", String((params.page - 1) * (params.limit ?? 50)));
  const query = search.toString() ? `?${search.toString()}` : "";
  return request<AuditList>(`/api/v1/audit${query}`, { token });
}


// ---------- Horarios personalizados por día (supervisor/admin) ----------

export function createDayOverride(
  token: string,
  payload: { user_id: number; date: string; shift?: string; start?: string; end?: string; reason?: string },
) {
  return request<DayOverrideEntry>("/api/v1/day-overrides", { method: "POST", token, body: payload });
}

export function deleteDayOverride(token: string, overrideId: number) {
  return request<void>(`/api/v1/day-overrides/${overrideId}`, { method: "DELETE", token });
}


export type TaskStatus = "PENDING" | "IN_PROGRESS" | "DONE";
export type TaskPriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";

export interface TaskExternal { system: string; id: string; url: string; }

export interface TaskEvent {
  id: number;
  user: UserBrief;
  event: string;
  detail: string | null;
  created_at: string;
}

export interface Task {
  id: number;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  assignee: UserBrief | null;
  created_by: UserBrief;
  due_date: string | null;
  is_overdue: boolean;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  external: TaskExternal | null;
}

export interface TaskDetail extends Task { events: TaskEvent[]; }
export interface TaskList { total: number; today: string; items: Task[]; }

export function fetchTasks(token: string, params?: { status?: string; priority?: string; page?: number; limit?: number }) {
  const search = new URLSearchParams();
  if (params?.status) search.set("status", params.status);
  if (params?.priority) search.set("priority", params.priority);
  if (params?.limit) search.set("limit", String(params.limit));
  if (params?.page) search.set("offset", String((params.page - 1) * (params.limit ?? 50)));
  const query = search.toString() ? `?${search.toString()}` : "";
  return request<TaskList>(`/api/v1/tasks${query}`, { token });
}

export function fetchTask(token: string, taskId: number) {
  return request<TaskDetail>(`/api/v1/tasks/${taskId}`, { token });
}

export function createTask(token: string, payload: Record<string, unknown>) {
  return request<TaskDetail>("/api/v1/tasks", { method: "POST", token, body: payload });
}

export function updateTask(token: string, taskId: number, payload: Record<string, unknown>) {
  return request<TaskDetail>(`/api/v1/tasks/${taskId}`, { method: "PATCH", token, body: payload });
}

export function deleteTask(token: string, taskId: number) {
  return request<void>(`/api/v1/tasks/${taskId}`, { method: "DELETE", token });
}

export function pushTask(token: string, taskId: number, target: "jira" | "trello") {
  return request<TaskDetail>(`/api/v1/tasks/${taskId}/push`, { method: "POST", token, body: { target } });
}