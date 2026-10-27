import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, draftsApi, saveBlob, type Draft, type TemplateDef } from '../api'
import { Field } from '../components/DraftFields'
import { ErrorBanner, Spinner } from '../components/ui'

/**
 * Draft generator: pick a template, fill a schema-driven form, and watch a
 * live A4-style preview. All drafting logic lives in the Python backend (no
 * LLM). This page only collects input and shows the server's output, so the
 * preview, DOCX and PDF are guaranteed to match.
 */
export default function DraftGenerator() {
  const [templates, setTemplates] = useState<TemplateDef[]>([])
  const [active, setActive] = useState<string>('')
  // Form state is kept per template, so switching templates doesn't lose work.
  const [forms, setForms] = useState<Record<string, Record<string, unknown>>>({})
  const [draft, setDraft] = useState<Draft | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [rendering, setRendering] = useState(false)
  const [exporting, setExporting] = useState<'' | 'docx' | 'pdf'>('')
  const seq = useRef(0)

  useEffect(() => {
    draftsApi
      .templates()
      .then((t) => {
        setTemplates(t)
        setForms(Object.fromEntries(t.map((x) => [x.id, structuredClone(x.sample)])))
        setActive(t[0]?.id ?? '')
      })
      .catch((e) => setError(e.message))
  }, [])

  const tpl = useMemo(() => templates.find((t) => t.id === active), [templates, active])
  // Memoised so a missing entry doesn't yield a new {} every render, which
  // would retrigger the preview effect below in a loop.
  const data = useMemo(() => forms[active] ?? {}, [forms, active])

  // Live preview, debounced: typing shouldn't send a request per keystroke.
  // The sequence number drops responses that arrive out of order, so a slow
  // older render can't overwrite a newer one.
  useEffect(() => {
    if (!active) return
    const id = ++seq.current
    const t = setTimeout(async () => {
      setRendering(true)
      try {
        const d = await draftsApi.render(active, data)
        if (id !== seq.current) return
        setDraft(d)
        setFieldErrors({})
        setError(null)
      } catch (e) {
        if (id !== seq.current) return
        const err = e as ApiError
        setFieldErrors(err.fieldErrors ?? {})
        setError(err.fieldErrors ? null : err.message)
      } finally {
        if (id === seq.current) setRendering(false)
      }
    }, 450)
    return () => clearTimeout(t)
  }, [active, data])

  const update = (name: string, value: unknown) => setForms((f) => ({ ...f, [active]: { ...f[active], [name]: value } }))

  const exportAs = async (fmt: 'docx' | 'pdf') => {
    setExporting(fmt)
    try {
      const blob = await draftsApi.export(active, data, fmt)
      saveBlob(blob, `${active}.${fmt}`)
    } catch (e) {
      const err = e as ApiError
      setFieldErrors(err.fieldErrors ?? {})
      setError(err.message)
    } finally {
      setExporting('')
    }
  }

  const errorCount = Object.keys(fieldErrors).length

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-ink">Legal Draft Generator</h1>
        <p className="text-sm text-slate-500">
          Rule-based drafting in pure Python (no AI). The sample data is pre-filled, so edit it and download as Word or PDF.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {templates.map((t) => (
          <button
            key={t.id}
            onClick={() => setActive(t.id)}
            className={`card p-4 text-left transition hover:border-brand ${active === t.id ? 'border-brand ring-2 ring-brand/20' : ''}`}
          >
            <div className="font-semibold text-ink">{t.title}</div>
            <div className="mt-1 text-xs text-slate-500">{t.description}</div>
          </button>
        ))}
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {tpl && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
          {/* ---------------------------------------------------------- form */}
          <div className="space-y-4">
            {tpl.sections.map((s) => (
              <details key={s.title} open className="card group">
                <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-3 text-sm font-bold uppercase tracking-wide text-slate-600">
                  {s.title}
                  <span className="text-slate-400 transition group-open:rotate-180">▾</span>
                </summary>
                <div className="space-y-4 border-t border-slate-100 px-5 py-4">
                  {s.fields.map((f) => (
                    <Field key={f.name} def={f} value={data[f.name]} onChange={(v) => update(f.name, v)} errors={fieldErrors} partyFields={tpl.party_fields} />
                  ))}
                </div>
              </details>
            ))}
            <div className="flex gap-2">
              <button className="btn btn-ghost" onClick={() => setForms((f) => ({ ...f, [active]: structuredClone(tpl.sample) }))}>
                Reset to sample
              </button>
              <button className="btn btn-ghost" onClick={() => setForms((f) => ({ ...f, [active]: {} }))}>
                Clear form
              </button>
            </div>
          </div>

          {/* ------------------------------------------------------- preview */}
          <div className="lg:sticky lg:top-4 lg:self-start">
            <div className="card overflow-hidden">
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 bg-slate-50 px-4 py-2">
                <span className="text-sm font-bold text-slate-600">Preview</span>
                {rendering && <Spinner className="h-3 w-3 text-slate-400" />}
                {errorCount > 0 && (
                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">
                    {errorCount} field{errorCount > 1 ? 's' : ''} need attention
                  </span>
                )}
                {draft && !errorCount && <span className="text-xs text-slate-400">{draft.word_count} words</span>}
                <div className="ml-auto flex gap-2">
                  <button className="btn btn-primary !py-1.5" disabled={!!exporting || errorCount > 0} onClick={() => exportAs('docx')}>
                    {exporting === 'docx' ? <Spinner /> : '⬇'} Word
                  </button>
                  <button className="btn btn-ghost !py-1.5" disabled={!!exporting || errorCount > 0} onClick={() => exportAs('pdf')}>
                    {exporting === 'pdf' ? <Spinner /> : '⬇'} PDF
                  </button>
                </div>
              </div>
              <div className={`max-h-[80vh] overflow-auto bg-slate-200 p-4 transition ${errorCount ? 'opacity-50' : ''}`}>
                {draft ? (
                  // The backend escapes all user text before building this HTML (exporters._block_html).
                  <article className="doc mx-auto max-w-[680px] px-10 py-12 shadow-lg" dangerouslySetInnerHTML={{ __html: draft.html }} />
                ) : (
                  <div className="py-20 text-center text-sm text-slate-500">
                    <Spinner /> Generating preview…
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
