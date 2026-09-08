/** Shared primitives. Kept in one file on purpose — none of them is worth a module. */

import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'
import { useId } from 'react'

import { ApiError } from '../api/client'
import type { RiskBand } from '../api/types'
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  InfoIcon,
  SpinnerIcon,
  XCircleIcon,
} from './icons'

// --- buttons -----------------------------------------------------------------

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  icon?: ReactNode
  /** Disables the control and shows a spinner while keeping the label readable. */
  loading?: boolean
}

const BUTTON_VARIANTS = {
  primary:
    'bg-[var(--accent)] text-[var(--accent-contrast)] shadow-sm hover:bg-[var(--accent-hover)]',
  secondary:
    'bg-[var(--surface)] text-[var(--text)] border border-[var(--border-strong)] shadow-sm hover:bg-[var(--surface-2)]',
  ghost: 'text-[var(--text-2)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]',
  danger:
    'bg-[var(--surface)] text-[var(--danger-fg)] border border-[var(--danger-border)] hover:bg-[var(--danger-bg)]',
}

const BUTTON_SIZES = {
  sm: 'h-7 px-2.5 text-[0.8125rem] gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-2',
}

export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  loading = false,
  className = '',
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`transition-ui inline-flex items-center justify-center rounded-[var(--radius-sm)] font-medium whitespace-nowrap select-none active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50 disabled:active:translate-y-0 ${BUTTON_VARIANTS[variant]} ${BUTTON_SIZES[size]} ${className}`}
    >
      {loading ? <SpinnerIcon /> : icon}
      {children}
    </button>
  )
}

/** Small square control for an icon-only action; the label is required, for the tooltip and the reader. */
export function IconButton({
  label,
  className = '',
  size = 'md',
  variant = 'ghost',
  ...props
}: Omit<ButtonProps, 'icon' | 'children'> & { label: string; children: ReactNode }) {
  return (
    <button
      {...props}
      type={props.type ?? 'button'}
      title={label}
      aria-label={label}
      className={`transition-ui inline-flex items-center justify-center rounded-[var(--radius-sm)] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_VARIANTS[variant]} ${size === 'sm' ? 'h-7 w-7' : 'h-9 w-9'} ${className}`}
    />
  )
}

// --- surfaces ----------------------------------------------------------------

export function Card({
  children,
  className = '',
  title,
  description,
  actions,
  padding = 'md',
  as: Tag = 'section',
}: {
  children: ReactNode
  className?: string
  title?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  padding?: 'none' | 'sm' | 'md'
  as?: 'section' | 'div' | 'article'
}) {
  const pad = { none: '', sm: 'p-3', md: 'p-4' }[padding]
  return (
    <Tag
      className={`rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-sm)] ${title ? '' : pad} ${className}`}
    >
      {title && (
        <header
          className={`flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border)] px-4 py-3`}
        >
          <div className="min-w-0">
            <h2 className="text-h3">{title}</h2>
            {description && <p className="text-meta mt-0.5">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      {title ? <div className={pad}>{children}</div> : children}
    </Tag>
  )
}

/** A headline number with its label. Density without decoration. */
export function StatTile({
  label,
  value,
  hint,
  tone = 'neutral',
  icon,
  className = '',
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info'
  icon?: ReactNode
  className?: string
}) {
  const valueTone = {
    neutral: 'text-[var(--text)]',
    accent: 'text-[var(--accent)]',
    success: 'text-[var(--success-fg)]',
    warning: 'text-[var(--warning-fg)]',
    danger: 'text-[var(--danger-fg)]',
    info: 'text-[var(--info-fg)]',
  }[tone]
  return (
    <div
      className={`flex flex-col gap-1 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-4 py-3 shadow-[var(--shadow-sm)] ${className}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-label">{label}</span>
        {icon && <span className="text-[var(--muted)]">{icon}</span>}
      </div>
      <div className={`text-num text-[1.375rem] leading-7 font-semibold tracking-tight ${valueTone}`}>
        {value}
      </div>
      {hint && <div className="text-meta truncate">{hint}</div>}
    </div>
  )
}

// --- badges and status -------------------------------------------------------

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'accent'

/**
 * A small labelled chip. `band` maps to the risk palette so a priority, a severity and
 * a risk band share one colour meaning. The text is always the meaning; colour is extra.
 */
export function Badge({
  tone = 'neutral',
  band,
  children,
  className = '',
  size = 'sm',
  icon,
  title,
}: {
  tone?: Tone
  band?: RiskBand | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  children: ReactNode
  className?: string
  size?: 'xs' | 'sm'
  icon?: ReactNode
  title?: string
}) {
  const colour = band ? `risk-${band}` : `tone-${tone}`
  return (
    <span
      title={title}
      className={`${colour} inline-flex items-center gap-1 rounded-[4px] border font-medium whitespace-nowrap ${
        size === 'xs' ? 'px-1 py-0 text-[0.6875rem] leading-4' : 'px-1.5 py-0.5 text-xs leading-4'
      } ${className}`}
    >
      {icon}
      {children}
    </span>
  )
}

const STATUS_TONE: Record<string, Tone> = {
  // analysis
  QUEUED: 'neutral',
  RUNNING: 'info',
  COMPLETED: 'success',
  PARTIAL: 'warning',
  FAILED: 'danger',
  CANCELLED: 'neutral',
  // case
  OPEN: 'accent',
  ANALYSING: 'info',
  REVIEW: 'warning',
  CLOSED: 'neutral',
}

const STATUS_DOT: Record<Tone, string> = {
  neutral: 'bg-[var(--border-strong)]',
  info: 'bg-[var(--info-fg)]',
  success: 'bg-[var(--success-fg)]',
  warning: 'bg-[var(--warning-fg)]',
  danger: 'bg-[var(--danger-fg)]',
  accent: 'bg-[var(--accent)]',
}

export function statusTone(status: string): Tone {
  return STATUS_TONE[status] ?? 'neutral'
}

/** A status word with its dot. Running states pulse; the word never leaves. */
export function StatusPill({
  status,
  label,
  className = '',
  ...rest
}: {
  status: string
  label?: string
  className?: string
  'data-testid'?: string
}) {
  const tone = statusTone(status)
  const live = status === 'RUNNING' || status === 'ANALYSING'
  return (
    <span
      {...rest}
      className={`inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)] px-2 py-0.5 text-xs font-medium tracking-wide text-[var(--text-2)] uppercase ${className}`}
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[tone]} ${live ? 'pulse-ring' : ''}`}
      />
      {label ?? status}
    </span>
  )
}

/** A 0–100 bar in the band's colour, with the band word beside it. */
export function Meter({
  value,
  band,
  className = '',
  showValue = false,
}: {
  value: number
  band: RiskBand
  className?: string
  showValue?: boolean
}) {
  const pct = Math.max(0, Math.min(100, value))
  const fill = {
    LOW: 'bg-[var(--risk-low-border)]',
    MEDIUM: 'bg-[var(--risk-medium-border)]',
    HIGH: 'bg-[var(--risk-high-border)]',
    CRITICAL: 'bg-[var(--risk-critical-border)]',
  }[band]
  return (
    <div className={`flex items-center gap-2 ${className}`} aria-hidden="true">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--surface-3)]">
        <div
          className={`h-full rounded-full ${fill} transition-[width] duration-500 ease-out`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showValue && <span className="text-num text-xs text-[var(--muted)]">{Math.round(pct)}</span>}
    </div>
  )
}

