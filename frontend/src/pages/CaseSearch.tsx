import { useEffect, useRef, useState } from 'react'
import {
  casesApi,
  type CaptchaRequired,
  type CaseData,
  type ComplexOption,
  type Match,
  type Option,
  type SearchResult,
} from '../api'
import CaptchaDialog from '../components/CaptchaDialog'
import CaseView from '../components/CaseView'
import { ErrorBanner, Spinner } from '../components/ui'

/**
 * The assignment's example search. The cascade below auto-selects these values
 * on first load, so a reviewer can just press "Search". As soon as the user
 * touches any dropdown, auto-selection stops.
 */
const EXAMPLE = { state: '26', district: '10', complexCode: '1260011', est: '1', caseTypePrefix: 'CS (COMM)', number: '233', year: '2024' }
const EXAMPLE_CNR = 'DLND020000602007'

type Mode = 'cnr' | 'case'

export default function CaseSearch() {
  const [mode, setMode] = useState<Mode>('cnr')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [captcha, setCaptcha] = useState<CaptchaRequired | null>(null)
  const [matches, setMatches] = useState<Match[] | null>(null)
  const [caseData, setCaseData] = useState<CaseData | null>(null)
  const [solvedBy, setSolvedBy] = useState<string | null>(null)

  /** One handler for every search response shape (case / matches / captcha). */
  const handle = async (res: SearchResult) => {
    if (res.status === 'captcha_required') {
      setCaptcha(res)
      return
    }
    setCaptcha(null)
    setSolvedBy(res.captcha?.mode === 'auto' ? `Captcha auto-solved by OCR in ${res.captcha.attempts} attempt(s)` : 'Captcha solved manually')
    if (res.type === 'case') {
      setCaseData(res.case)
    } else {
      setMatches(res.matches)
      // A single match is the common case: open it straight away to save a click.
      // It is awaited here (not through openMatch/run), so the spinner stays on
      // until the details arrive.
      if (res.matches.length === 1) setCaseData((await casesApi.detail(res.matches[0].detail_ref)).case)
    }
  }

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const reset = () => {
    setMatches(null)
    setCaseData(null)
    setSolvedBy(null)
  }

  const openMatch = (m: Match) =>
    run(async () => {
      const res = await casesApi.detail(m.detail_ref)
      setCaseData(res.case)
    })

  return (
    <div className="space-y-6">
      <div className="card p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-ink">District Court Case Status</h1>
            <p className="text-sm text-slate-500">
              Live lookup on the eCourts portal. The captcha is solved automatically, with manual entry as a fallback.
            </p>
          </div>
          <div className="inline-flex rounded-xl bg-slate-100 p-1">
            {(['cnr', 'case'] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => {
                  setMode(m)
                  setError(null)
                }}
                className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition ${
                  mode === m ? 'bg-white text-brand shadow' : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                {m === 'cnr' ? 'CNR Number' : 'Case Number'}
              </button>
            ))}
          </div>
        </div>

        {mode === 'cnr' ? (
          <CnrForm
            busy={busy}
            onSearch={(cnr) =>
              run(async () => {
                reset()
                await handle(await casesApi.searchCnr(cnr))
              })
            }
          />
        ) : (
          <CaseNumberForm
            busy={busy}
            onError={setError}
            onSearch={(q) =>
              run(async () => {
                reset()
                await handle(await casesApi.searchCaseNumber(q))
              })
            }
          />
        )}

        {busy && (
          <div className="mt-4 flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Talking to eCourts (session → captcha → search). This usually takes 5–20 seconds…
          </div>
        )}
        {solvedBy && !busy && <div className="mt-3 text-xs text-emerald-700">✓ {solvedBy}</div>}
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {matches && (matches.length > 1 || !caseData) && (
        <div className="card p-5">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-600">{matches.length} matching cases</h2>
          <MatchTable matches={matches} onOpen={openMatch} busy={busy} />
        </div>
      )}

      {caseData && <CaseView data={caseData} />}

      {captcha && (
        <CaptchaDialog
          challenge={captcha}
          busy={busy}
          onCancel={() => setCaptcha(null)}
          onSubmit={(code) => run(async () => handle(await casesApi.submitCaptcha(captcha.search_id, code)))}
        />
      )}
    </div>
  )
}

