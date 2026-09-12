/**
 * Hand-rolled inline icons, one family: 16-unit grid, 1.5 stroke, round joins. An icon
 * library would be a dependency for thirty paths.
 *
 * Every icon is decorative — the text beside it always carries the meaning.
 */

import type { ReactNode } from 'react'

export type IconProps = { className?: string }

const base = 'h-3.5 w-3.5 shrink-0'

function Svg({ className, children }: IconProps & { children: ReactNode }) {
  // A caller's className adds colour or spacing; it only replaces the size when it sets one.
  const cls = /\bh-/.test(className ?? '') ? className : `${base} ${className ?? ''}`
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
      className={cls}
    >
      {children}
    </svg>
  )
}

// --- attribution tiers -------------------------------------------------------

/** CONFIRMED */
export function ShieldCheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 1.5 13.5 3.5v4.2c0 3.2-2.3 5.6-5.5 6.8-3.2-1.2-5.5-3.6-5.5-6.8V3.5Z" />
      <path d="M5.6 7.8 7.3 9.5l3.1-3.1" />
    </Svg>
  )
}

/** PROBABLE */
export function QuestionDiamondIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 1.2 14.8 8 8 14.8 1.2 8Z" />
      <path d="M6.6 6.3a1.45 1.45 0 1 1 1.9 1.4c-.35.13-.5.4-.5.75v.35" />
      <path d="M8 11.2h.01" />
    </Svg>
  )
}

/** UNATTRIBUTED */
export function DashIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3.5 8h9" />
    </Svg>
  )
}

// --- actions -----------------------------------------------------------------

export function CopyIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="5.5" y="5.5" width="9" height="9" rx="1.5" />
      <path d="M10.5 3.2a1.7 1.7 0 0 0-1.7-1.7H3.2a1.7 1.7 0 0 0-1.7 1.7v5.6a1.7 1.7 0 0 0 1.7 1.7" />
    </Svg>
  )
}

export function ExternalLinkIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9.5 2h4.5v4.5" />
      <path d="M14 2 7.5 8.5" />
      <path d="M12.5 9.6V13a1.5 1.5 0 0 1-1.5 1.5H3A1.5 1.5 0 0 1 1.5 13V5A1.5 1.5 0 0 1 3 3.5h3.4" />
    </Svg>
  )
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 8.5 6.2 11.7 13 4.9" />
    </Svg>
  )
}

export function PlusIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 3v10M3 8h10" />
    </Svg>
  )
}

export function TrashIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M2.5 4h11M5.5 4V2.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1V4M12.5 4v9.5a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1V4" />
      <path d="M6.5 7v4.5M9.5 7v4.5" />
    </Svg>
  )
}

export function SearchIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="7" cy="7" r="4.5" />
      <path d="m10.5 10.5 3.5 3.5" />
    </Svg>
  )
}

export function ArrowLeftIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M13 8H3M7 4 3 8l4 4" />
    </Svg>
  )
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 8h10M9 4l4 4-4 4" />
    </Svg>
  )
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m4 6 4 4 4-4" />
    </Svg>
  )
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m6 4 4 4-4 4" />
    </Svg>
  )
}

export function DownloadIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 2.5v8M4.5 7 8 10.5 11.5 7" />
      <path d="M2.5 11.5v1a1.5 1.5 0 0 0 1.5 1.5h8a1.5 1.5 0 0 0 1.5-1.5v-1" />
    </Svg>
  )
}

export function LogOutIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 2.5H3.5A1.5 1.5 0 0 0 2 4v8a1.5 1.5 0 0 0 1.5 1.5H6" />
      <path d="M10 11.5 13.5 8 10 4.5M13.5 8H6" />
    </Svg>
  )
}

export function XIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m4 4 8 8M12 4l-8 8" />
    </Svg>
  )
}

// --- graph controls ----------------------------------------------------------

export function ZoomInIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="7" cy="7" r="4.5" />
      <path d="m10.5 10.5 3.5 3.5M7 5v4M5 7h4" />
    </Svg>
  )
}

export function ZoomOutIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="7" cy="7" r="4.5" />
      <path d="m10.5 10.5 3.5 3.5M5 7h4" />
    </Svg>
  )
}

export function MaximizeIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10" />
    </Svg>
  )
}

export function CrosshairIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="5" />
      <path d="M8 1.5v3M8 11.5v3M1.5 8h3M11.5 8h3" />
    </Svg>
  )
}

// --- status and meaning ------------------------------------------------------

