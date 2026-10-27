import { useEffect, useRef, useState } from 'react'
import type { CaptchaRequired } from '../api'
import { Spinner } from './ui'

/**
 * Manual-captcha fallback. Shown only when the backend's OCR gave up.
 * The image comes from the backend's parked portal session, so the answer
 * must be posted back with the same search_id.
 */
export default function CaptchaDialog({
  challenge,
  busy,
  onSubmit,
  onCancel,
}: {
  challenge: CaptchaRequired
  busy: boolean
  onSubmit: (code: string) => void
  onCancel: () => void
}) {
  const [code, setCode] = useState('')
  const input = useRef<HTMLInputElement>(null)

  // New challenge (e.g. after a wrong answer): clear the box and refocus.
  useEffect(() => {
    setCode('')
    input.current?.focus()
  }, [challenge.captcha_image])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <form
        className="card w-full max-w-sm p-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (code.trim()) onSubmit(code.trim())
        }}
      >
        <h2 className="text-lg font-bold text-ink">Captcha required</h2>
        <p className="mt-1 text-sm text-slate-600">{challenge.message}</p>
        <img
          src={challenge.captcha_image}
          alt="eCourts captcha"
          className="mx-auto my-4 h-14 rounded border border-slate-200 bg-white [image-rendering:pixelated]"
        />
        <input
          ref={input}
          className="input text-center font-mono text-lg tracking-widest"
          value={code}
          // Mirror the portal's own filter: letters and digits only.
          onChange={(e) => setCode(e.target.value.replace(/[^a-zA-Z0-9]/g, ''))}
          placeholder="Enter the characters"
          maxLength={8}
          autoComplete="off"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={busy || !code}>
            {busy && <Spinner />} Submit
          </button>
        </div>
      </form>
    </div>
  )
}
