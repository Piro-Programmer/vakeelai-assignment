/**
 * Thin typed wrapper around the FastAPI backend.
 *
 * Every call goes through `request()`, so error handling is uniform: the
 * backend returns `{status:"error", message}` for scraper failures and
 * `{detail:{message, errors}}` for draft validation, and both become an
 * ApiError the UI can display (errors can be mapped onto form fields).
 */

export const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number
  fieldErrors?: Record<string, string>
  constructor(message: string, status: number, fieldErrors?: Record<string, string>) {
    super(message)
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(API_BASE + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError('Cannot reach the server. Is the backend running?', 0)
  }
  if (res.ok) {
    const type = res.headers.get('content-type') ?? ''
    return (type.includes('application/json') ? res.json() : res.blob()) as Promise<T>
  }
  let body: { message?: string; detail?: string | { message?: string; errors?: Record<string, string> } } | null = null
  try {
    body = await res.json()
  } catch {
    /* non-JSON error page (e.g. proxy timeout) */
  }
  const detail = body?.detail
  const message =
    body?.message ?? (typeof detail === 'string' ? detail : detail?.message) ?? `Request failed (${res.status})`
  throw new ApiError(message, res.status, typeof detail === 'object' ? detail?.errors : undefined)
}

const post = <T,>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) })

/** Absolute URL for backend-relative links such as `pdf_url` (opened in a new tab). */
export const apiUrl = (path: string) => API_BASE + path

// ------------------------------------------------------------------ cases
export type Option = { value: string; label: string }
export type ComplexOption = Option & { code: string; establishment_codes: string[]; requires_establishment: boolean }

export type Party = { name: string; advocates: string[]; details: string | null }
export type Hearing = {
  judge: string | null
  business_on_date: string | null
  hearing_date: string | null
  purpose_of_hearing: string | null
  business_url?: string
}
export type Order = { order_number: string | null; order_date: string | null; order_details: string | null; pdf_url: string | null }

export type CaseData = {
  court_name: string | null
  summary: {
    cnr: string | null
    title: string
    case_type: string | null
    registration_number: string | null
    court: string | null
    is_disposed: boolean
    next_hearing_date: string | null
    decision_date: string | null
    stage: string | null
  }
  case_details: Record<string, string | null>
  case_status: Record<string, string | null>
  petitioners: Party[]
  respondents: Party[]
  acts: { act: string | null; sections: string | null }[]
  fir_details: Record<string, string | null> | null
  hearing_history: Hearing[]
  interim_orders: Order[]
  final_orders: Order[]
  processes?: Record<string, string | null>[]
  case_transfers?: Record<string, string | null>[]
  subordinate_court?: unknown
  ia_status?: unknown
  linked_cases?: unknown
  other_sections?: Record<string, unknown>
  source: { portal: string; fetched_at: string }
}

export type Match = {
  sr_no: string
  establishment: string | null
  case_number: string
  petitioner: string | null
  respondent: string | null
  title: string
  cnr: string | null
  detail_ref: string
}

export type CaptchaRequired = {
  status: 'captcha_required'
  search_id: string
  captcha_image: string
  message: string
  expires_in: number
}
export type CaseResult = { status: 'ok'; type: 'case'; case: CaseData; captcha?: { mode: string; attempts?: number } }
export type MatchesResult = { status: 'ok'; type: 'matches'; matches: Match[]; captcha?: { mode: string; attempts?: number } }
export type SearchResult = CaseResult | MatchesResult | CaptchaRequired

export type CaseNumberQuery = {
  state_code: string
  dist_code: string
  court_complex: string
  est_code: string | null
  case_type: string
  case_number: string
  year: string
}

export const casesApi = {
  states: () => request<Option[]>('/api/meta/states'),
  districts: (state: string) => request<Option[]>(`/api/meta/districts?state=${encodeURIComponent(state)}`),
  complexes: (state: string, district: string) =>
    request<ComplexOption[]>(`/api/meta/complexes?state=${state}&district=${district}`),
  establishments: (state: string, district: string, complex: string) =>
    request<Option[]>(`/api/meta/establishments?state=${state}&district=${district}&complex=${encodeURIComponent(complex)}`),
  caseTypes: (state: string, district: string, complex: string, est: string) =>
    request<Option[]>(
      `/api/meta/case-types?state=${state}&district=${district}&complex=${encodeURIComponent(complex)}&establishment=${est}`,
    ),
  searchCnr: (cnr: string) => post<SearchResult>('/api/cases/cnr', { cnr }),
  searchCaseNumber: (q: CaseNumberQuery) => post<SearchResult>('/api/cases/case-number', q),
  submitCaptcha: (search_id: string, code: string) => post<SearchResult>('/api/cases/captcha', { search_id, code }),
  detail: (detail_ref: string) => post<CaseResult>('/api/cases/detail', { detail_ref }),
  business: (url: string) => request<{ status: string; business: Record<string, string | null> }>(url),
}

// ------------------------------------------------------------------ drafts
export type FieldType = 'text' | 'textarea' | 'date' | 'number' | 'money' | 'select' | 'checkbox' | 'list' | 'parties'
export type FieldDef = {
  name: string
  label: string
  type: FieldType
  required?: boolean
  default?: unknown
  help?: string
  options?: string[]
  min_items?: number
  max_items?: number
}
export type TemplateDef = {
  id: string
  title: string
  description: string
  sections: { title: string; fields: FieldDef[] }[]
  party_fields: FieldDef[]
  sample: Record<string, unknown>
}
export type Block = { kind: string; text: string; label: string | null }
export type Draft = { template: string; title: string; blocks: Block[]; word_count: number; html: string }

export const draftsApi = {
  templates: () => request<TemplateDef[]>('/api/drafts/templates'),
  render: (template: string, data: Record<string, unknown>) => post<Draft>('/api/drafts/render', { template, data }),
  export: (template: string, data: Record<string, unknown>, fmt: 'docx' | 'pdf') =>
    post<Blob>(`/api/drafts/export/${fmt}`, { template, data }),
}

/** Trigger a browser download for a Blob. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
