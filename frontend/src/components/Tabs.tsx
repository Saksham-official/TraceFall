import { useId, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'

export interface Tab {
  id: string
  label: string
  /** Rendered lazily so a tab whose API does not exist costs nothing. */
  render: () => ReactNode
  icon?: ReactNode
}

/** WAI-ARIA tabs with roving focus. A tab strip that needs a mouse fails on a demo laptop. */
export function Tabs({
  tabs,
  label = 'Sections',
  initial,
  onChange,
  sticky = false,
}: {
  tabs: Tab[]
  label?: string
  initial?: string
  onChange?: (id: string) => void
  /** Keep the strip visible while a long panel scrolls. */
  sticky?: boolean
}) {
  const base = useId()
  const [active, setActive] = useState(initial ?? tabs[0].id)
  const strip = useRef<HTMLDivElement>(null)

  function select(id: string) {
    setActive(id)
    onChange?.(id)
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = tabs.findIndex((tab) => tab.id === active)
    const moves: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      Home: 0,
      End: tabs.length - 1,
    }
    const next = moves[event.key]
    if (next === undefined) return
    event.preventDefault()
    const target = tabs[(next + tabs.length) % tabs.length]
    select(target.id)
    strip.current?.querySelector<HTMLButtonElement>(`#${CSS.escape(`${base}-${target.id}`)}`)?.focus()
  }

  const current = tabs.find((tab) => tab.id === active) ?? tabs[0]

  return (
    <div>
      <div
        className={`border-b border-[var(--border)] ${sticky ? 'sticky top-14 z-10 -mx-px bg-[var(--bg)]/95 backdrop-blur' : ''}`}
      >
        <div
          ref={strip}
          role="tablist"
          aria-label={label}
          onKeyDown={onKeyDown}
          className="-mb-px flex gap-1 overflow-x-auto"
        >
          {tabs.map((tab) => {
            const selected = tab.id === current.id
            return (
              <button
                key={tab.id}
                id={`${base}-${tab.id}`}
                role="tab"
                type="button"
                aria-selected={selected}
                aria-controls={`${base}-${tab.id}-panel`}
                tabIndex={selected ? 0 : -1}
                onClick={() => select(tab.id)}
                className={`transition-ui inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium whitespace-nowrap ${
                  selected
                    ? 'border-[var(--accent)] text-[var(--text)]'
                    : 'border-transparent text-[var(--muted)] hover:border-[var(--border-strong)] hover:text-[var(--text)]'
                }`}
              >
                {tab.icon && <span className="text-[var(--muted)]">{tab.icon}</span>}
                {tab.label}
              </button>
            )
          })}
        </div>
      </div>
      <div
        key={current.id}
        id={`${base}-${current.id}-panel`}
        role="tabpanel"
        aria-labelledby={`${base}-${current.id}`}
        tabIndex={0}
        className="fade-up pt-4 focus:outline-none"
      >
        {current.render()}
      </div>
    </div>
  )
}
