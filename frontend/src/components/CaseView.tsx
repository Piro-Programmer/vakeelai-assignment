import { useState, type ReactNode } from 'react'
import { apiUrl, casesApi, type CaseData, type Hearing, type Order, type Party } from '../api'
import { DataTable, KeyValueGrid, Section, Spinner, humanize } from './ui'

/**
 * Renders everything the scraper returns for one case.
 * Known sections get purpose-built layouts. Anything else (subordinate court,
 * IA status, or sections the portal adds later) falls back to generic
 * tables, so no data is silently hidden.
 */
export default function CaseView({ data }: { data: CaseData }) {
  const [showJson, setShowJson] = useState(false)
  const s = data.summary

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(blob),
      download: `${s.cnr ?? 'case'}.json`,
    })
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const extras: [string, unknown][] = [
    ['subordinate_court', data.subordinate_court],
    ['ia_status', data.ia_status],
    ['linked_cases', data.linked_cases],
    ...Object.entries(data.other_sections ?? {}),
  ].filter(([, v]) => v != null && !(Array.isArray(v) && v.length === 0)) as [string, unknown][]

  return (
    <div className="space-y-5">
      {/* ---------------------------------------------------------- summary */}
      <div className="card overflow-hidden">
        <div className="bg-gradient-to-r from-ink to-brand px-6 py-5 text-white">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-widest text-blue-200">{s.court}</div>
              <h2 className="mt-1 font-serif text-2xl font-bold">{s.title}</h2>
              <div className="mt-1 text-sm text-blue-100">
                {s.case_type} · Reg. No. {s.registration_number ?? '—'} · CNR <span className="font-mono">{s.cnr}</span>
              </div>
            </div>
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${
                s.is_disposed ? 'bg-emerald-400/20 text-emerald-100' : 'bg-amber-400/20 text-amber-100'
              }`}
            >
              {s.is_disposed ? 'Disposed' : 'Pending'}
            </span>
          </div>
        </div>
        <div className="grid gap-4 px-6 py-4 sm:grid-cols-3">
          <Stat label={s.is_disposed ? 'Decision date' : 'Next hearing'} value={s.is_disposed ? s.decision_date : s.next_hearing_date} />
          <Stat label={s.is_disposed ? 'Status' : 'Stage'} value={s.stage} />
          <Stat label="Hearings / Orders" value={`${data.hearing_history.length} / ${data.interim_orders.length + data.final_orders.length}`} />
        </div>
        <div className="flex flex-wrap gap-2 border-t border-slate-100 px-6 py-3">
          <button className="btn btn-ghost" onClick={() => setShowJson((v) => !v)}>
            {showJson ? 'Hide JSON' : 'View JSON'}
          </button>
          <button className="btn btn-ghost" onClick={downloadJson}>
            Download JSON
          </button>
          <span className="ml-auto self-center text-xs text-slate-400">
            Fetched {new Date(data.source.fetched_at).toLocaleString()}
          </span>
        </div>
        {showJson && (
          <pre className="max-h-[500px] overflow-auto border-t border-slate-100 bg-slate-900 p-4 text-xs text-emerald-200">
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </div>

      {/* ---------------------------------------------------------- details */}
      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="Case details · Filing & registration">
          <KeyValueGrid data={data.case_details} />
        </Section>
        <Section title="Case status">
          <KeyValueGrid data={data.case_status} />
        </Section>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <Section title="Petitioner(s) & advocate(s)">
          <PartyList parties={data.petitioners} />
        </Section>
        <Section title="Respondent(s) & advocate(s)">
          <PartyList parties={data.respondents} />
        </Section>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <Section title="Acts & sections">
          <DataTable rows={data.acts} />
        </Section>
        {data.fir_details && (
          <Section title="FIR details">
            <KeyValueGrid data={data.fir_details} />
          </Section>
        )}
      </div>

      {(data.final_orders.length > 0 || data.interim_orders.length > 0) && (
        <div className="grid gap-5 lg:grid-cols-2">
          {data.final_orders.length > 0 && (
            <Section title="Final orders / judgments">
              <OrderList orders={data.final_orders} />
            </Section>
          )}
          {data.interim_orders.length > 0 && (
            <Section title="Interim orders">
              <OrderList orders={data.interim_orders} />
            </Section>
          )}
        </div>
      )}

      <Section title={`Hearing history (${data.hearing_history.length})`}>
        <HearingTable rows={data.hearing_history} />
      </Section>

      {!!data.processes?.length && (
        <Section title="Processes">
          <DataTable rows={data.processes} />
        </Section>
      )}
      {!!data.case_transfers?.length && (
        <Section title="Case transfers within establishment">
          <DataTable rows={data.case_transfers} />
        </Section>
      )}
      {extras.map(([k, v]) => (
        <Section key={k} title={humanize(k)}>
          {Array.isArray(v) ? (
            <DataTable rows={v as Record<string, unknown>[]} />
          ) : typeof v === 'object' ? (
            <KeyValueGrid data={v as Record<string, unknown>} />
          ) : (
            <p className="text-sm">{String(v)}</p>
          )}
        </Section>
      ))}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-0.5 font-semibold text-ink">{value ?? '—'}</div>
    </div>
  )
}

function PartyList({ parties }: { parties: Party[] }) {
  if (!parties.length) return <p className="text-sm text-slate-400">Not available</p>
  return (
    <ol className="space-y-3">
      {parties.map((p, i) => (
        <li key={i} className="flex gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-soft text-xs font-bold text-brand">
            {i + 1}
          </span>
          <div>
            <div className="font-semibold text-slate-800">{p.name}</div>
            {p.details && <div className="text-sm text-slate-500">{p.details}</div>}
            {p.advocates.length > 0 ? (
              <div className="text-sm text-slate-600">Advocate: {p.advocates.join(', ')}</div>
            ) : (
              <div className="text-xs text-slate-400">No advocate listed</div>
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}

function OrderList({ orders }: { orders: Order[] }) {
  return (
    <ul className="divide-y divide-slate-100">
      {orders.map((o, i) => (
        <li key={i} className="flex items-center justify-between gap-3 py-2 text-sm">
          <div>
            <span className="mr-2 font-mono text-slate-400">#{o.order_number}</span>
            <span className="font-medium">{o.order_details}</span>
            <div className="text-xs text-slate-500">{o.order_date}</div>
          </div>
          {o.pdf_url ? (
            // Opened via our backend proxy: portal PDF links are session-bound.
            <a href={apiUrl(o.pdf_url)} target="_blank" rel="noreferrer" className="btn btn-ghost shrink-0 !px-3 !py-1">
              📄 PDF
            </a>
          ) : (
            <span className="text-xs text-slate-400">No document</span>
          )}
        </li>
      ))}
    </ul>
  )
}

function HearingTable({ rows }: { rows: Hearing[] }) {
  // Business details are fetched on demand: one portal round trip per row,
  // so prefetching dozens of hearings would be slow and impolite to the portal.
  const [open, setOpen] = useState<Record<number, Record<string, string | null> | 'loading' | string>>({})

  const toggle = async (i: number, url?: string) => {
    if (!url) return
    if (open[i]) {
      setOpen((o) => {
        const next = { ...o }
        delete next[i]
        return next
      })
      return
    }
    setOpen((o) => ({ ...o, [i]: 'loading' }))
    try {
      const res = await casesApi.business(url)
      setOpen((o) => ({ ...o, [i]: res.business }))
    } catch (e) {
      setOpen((o) => ({ ...o, [i]: (e as Error).message }))
    }
  }

  if (!rows.length) return <p className="text-sm text-slate-400">No hearings recorded</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
            <th className="px-3 py-2">Business on</th>
            <th className="px-3 py-2">Next hearing</th>
            <th className="px-3 py-2">Purpose</th>
            <th className="px-3 py-2">Judge</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {rows.map((h, i) => {
            const state = open[i]
            return (
              <FragmentRow key={i}>
                <tr className="border-b border-slate-100">
                  <td className="px-3 py-2 font-medium">{h.business_on_date ?? '—'}</td>
                  <td className="px-3 py-2">{h.hearing_date ?? '—'}</td>
                  <td className="px-3 py-2">{h.purpose_of_hearing ?? '—'}</td>
                  <td className="px-3 py-2 text-slate-500">{h.judge ?? '—'}</td>
                  <td className="px-3 py-2 text-right">
                    {h.business_url && (
                      <button className="text-xs font-semibold text-brand hover:underline" onClick={() => toggle(i, h.business_url)}>
                        {state ? 'Hide' : 'Details'}
                      </button>
                    )}
                  </td>
                </tr>
                {state && (
                  <tr className="bg-slate-50">
                    <td colSpan={5} className="px-5 py-3">
                      {state === 'loading' ? (
                        <span className="flex items-center gap-2 text-sm text-slate-500">
                          <Spinner /> Fetching daily status…
                        </span>
                      ) : typeof state === 'string' ? (
                        <span className="text-sm text-red-600">{state}</span>
                      ) : (
                        <KeyValueGrid data={state} />
                      )}
                    </td>
                  </tr>
                )}
              </FragmentRow>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// Lets a pair of <tr>s share one key inside .map().
const FragmentRow = ({ children }: { children: ReactNode }) => <>{children}</>