// ------------------------------------------------------------------ CNR form
function CnrForm({ busy, onSearch }: { busy: boolean; onSearch: (cnr: string) => void }) {
  const [cnr, setCnr] = useState(EXAMPLE_CNR)
  // Same normalisation as the backend, so the counter matches what gets validated.
  const clean = cnr.replace(/[\s-]/g, '').toUpperCase()
  const valid = /^[A-Z0-9]{16}$/.test(clean)
  return (
    <form
      className="flex flex-col gap-3 sm:flex-row sm:items-end"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) onSearch(clean)
      }}
    >
      <div className="flex-1">
        <label className="label" htmlFor="cnr">
          CNR number <span className="normal-case text-slate-400">({clean.length}/16)</span>
        </label>
        <input
          id="cnr"
          className="input font-mono uppercase tracking-wider"
          value={cnr}
          onChange={(e) => setCnr(e.target.value)}
          placeholder="e.g. DLND020000602007"
          maxLength={24}
        />
      </div>
      <button className="btn btn-primary" disabled={busy || !valid}>
        {busy ? <Spinner /> : '🔍'} Search
      </button>
    </form>
  )
}

// ---------------------------------------------------------- case number form
function CaseNumberForm({
  busy,
  onSearch,
  onError,
}: {
  busy: boolean
  onSearch: (q: Parameters<typeof casesApi.searchCaseNumber>[0]) => void
  onError: (m: string) => void
}) {
  const [states, setStates] = useState<Option[]>([])
  const [districts, setDistricts] = useState<Option[]>([])
  const [complexes, setComplexes] = useState<ComplexOption[]>([])
  const [ests, setEsts] = useState<Option[]>([])
  const [types, setTypes] = useState<Option[]>([])
  const [sel, setSel] = useState({ state: '', district: '', complex: '', est: '', type: '' })
  const [number, setNumber] = useState(EXAMPLE.number)
  const [year, setYear] = useState(EXAMPLE.year)
  const [loading, setLoading] = useState<string | null>(null)
  const auto = useRef(true) // pre-fill the example until the user takes over

  const complex = complexes.find((c) => c.value === sel.complex)
  const needsEst = !!complex?.requires_establishment

  // Each level loads when its parent changes and clears everything below it.
  // `pick` chooses the example value while auto-fill is on.
  const load = async <T extends Option>(what: string, fn: () => Promise<T[]>, set: (o: T[]) => void, pick?: (o: T[]) => string | undefined, key?: keyof typeof sel) => {
    setLoading(what)
    try {
      const opts = await fn()
      set(opts)
      if (auto.current && pick && key) {
        const v = pick(opts)
        if (v) setSel((s) => ({ ...s, [key]: v }))
      }
    } catch (e) {
      onError(`Could not load ${what}: ${(e as Error).message}`)
    } finally {
      setLoading(null)
    }
  }

  /* eslint-disable react-hooks/exhaustive-deps --
     Each cascade level must re-run ONLY when its direct parent selection changes.
     Listing every value read inside (load, sibling selections) would refetch
     lists on unrelated changes and wipe the user's choices below. */
  useEffect(() => {
    void load('states', casesApi.states, setStates, (o) => o.find((x) => x.value === EXAMPLE.state)?.value, 'state')
  }, [])

  useEffect(() => {
    setDistricts([]); setComplexes([]); setEsts([]); setTypes([])
    if (sel.state) void load('districts', () => casesApi.districts(sel.state), setDistricts, (o) => o.find((x) => x.value === EXAMPLE.district)?.value, 'district')
  }, [sel.state])

  useEffect(() => {
    setComplexes([]); setEsts([]); setTypes([])
    if (sel.district) void load('court complexes', () => casesApi.complexes(sel.state, sel.district), setComplexes, (o) => o.find((x) => x.code === EXAMPLE.complexCode)?.value, 'complex')
  }, [sel.district])

  useEffect(() => {
    setEsts([]); setTypes([])
    if (!sel.complex) return
    if (needsEst) void load('establishments', () => casesApi.establishments(sel.state, sel.district, sel.complex), setEsts, (o) => o.find((x) => x.value === EXAMPLE.est)?.value, 'est')
  }, [sel.complex])

  useEffect(() => {
    setTypes([])
    if (!sel.complex || (needsEst && !sel.est)) return
    void load('case types', () => casesApi.caseTypes(sel.state, sel.district, sel.complex, needsEst ? sel.est : ''), setTypes, (o) => {
      const v = o.find((x) => x.label.startsWith(EXAMPLE.caseTypePrefix))?.value
      auto.current = false // the example chain ends here
      return v
    }, 'type')
  }, [sel.complex, sel.est])
  /* eslint-enable react-hooks/exhaustive-deps */

  const change = (key: keyof typeof sel, value: string) => {
    auto.current = false
    const order: (keyof typeof sel)[] = ['state', 'district', 'complex', 'est', 'type']
    const reset = Object.fromEntries(order.slice(order.indexOf(key) + 1).map((k) => [k, '']))
    setSel((s) => ({ ...s, ...reset, [key]: value }))
  }

  const ready = sel.state && sel.district && sel.complex && (!needsEst || sel.est) && sel.type && /^\d+$/.test(number) && /^\d{4}$/.test(year)

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (ready)
          onSearch({
            state_code: sel.state, dist_code: sel.district, court_complex: sel.complex,
            est_code: needsEst ? sel.est : null, case_type: sel.type, case_number: number, year,
          })
      }}
      className="space-y-4"
    >
      <div className="grid gap-3 rounded-xl bg-ink p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Select dark label="State" value={sel.state} options={states} onChange={(v) => change('state', v)} />
        <Select dark label="District" value={sel.district} options={districts} onChange={(v) => change('district', v)} />
        <Select dark label="Court complex" value={sel.complex} options={complexes} onChange={(v) => change('complex', v)} />
        <Select
          dark
          label="Establishment"
          value={sel.est}
          options={ests}
          onChange={(v) => change('est', v)}
          disabled={!needsEst}
          placeholder={sel.complex && !needsEst ? 'Not required for this complex' : undefined}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end">
        <Select label="Case type" value={sel.type} options={types} onChange={(v) => change('type', v)} />
        <div>
          <label className="label">Case number</label>
          <input className="input" value={number} inputMode="numeric" onChange={(e) => setNumber(e.target.value.replace(/\D/g, ''))} maxLength={7} />
        </div>
        <div>
          <label className="label">Year</label>
          <input className="input" value={year} inputMode="numeric" onChange={(e) => setYear(e.target.value.replace(/\D/g, ''))} maxLength={4} />
        </div>
        <button className="btn btn-primary" disabled={busy || !ready}>
          {busy ? <Spinner /> : '🔍'} Search
        </button>
      </div>
      {loading && (
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Spinner className="h-3 w-3" /> Loading {loading}…
        </div>
      )}
    </form>
  )
}

