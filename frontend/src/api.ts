// Resolve API base URL at runtime:
// 1. window.__APP_CONFIG__.API_BASE (from public/config.js) — override at deploy time
// 2. import.meta.env.VITE_API_URL — baked in at build time
// 3. '/api' — fallback (works with Vite dev server proxy)
const API_BASE: string =
  (typeof window !== "undefined" && (window as any).__APP_CONFIG__?.API_BASE) ||
  import.meta.env.VITE_API_URL ||
  '/api';

export interface CalendarEvent {
  id: string;
  title: string;
  description?: string;
  source: string;
  scheduled_start: string;
  deadline: string;
  duration?: number;
  computed_end_time?: string;
  location?: string;
  priority?: string;
  status?: string;
  category: string;
  color_tag: string;
  recurring_rule?: Record<string, unknown>;
  metadata: Record<string, unknown>;
  tags: string[];
  created_at?: string;
  updated_at?: string;
  duration_minutes: number;
  is_feasible: boolean;
  is_overdue: boolean;
  is_recurring: boolean;
}

export interface Calendar {
  id: string;
  name: string;
  description?: string;
  events: CalendarEvent[];
  created_at?: string;
  updated_at?: string;
}

export interface DraftCalendar {
  id: string;
  events: CalendarEvent[];
  dirty?: string;
}

