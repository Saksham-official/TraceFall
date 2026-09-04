/**
 * Hand-rolled inline icons. An icon library would be a dependency for six paths.
 * Every icon is decorative — the text beside it always carries the meaning.
 */

import type { ReactNode } from 'react'

type Props = { className?: string }

const base = 'h-3.5 w-3.5 shrink-0'

function Svg({ className, children }: Props & { children: ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className ?? base}
    >
      {children}
    </svg>
  )
}

/** CONFIRMED */
export function ShieldCheckIcon(props: Props) {
  return (
    <Svg {...props}>
      <path d="M8 1.5 13.5 3.5v4.2c0 3.2-2.3 5.6-5.5 6.8-3.2-1.2-5.5-3.6-5.5-6.8V3.5Z" />
      <path d="M5.6 7.8 7.3 9.5l3.1-3.1" />
    </Svg>
  )
}

/** PROBABLE */
export function QuestionDiamondIcon(props: Props) {
  return (
    <Svg {...props}>
      <path d="M8 1.2 14.8 8 8 14.8 1.2 8Z" />
      <path d="M6.6 6.3a1.45 1.45 0 1 1 1.9 1.4c-.35.13-.5.4-.5.75v.35" />
      <path d="M8 11.2h.01" />
    </Svg>
  )
}

/** UNATTRIBUTED */
export function DashIcon(props: Props) {
  return (
    <Svg {...props}>
      <path d="M3.5 8h9" />
    </Svg>
  )
}

export function CopyIcon(props: Props) {
  return (
    <Svg {...props}>
      <rect x="5.5" y="5.5" width="9" height="9" rx="1.5" />
      <path d="M10.5 3.2a1.7 1.7 0 0 0-1.7-1.7H3.2a1.7 1.7 0 0 0-1.7 1.7v5.6a1.7 1.7 0 0 0 1.7 1.7" />
    </Svg>
  )
}

export function ExternalLinkIcon(props: Props) {
  return (
    <Svg {...props}>
      <path d="M9.5 2h4.5v4.5" />
      <path d="M14 2 7.5 8.5" />
      <path d="M12.5 9.6V13a1.5 1.5 0 0 1-1.5 1.5H3A1.5 1.5 0 0 1 1.5 13V5A1.5 1.5 0 0 1 3 3.5h3.4" />
    </Svg>
  )
}

export function CheckIcon(props: Props) {
  return (
    <Svg {...props}>
      <path d="M3 8.5 6.2 11.7 13 4.9" />
    </Svg>
  )
}
