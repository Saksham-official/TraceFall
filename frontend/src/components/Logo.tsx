/** The mark: a fund flow falling through hops to its terminal. Wordmark beside it. */

export function LogoMark({ className = 'h-6 w-6' }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" className={className}>
      <rect width="24" height="24" rx="6" fill="var(--accent)" />
      <path
        d="M7 6.5h10M12 6.5v4M12 10.5 8.5 14M12 10.5l3.5 3.5"
        stroke="var(--accent-contrast)"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="8.5" cy="16.5" r="1.6" fill="var(--accent-contrast)" />
      <circle cx="15.5" cy="16.5" r="1.6" fill="var(--accent-contrast)" />
    </svg>
  )
}

export function Wordmark({ className = '' }: { className?: string }) {
  return (
    <span className={`font-semibold tracking-tight ${className}`}>
      Trace<span className="text-[var(--accent)]">Fall</span>
    </span>
  )
}
