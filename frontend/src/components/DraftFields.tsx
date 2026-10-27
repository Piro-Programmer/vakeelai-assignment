import type { FieldDef } from '../api'

/**
 * Schema-driven inputs. The backend's field schema decides what is rendered,
 * so a new template needs no frontend changes.
 */

type Errors = Record<string, string>
type Value = unknown

export function Field({
  def, value, onChange, errors, partyFields,
}: {
  def: FieldDef
  value: Value
  onChange: (v: Value) => void
  errors: Errors
  partyFields: FieldDef[]
}) {
  const err = errors[def.name]
  const label = (
    <label className="label" htmlFor={def.name}>
      {def.label}
      {def.required && <span className="text-red-500"> *</span>}
    </label>
  )
  const help = def.help && <p className="mt-1 text-xs text-slate-400">{def.help}</p>
  const errEl = err && <p className="mt-1 text-xs font-medium text-red-600">{err}</p>
  const cls = `input ${err ? '!border-red-400' : ''}`

  switch (def.type) {
    case 'parties':
      return (
        <div>
          {label}
          <PartiesEditor name={def.name} value={(value as Record<string, string>[]) ?? []} onChange={onChange} fields={partyFields} errors={errors} max={def.max_items} />
          {errEl}
        </div>
      )
    case 'list':
      return (
        <div>
          {label}
          <ListEditor value={(value as string[]) ?? []} onChange={onChange} />
          {help}
          {errEl}
        </div>
      )
    case 'checkbox':
      return (
        <label className="flex cursor-pointer items-start gap-2 text-sm text-slate-700">
          <input type="checkbox" className="mt-0.5 h-4 w-4 accent-brand" checked={!!value} onChange={(e) => onChange(e.target.checked)} />
          <span>{def.label}</span>
        </label>
      )
    case 'select':
      return (
        <div>
          {label}
          <select id={def.name} className={cls} value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)}>
            <option value="">—</option>
            {def.options?.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
          {errEl}
        </div>
      )
    case 'textarea':
      return (
        <div>
          {label}
          <textarea id={def.name} className={cls} rows={3} value={(value as string) ?? ''} onChange={(e) => onChange(e.target.value)} />
          {help}
          {errEl}
        </div>
      )
    default: {
      const type = def.type === 'date' ? 'date' : def.type === 'number' || def.type === 'money' ? 'number' : 'text'
      return (
        <div>
          {label}
          <div className="relative">
            {def.type === 'money' && <span className="pointer-events-none absolute left-3 top-2 text-sm text-slate-400">₹</span>}
            <input
              id={def.name}
              type={type}
              min={type === 'number' ? 0 : undefined}
              className={`${cls} ${def.type === 'money' ? 'pl-7' : ''}`}
              value={(value as string | number | undefined) ?? ''}
              onChange={(e) => onChange(e.target.value)}
            />
          </div>
          {help}
          {errEl}
        </div>
      )
    }
  }
}

/** Repeatable paragraphs (facts, prayers, grounds). */
function ListEditor({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const items = value.length ? value : ['']
  const set = (i: number, v: string) => onChange(items.map((x, j) => (j === i ? v : x)))
  const move = (i: number, d: number) => {
    const j = i + d
    if (j < 0 || j >= items.length) return
    const next = [...items]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(next)
  }
  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div key={i} className="flex gap-2">
          <span className="mt-2 w-6 shrink-0 text-right text-xs font-bold text-slate-400">{i + 1}.</span>
          <textarea className="input min-h-[60px]" rows={2} value={item} onChange={(e) => set(i, e.target.value)} />
          <div className="flex shrink-0 flex-col gap-0.5 text-slate-400">
            <button type="button" title="Move up" className="hover:text-slate-700" onClick={() => move(i, -1)}>▲</button>
            <button type="button" title="Move down" className="hover:text-slate-700" onClick={() => move(i, 1)}>▼</button>
            <button type="button" title="Remove" className="hover:text-red-600" onClick={() => onChange(items.filter((_, j) => j !== i))}>✕</button>
          </div>
        </div>
      ))}
      <button type="button" className="ml-8 text-xs font-semibold text-brand hover:underline" onClick={() => onChange([...items, ''])}>
        + Add paragraph
      </button>
    </div>
  )
}

/** Repeatable party cards (plaintiffs, accused, deponent...). */
function PartiesEditor({
  name, value, onChange, fields, errors, max,
}: {
  name: string
  value: Record<string, string>[]
  onChange: (v: Record<string, string>[]) => void
  fields: FieldDef[]
  errors: Errors
  max?: number
}) {
  const parties = value.length ? value : [{}]
  const set = (i: number, k: string, v: string) => onChange(parties.map((p, j) => (j === i ? { ...p, [k]: v } : p)))
  return (
    <div className="space-y-3">
      {parties.map((p, i) => (
        <div key={i} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500">Party {i + 1}</span>
            {parties.length > 1 && (
              <button type="button" className="text-xs text-red-500 hover:underline" onClick={() => onChange(parties.filter((_, j) => j !== i))}>
                Remove
              </button>
            )}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {fields.map((f) => {
              const err = errors[`${name}.${i}.${f.name}`]
              const common = {
                className: `input ${err ? '!border-red-400' : ''}`,
                value: p[f.name] ?? '',
                placeholder: f.label + (f.required ? ' *' : ''),
                title: f.help ?? f.label,
              }
              return (
                <div key={f.name} className={f.type === 'textarea' || f.name === 'description' ? 'sm:col-span-2' : ''}>
                  {f.type === 'textarea' ? (
                    <textarea {...common} rows={2} onChange={(e) => set(i, f.name, e.target.value)} />
                  ) : (
                    <input {...common} type={f.type === 'number' ? 'number' : 'text'} onChange={(e) => set(i, f.name, e.target.value)} />
                  )}
                  {err && <p className="mt-0.5 text-xs text-red-600">{err}</p>}
                </div>
              )
            })}
          </div>
        </div>
      ))}
      {(!max || parties.length < max) && (
        <button type="button" className="text-xs font-semibold text-brand hover:underline" onClick={() => onChange([...parties, {}])}>
          + Add party
        </button>
      )}
    </div>
  )
}