export interface CreateEventRequest {
  title: string;
  source?: string;
  scheduled_start: string;
  deadline: string;
  duration?: number;
  description?: string;
  location?: string;
  priority?: string;
  status?: string;
  category?: string;
  color_tag?: string;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export interface UpdateEventRequest {
  title?: string;
  description?: string;
  source?: string;
  scheduled_start?: string;
  deadline?: string;
  duration?: number;
  location?: string;
  priority?: string;
  status?: string;
  category?: string;
  color_tag?: string;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export interface ChatStreamEvent {
  event: string;
  data: string;
}

export interface CommitResult {
  ok: boolean;
  synced_count: number;
}

export interface ResetDraftResult {
  ok: boolean;
  reset_count: number;
}

export interface TermInfo {
  term_id: string;
  year: number;
  semester: number;
  label: string;
  status: string;
}

export interface CourseMeeting {
  course_id?: string | null;
  course_name: string;
  instructor?: string | null;
  location?: string | null;
  day_of_week?: number | null;
  start_slot?: number | null;
  end_slot?: number | null;
  weeks?: string | null;
  credits?: number | null;
  source: string;
  metadata: Record<string, unknown>;
  /** Backend flag indicating this course has no schedule info yet */
  _missing_schedule?: boolean;
}

export interface CourseSchedule {
  term: TermInfo;
  meetings: CourseMeeting[];
  source: string;
}

export interface RecommendationPlan {
  term: TermInfo;
  recommended_courses: {
    course_id?: string | null;
    course_name: string;
    credits?: number | null;
    score: number;
    reason?: string | null;
    status?: string;
    source?: string;
  }[];
  postponed_courses: {
    course_id?: string | null;
    course_name: string;
    credits?: number | null;
    score: number;
    reason?: string | null;
    status?: string;
    source?: string;
  }[];
  meetings: CourseMeeting[];
  warnings: string[];
  rationale: string;
  graduation_check: {
    status: string;
    summary: string;
    missing_courses: string[];
  };
}

export interface RecommendationExplanation {
  based_on: string[];
  matched_courses: Array<{
    course_code?: string | null;
    course_name: string;
    credits?: number | null;
    status?: string | null;
    source?: string | null;
    reason: string;
  }>;
  requirement_summary: string;
}

// Course planning chat types removed

export async function fetchCalendar(): Promise<Calendar> {
  const res = await fetch(`${API_BASE}/calendar`);
  if (!res.ok) throw new Error('Failed to fetch calendar');
  return res.json();
}

export async function fetchDraftCalendar(): Promise<DraftCalendar> {
  const res = await fetch(`${API_BASE}/calendar/draft`);
  if (!res.ok) throw new Error('Failed to fetch draft calendar');
  return res.json();
}

export async function createEvent(req: CreateEventRequest): Promise<DraftCalendar> {
  const res = await fetch(`${API_BASE}/calendar/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create event');
  }
  return res.json();
}

export async function updateEvent(eventId: string, req: UpdateEventRequest): Promise<DraftCalendar> {
  const res = await fetch(`${API_BASE}/calendar/events/${eventId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update event');
  }
  return res.json();
}

export async function deleteEvent(eventId: string): Promise<DraftCalendar> {
  const res = await fetch(`${API_BASE}/calendar/events/${eventId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete event');
  }
  return res.json();
}

export async function commitDraft(): Promise<CommitResult> {
  const res = await fetch(`${API_BASE}/calendar/commit`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to commit draft');
  return res.json();
}

export async function resetDraft(): Promise<ResetDraftResult> {
  const res = await fetch(`${API_BASE}/calendar/reset-draft`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to reset draft');
  return res.json();
}

export async function* streamChat(message: string): AsyncGenerator<ChatStreamEvent> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Chat API error: ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response stream');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let currentEvent = '';
    for (const line of lines) {
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        const data = line.slice(5).trim();
        if (data) {
          yield { event: currentEvent, data };
        }
      }
    }
  }
}

export async function resetAgent(): Promise<{ ok: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/chat/reset`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to reset agent');
  return res.json();
}

export interface HistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export async function fetchChatHistory(): Promise<{ ok: boolean; messages: HistoryMessage[] }> {
  const res = await fetch(`${API_BASE}/chat/history`);
  if (!res.ok) throw new Error('Failed to fetch chat history');
  return res.json();
}

export async function fetchChatStatus(): Promise<{ busy: boolean; agent_initialized: boolean }> {
  const res = await fetch(`${API_BASE}/chat/status`);
  if (!res.ok) throw new Error('Failed to fetch chat status');
  return res.json();
}

// ====================================================================
// Script Automation API
// ====================================================================

export interface ScriptOutputEvent {
  execution_id: string;
  stream: "stdout" | "stderr";
  message: string;
}

export interface ScriptExecutionEvent {
  execution_id: string;
  stage: "running" | "completed" | "killed";
  name?: string;
  message?: string;
  returncode?: number;
  ok?: boolean;
}

export async function* streamScriptChat(message: string): AsyncGenerator<ChatStreamEvent> {
  const res = await fetch(`${API_BASE}/script-chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Script Chat API error: ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response stream');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let currentEvent = '';
    for (const line of lines) {
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        const data = line.slice(5).trim();
        if (data) {
          yield { event: currentEvent, data };
        }
      }
    }
  }
}

// ====================================================================
// Campus QA API
// ====================================================================

export interface CampusQaStreamEvent {
  event: string;
  data: string;
}

export async function* streamCampusQa(
  message: string,
  courseScope?: string | null,
  sessionId?: string,
): AsyncGenerator<CampusQaStreamEvent> {
  const res = await fetch(`${API_BASE}/qa/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      course_scope: courseScope,
      session_id: sessionId,
    }),
  });

  if (!res.ok) {
    throw new Error(`Campus QA API error: ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response stream');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let currentEvent = '';
    for (const line of lines) {
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        const data = line.slice(5).trim();
        if (data) {
          yield { event: currentEvent, data };
        }
      }
    }
  }
}

export async function resetScriptAgent(): Promise<{ ok: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/script-chat/reset`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to reset script agent');
  return res.json();
}

export async function fetchScriptChatHistory(): Promise<{ ok: boolean; messages: HistoryMessage[] }> {
  const res = await fetch(`${API_BASE}/script-chat/history`);
  if (!res.ok) throw new Error('Failed to fetch script chat history');
  return res.json();
}

export async function fetchScriptChatStatus(): Promise<{ busy: boolean; agent_initialized: boolean }> {
  const res = await fetch(`${API_BASE}/script-chat/status`);
  if (!res.ok) throw new Error('Failed to fetch script chat status');
  return res.json();
}

export async function killScriptExecution(executionId: string): Promise<{ ok: boolean; execution_id: string; message: string }> {
  const res = await fetch(`${API_BASE}/script-chat/${executionId}/kill`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to kill execution');
  }
  return res.json();
}

export async function fetchCourseTerms(): Promise<{ terms: TermInfo[]; message?: string }> {
  const res = await fetch(`${API_BASE}/course-recommendation/terms`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch terms');
  }
  return res.json();
}

export async function fetchCourseSchedule(termId: string): Promise<CourseSchedule> {
  const params = new URLSearchParams({ term_id: termId });
  const res = await fetch(`${API_BASE}/course-recommendation/schedule?${params.toString()}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch schedule');
  }
  const payload = await res.json();
  return payload.schedule as CourseSchedule;
}

export async function requestCoursePlan(payload: {
  term_id: string;
  major?: string;
  interests?: string[];
  career_goal?: string;
  recommendation_note?: string;
  min_credits?: number;
  max_credits?: number;
  use_llm?: boolean;
}): Promise<RecommendationPlan> {
  const res = await fetch(`${API_BASE}/course-recommendation/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to generate course plan');
  }
  const data = await res.json();
  return data.plan as RecommendationPlan;
}

// ====================================================================
// Course Plan Streaming (SSE – shows live agent loop progress)
// ====================================================================

export interface CoursePlanStreamEvent {
  event: string;
  data: string;
}

/**
 * Stream course plan generation with live progress updates.
 * Yields `status` (progress text), `tool_progress` (tool call updates),
 * `thought` (AI reasoning), `done` (contains the final plan), and `error`.
 */
export async function* streamCoursePlan(payload: {
  term_id: string;
  major?: string;
  interests?: string[];
  career_goal?: string;
  recommendation_note?: string;
  min_credits?: number;
  max_credits?: number;
  use_llm?: boolean;
  avoid_time_slots?: string;
}): AsyncGenerator<CoursePlanStreamEvent> {
  const res = await fetch(`${API_BASE}/course-recommendation/plan/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to stream course plan');
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response stream');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let currentEvent = '';
    for (const line of lines) {
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        const data = line.slice(5).trim();
        if (data) {
          yield { event: currentEvent, data };
        }
      }
    }
  }
}

export async function fetchRecommendationExplanation(payload: {
  term_id: string;
  recommended_courses: Array<{ course_id?: string | null; course_name: string; credits?: number | null; status?: string | null; source?: string | null }>;
  postponed_courses?: Array<{ course_id?: string | null; course_name: string; credits?: number | null; status?: string | null; source?: string | null }>;
  user_major?: string;
  user_note?: string;
}): Promise<RecommendationExplanation> {
  const res = await fetch(`${API_BASE}/course-recommendation/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error('Failed to fetch explanation');
  }
  return res.json();
}
export function parseBackendEvent(raw: CalendarEvent): CalendarEvent {
  return raw;
}

// ====================================================================
// Script Sandbox Directory API
// ====================================================================

export interface SandboxDirResponse {
  directory: string;
  exists: boolean;
}

export interface UpdateSandboxDirResponse {
  ok: boolean;
  directory: string;
  error?: string;
}

export async function fetchScriptSandboxDir(): Promise<SandboxDirResponse> {
  const res = await fetch(`${API_BASE}/script-sandbox`);
  if (!res.ok) throw new Error('Failed to fetch script sandbox directory');
  return res.json();
}

export async function updateScriptSandboxDir(directory: string): Promise<UpdateSandboxDirResponse> {
  const res = await fetch(`${API_BASE}/script-sandbox`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ directory }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '未知错误' }));
    throw new Error(err.detail || 'Failed to update script sandbox directory');
  }
  return res.json();
}

