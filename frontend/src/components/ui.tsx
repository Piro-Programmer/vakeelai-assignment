import type { ReactNode } from 'react'

export function Spinner({ className = 'h-4 w-4' }: { className?: string }) {
  return <span className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${className}`} />
}

export function ErrorBanner({ message, onClose }: { message: string; onClose?: () => void }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      <span>⚠️ {message}</span>
      {onClose && (
        <button onClick={onClose} className="text-red-500 hover:text-red-800" aria-label="Dismiss">
          ✕
        </button>
      )}
    </div>
  )
}

export function Section({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-5 py-3">
        <h3 className="text-sm font-bold uppercase tracking-wide text-slate-600">{title}</h3>
        {right}
      </div>
      <div className="p-5">{children}</div>
    </section>
  )
}

/** snake_case API keys -> readable labels ("court_number_and_judge" -> "Court number and judge"). */
export const humanize = (key: string) => {
  const s = key.replace(/_/g, ' ').replace(/\bcnr\b/i, 'CNR').replace(/\bfir\b/i, 'FIR').replace(/\bia\b/i, 'IA')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function KeyValueGrid({ data }: { data: Record<string, unknown> | null | undefined }) {
  const entries = Object.entries(data ?? {}).filter(([, v]) => v !== null && v !== '')
  if (!entries.length) return <p className="text-sm text-slate-400">Not available</p>
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
      {entries.map(([k, v]) => (
        <div key={k}>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{humanize(k)}</dt>
          <dd className="mt-0.5 text-sm font-medium text-slate-800">{String(v)}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Generic table for row lists whose columns we don't model explicitly. */
export function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <p className="text-sm text-slate-400">No records</p>
  const cols = Object.keys(rows[0]).filter((c) => !c.startsWith('_'))
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
            {cols.map((c) => (
              <th key={c} className="px-3 py-2 font-semibold">
                {humanize(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-slate-100 last:border-0">
              {cols.map((c) => (
                <td key={c} className="px-3 py-2 align-top">
                  {r[c] == null ? '—' : String(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