function Select({
  label, value, options, onChange, disabled, placeholder, dark,
}: {
  label: string
  value: string
  options: Option[]
  onChange: (v: string) => void
  disabled?: boolean
  placeholder?: string
  dark?: boolean
}) {
  return (
    <div>
      <label className={`label ${dark ? '!text-blue-200' : ''}`}>{label}</label>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled || !options.length}>
        <option value="">{placeholder ?? (options.length ? `Select ${label.toLowerCase()}` : '—')}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  )
}

function MatchTable({ matches, onOpen, busy }: { matches: Match[]; onOpen: (m: Match) => void; busy: boolean }) {
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b text-xs uppercase tracking-wide text-slate-500">
          <th className="px-3 py-2">Case</th>
          <th className="px-3 py-2">Parties</th>
          <th className="px-3 py-2">Establishment</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {matches.map((m) => (
          <tr key={m.detail_ref} className="border-b border-slate-100">
            <td className="px-3 py-2 font-medium">{m.case_number}</td>
            <td className="px-3 py-2">{m.title}</td>
            <td className="px-3 py-2 text-slate-500">{m.establishment}</td>
            <td className="px-3 py-2 text-right">
              <button className="btn btn-ghost !py-1" disabled={busy} onClick={() => onOpen(m)}>
                View
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