// ====================================================================
// LLM Settings API
// ====================================================================

export interface LLMStatus {
  configured: boolean;
  provider?: string | null;
  base_url: string;
  fallback_provider?: string | null;
  fallback_base_url: string;
  fallback_enabled: boolean;
  has_api_key: boolean;
  has_fallback_key: boolean;
  api_key_masked: string;
  fallback_api_key_masked: string;
  tiers: Record<string, unknown>;
  llm_available: boolean;
}

export interface LLMTestResult {
  ok: boolean;
  message: string;
}

export interface LLMConfigPayload {
  provider: string;
  api_key?: string;
  base_url?: string;
  fallback_provider?: string;
  fallback_api_key?: string;
  fallback_base_url?: string;
  fallback_enabled?: boolean;
  tiers?: Record<string, unknown>;
}

export async function fetchLLMStatus(): Promise<LLMStatus> {
  const res = await fetch(`${API_BASE}/settings/llm/status`);
  if (!res.ok) throw new Error('Failed to fetch LLM status');
  return res.json();
}

export async function setLLMConfig(payload: LLMConfigPayload): Promise<LLMStatus> {
  const res = await fetch(`${API_BASE}/settings/llm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '未知错误' }));
    throw new Error(err.detail || 'Failed to set LLM config');
  }
  return res.json();
}

export async function testLLMConnection(payload: {
  provider: string;
  api_key: string;
  base_url?: string;
  model?: string;
}): Promise<LLMTestResult> {
  const res = await fetch(`${API_BASE}/settings/llm/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Failed to test LLM connection');
  return res.json();
}

// ====================================================================
// Credentials Settings API
// ====================================================================

export interface CredentialStatus {
  cas_configured: boolean;
  cas_username_masked: string;
  todoist_configured: boolean;
  todoist_token_masked: string;
}

export interface CredentialConfigPayload {
  cas_username?: string;
  cas_password?: string;
  todoist_token?: string;
}

export async function fetchCredentialStatus(): Promise<CredentialStatus> {
  const res = await fetch(`${API_BASE}/settings/credentials/status`);
  if (!res.ok) throw new Error('Failed to fetch credential status');
  return res.json();
}

export async function setCredentials(payload: CredentialConfigPayload): Promise<CredentialStatus> {
  const res = await fetch(`${API_BASE}/settings/credentials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '未知错误' }));
    throw new Error(err.detail || 'Failed to set credentials');
  }
  return res.json();
}

export function backendEventToFrontend(raw: CalendarEvent) {
  return {
    id: raw.id,
    title: raw.title,
    description: raw.description,
    source: raw.source,
    scheduled_start: raw.scheduled_start,
    deadline: raw.deadline,
    duration: raw.duration,
    computed_end_time: raw.computed_end_time,
    location: raw.location,
    priority: raw.priority,
    status: raw.status,
    category: raw.category,
    color_tag: raw.color_tag,
    recurring_rule: raw.recurring_rule,
    metadata: raw.metadata,
    tags: raw.tags,
    created_at: raw.created_at,
    updated_at: raw.updated_at,
    duration_minutes: raw.duration_minutes,
    is_feasible: raw.is_feasible,
    is_overdue: raw.is_overdue,
    is_recurring: raw.is_recurring,
  };
}