// --- forms -------------------------------------------------------------------

export function Field({
  label,
  hint,
  error,
  required,
  children,
  className = '',
}: {
  label: string
  hint?: ReactNode
  error?: string | null
  required?: boolean
  className?: string
  children: (props: { id: string; 'aria-describedby'?: string; 'aria-invalid'?: true }) => ReactNode
}) {
  const id = useId()
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ')

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <label htmlFor={id} className="text-secondary font-medium text-[var(--text-2)]">
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
        <p id={hintId} className="text-meta">
          {hint}
        </p>
      )}
      {error && (
        <p
          id={errorId}
          role="alert"
          className="flex items-start gap-1 text-xs font-medium text-[var(--danger)]"
        >
          <AlertTriangleIcon className="mt-0.5 h-3 w-3 shrink-0" />
          <span>{error}</span>
        </p>
      )}
    </div>
  )
}

const CONTROL =
  'transition-ui w-full rounded-[var(--radius-sm)] border border-[var(--border-strong)] bg-[var(--surface)] px-2.5 text-[var(--text)] placeholder:text-[var(--muted)]/70 hover:border-[var(--muted)] focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-soft)] aria-invalid:border-[var(--danger)] aria-invalid:focus:ring-[var(--danger-bg)] disabled:bg-[var(--surface-2)] disabled:opacity-70'

export function TextInput({ className = '', ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${CONTROL} h-9 ${className}`} />
}

export function TextArea({
  className = '',
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${CONTROL} min-h-20 py-2 ${className}`} rows={props.rows ?? 3} />
}

