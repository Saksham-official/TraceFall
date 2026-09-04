/** Shared primitives. Kept in one file on purpose — none of them is worth a module. */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import { useId } from 'react'

import { ApiError } from '../api/client'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
}

const BUTTON_VARIANTS = {
  primary: 'bg-[var(--accent)] text-[var(--accent-contrast)] hover:opacity-90',
  secondary:
    'bg-[var(--surface)] text-[var(--text)] border border-[var(--border)] hover:bg-[var(--surface-2)]',
  ghost: 'text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]',
  danger: 'bg-[var(--surface)] text-[var(--danger)] border border-[var(--danger)]',
}

export function Button({ variant = 'primary', className = '', ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded px-3 py-1.5 font-medium disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_VARIANTS[variant]} ${className}`}
    />
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 ${className}`}
    >
      {children}
    </section>
  )
}

export function Field({
  label,
  hint,
  error,
  required,
  children,
}: {
  label: string
  hint?: ReactNode
  error?: string | null
  required?: boolean
  children: (props: { id: string; 'aria-describedby'?: string; 'aria-invalid'?: true }) => ReactNode
}) {
  const id = useId()
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ')

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-medium">
        {label}
        {required && (
          <span className="ml-0.5 text-[var(--danger)]" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children({
        id,
        'aria-describedby': describedBy || undefined,
        'aria-invalid': error ? true : undefined,
      })}
      {hint && (
        <p id={hintId} className="text-xs text-[var(--muted)]">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-xs font-medium text-[var(--danger)]">
          {error}
        </p>
      )}
    </div>
  )
}

const CONTROL =
  'w-full rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1.5 text-[var(--text)] aria-invalid:border-[var(--danger)]'

export function TextInput({ className = '', ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${CONTROL} ${className}`} />
}

export function TextArea(props: InputHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={CONTROL} rows={3} />
}

export function Select({ className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${CONTROL} ${className}`} />
}

/** Neutral notice. `tone` changes the icon glyph and the word, not only the colour. */
export function Banner({
  tone,
  title,
  children,
}: {
  tone: 'info' | 'warning' | 'error'
  title: string
  children?: ReactNode
}) {
  const band = { info: 'risk-LOW', warning: 'risk-MEDIUM', error: 'risk-CRITICAL' }[tone]
  const word = { info: 'Note', warning: 'Warning', error: 'Error' }[tone]
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`${band} rounded border p-3`}>
      <p className="font-semibold">
        <span className="mr-1.5 text-xs tracking-wide uppercase opacity-80">{word}</span>
        {title}
      </p>
      {children && <div className="mt-1">{children}</div>}
    </div>
  )
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="rounded-lg border border-dashed border-[var(--border)] p-8 text-center">
      <p className="font-semibold">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-prose text-[var(--muted)]">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

/** Used for tabs whose API lands in a later phase. It never fakes data. */
export function LaterPhase({ what, phase }: { what: string; phase: string }) {
  return (
    <EmptyState title={`${what} is available in a later phase`}>
      <p>
        The analysis pipeline that produces this data is built in {phase}. Nothing is shown here
        rather than showing something that is not real.
      </p>
    </EmptyState>
  )
}

export function Spinner({ label }: { label: string }) {
  return (
    <p role="status" className="p-4 text-[var(--muted)]">
      {label}
    </p>
  )
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong. Please try again.'
}

export function ErrorNotice({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <Banner tone="error" title={errorMessage(error)}>
      {error instanceof ApiError && error.body.request_id !== '-' && (
        <p className="font-mono text-xs">request {error.body.request_id}</p>
      )}
      {onRetry && (
        <Button variant="secondary" className="mt-2" onClick={onRetry}>
          Try again
        </Button>
      )}
    </Banner>
  )
}