export function AlertTriangleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M7.1 2.6 1.6 12.3a1 1 0 0 0 .9 1.5h11a1 1 0 0 0 .9-1.5L8.9 2.6a1 1 0 0 0-1.8 0Z" />
      <path d="M8 6.2v3.3M8 11.6h.01" />
    </Svg>
  )
}

export function InfoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 7.3v3.6M8 5.2h.01" />
    </Svg>
  )
}

export function CheckCircleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6" />
      <path d="m5.3 8.2 1.8 1.8 3.6-3.7" />
    </Svg>
  )
}

export function XCircleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6" />
      <path d="m5.8 5.8 4.4 4.4M10.2 5.8l-4.4 4.4" />
    </Svg>
  )
}

export function ClockIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4.5V8l2.3 1.5" />
    </Svg>
  )
}

export function BanIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6" />
      <path d="m3.8 3.8 8.4 8.4" />
    </Svg>
  )
}

export function ActivityIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M1.5 8h3l1.8-4.5 3.4 9L11.5 8h3" />
    </Svg>
  )
}

export function BellIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 11V7a4 4 0 0 1 8 0v4l1.2 1.5H2.8Z" />
      <path d="M6.6 14a1.5 1.5 0 0 0 2.8 0" />
    </Svg>
  )
}

export function ShieldIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 1.5 13.5 3.5v4.2c0 3.2-2.3 5.6-5.5 6.8-3.2-1.2-5.5-3.6-5.5-6.8V3.5Z" />
    </Svg>
  )
}

// --- domain objects ----------------------------------------------------------

export function WalletIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M2 5.5A1.5 1.5 0 0 1 3.5 4h9A1.5 1.5 0 0 1 14 5.5v6a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 11.5Z" />
      <path d="M2 7h12M10.5 9.5h1.5" />
    </Svg>
  )
}

export function BuildingIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 14V3a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v11M11 6h1.5a.5.5 0 0 1 .5.5V14M1.5 14h13" />
      <path d="M5.5 4.5h1M7.5 4.5h1M5.5 7h1M7.5 7h1M5.5 9.5h1M7.5 9.5h1" />
    </Svg>
  )
}

export function GitBranchIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="4" cy="3.5" r="1.5" />
      <circle cx="4" cy="12.5" r="1.5" />
      <circle cx="12" cy="5.5" r="1.5" />
      <path d="M4 5v6M12 7c0 2.5-3 3-6 3.5" />
    </Svg>
  )
}

export function LayersIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m8 2 6 3-6 3-6-3Z" />
      <path d="m2 8 6 3 6-3M2 11l6 3 6-3" />
    </Svg>
  )
}

export function FileTextIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9 1.5H4.5A1.5 1.5 0 0 0 3 3v10a1.5 1.5 0 0 0 1.5 1.5h7A1.5 1.5 0 0 0 13 13V5.5Z" />
      <path d="M9 1.5v4h4M5.5 8.5h5M5.5 11h5" />
    </Svg>
  )
}

export function HashIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 6h10M3 10h10M6.5 2.5l-1 11M10.5 2.5l-1 11" />
    </Svg>
  )
}

export function LinkIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6.5 9.5a3 3 0 0 0 4.2 0l2-2a3 3 0 0 0-4.2-4.2l-.8.8" />
      <path d="M9.5 6.5a3 3 0 0 0-4.2 0l-2 2a3 3 0 0 0 4.2 4.2l.8-.8" />
    </Svg>
  )
}

export function FolderIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M1.5 4.5A1.5 1.5 0 0 1 3 3h3l1.5 1.5H13A1.5 1.5 0 0 1 14.5 6v6A1.5 1.5 0 0 1 13 13.5H3A1.5 1.5 0 0 1 1.5 12Z" />
    </Svg>
  )
}

export function UserIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="5.5" r="2.75" />
      <path d="M2.5 14a5.5 5.5 0 0 1 11 0" />
    </Svg>
  )
}

export function SunIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" />
    </Svg>
  )
}

export function MoonIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M13.5 9.5A6 6 0 0 1 6.5 2.5a6 6 0 1 0 7 7Z" />
    </Svg>
  )
}

export function SpinnerIcon(props: IconProps) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      className={`${props.className ?? base} animate-[spin_0.8s_linear_infinite]`}
    >
      <circle cx="8" cy="8" r="6" className="opacity-25" />
      <path d="M14 8a6 6 0 0 0-6-6" />
    </svg>
  )
}