export function Select({ className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${CONTROL} h-9 pr-8 ${className}`} />
}

// --- notices -----------------------------------------------------------------

const BANNER_TONE = {
  info: { cls: 'tone-info', word: 'Note', Icon: InfoIcon },
  success: { cls: 'tone-success', word: 'Done', Icon: CheckCircleIcon },
  warning: { cls: 'tone-warning', word: 'Warning', Icon: AlertTriangleIcon },
  error: { cls: 'tone-danger', word: 'Error', Icon: XCircleIcon },
}

/** Neutral notice. `tone` changes the icon and the word, not only the colour. */
export function Banner({
  tone,
  title,
  children,
  compact = false,
  className = '',
}: {
  tone: 'info' | 'success' | 'warning' | 'error'
  title: string
  children?: ReactNode
  compact?: boolean
  className?: string
}) {
  const { cls, word, Icon } = BANNER_TONE[tone]
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`${cls} flex gap-2.5 rounded-[var(--radius)] border ${compact ? 'px-3 py-2' : 'p-3'} ${className}`}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className={compact ? 'text-secondary font-semibold' : 'font-semibold'}>
          <span className="sr-only">{word}: </span>
          {title}
        </p>
        {children && <div className="text-secondary mt-1 text-[var(--text)]/90">{children}</div>}
      </div>
    </div>
  )
}

export function EmptyState({
  title,
  children,
  action,
  icon,
  compact = false,
}: {
  title: string
  children?: ReactNode
  action?: ReactNode
  icon?: ReactNode
  compact?: boolean
}) {
  return (
    <div
      className={`flex flex-col items-center rounded-[var(--radius-lg)] border border-dashed border-[var(--border-strong)] text-center ${compact ? 'px-4 py-6' : 'px-6 py-10'}`}
    >
      {icon && (
        <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-full bg-[var(--surface-2)] text-[var(--muted)] [&>svg]:h-4 [&>svg]:w-4">
          {icon}
        </div>
      )}
      <p className="font-semibold">{title}</p>
      {children && (
        <div className="text-secondary mx-auto mt-1 max-w-prose text-[var(--muted)]">{children}</div>
      )}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

export function Spinner({ label, className = '' }: { label: string; className?: string }) {
  return (
    <p
      role="status"
      className={`text-secondary flex items-center gap-2 p-4 text-[var(--muted)] ${className}`}
    >
      <SpinnerIcon className="h-4 w-4" />
      {label}
    </p>
  )
}

/** Placeholder blocks that hold the layout while a request is in flight. */
export function Skeleton({
  className = '',
  lines,
}: {
  className?: string
  /** Render this many text-height lines instead of one block. */
  lines?: number
}) {
  if (lines) {
    return (
      <div className={`flex flex-col gap-2 ${className}`} aria-hidden="true">
        {Array.from({ length: lines }, (_, index) => (
          <div
            key={index}
            className="skeleton h-3.5"
            style={{ width: `${index === lines - 1 ? 55 : 85 + ((index * 7) % 15)}%` }}
          />
        ))}
      </div>
    )
  }
  return <div aria-hidden="true" className={`skeleton ${className}`} />
}

/** A loading region that announces itself once, then shows skeletons. */
export function Loading({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      {children}
    </div>
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
        <p className="font-mono text-xs opacity-80">request {error.body.request_id}</p>
      )}
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-2" onClick={onRetry}>
          Try again
        </Button>
      )}
    </Banner>
  )
}

// --- layout helpers ----------------------------------------------------------

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className = '',
}: {
  eyebrow?: ReactNode
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div className={`flex flex-wrap items-end justify-between gap-x-4 gap-y-3 ${className}`}>
      <div className="min-w-0">
        {eyebrow && <div className="text-label mb-1">{eyebrow}</div>}
        <h1 className="text-h1">{title}</h1>
        {description && <p className="text-secondary mt-1 text-[var(--muted)]">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** Label/value pairs in a compact grid. */
export function Facts({
  items,
  columns = 2,
  className = '',
}: {
  items: { label: string; value: ReactNode }[]
  columns?: 1 | 2 | 3
  className?: string
}) {
  const cols = { 1: '', 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-3' }[columns]
  return (
    <dl className={`grid gap-x-6 gap-y-2 ${cols} ${className}`}>
      {items.map((item) => (
        <div key={item.label} className="flex min-w-0 items-baseline justify-between gap-3">
          <dt className="text-secondary shrink-0 text-[var(--muted)]">{item.label}</dt>
          <dd className="text-secondary text-num min-w-0 truncate text-right font-medium">
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  )
}

/** A short numbered flow. The current step is bold; finished ones tick. */
export function Steps({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-3 gap-y-1" aria-label="Progress">
      {steps.map((step, index) => {
        const done = index < current
        const active = index === current
        return (
          <li key={step} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className={`text-num flex h-5 w-5 items-center justify-center rounded-full border text-[0.6875rem] font-semibold ${
                done
                  ? 'border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success-fg)]'
                  : active
                    ? 'border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-contrast)]'
                    : 'border-[var(--border-strong)] text-[var(--muted)]'
              }`}
            >
              {done ? <CheckCircleIcon className="h-3 w-3" /> : index + 1}
            </span>
            <span
              className={`text-secondary ${active ? 'font-semibold' : 'text-[var(--muted)]'}`}
              aria-current={active ? 'step' : undefined}
            >
              {step}
            </span>
            {index < steps.length - 1 && (
              <span aria-hidden="true" className="h-px w-6 bg-[var(--border-strong)]" />
            )}
          </li>
        )
      })}
    </ol>
  )
}
