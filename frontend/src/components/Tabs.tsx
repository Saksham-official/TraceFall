import { useId, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'

export interface Tab {
  id: string
  label: string
  /** Rendered lazily so a tab whose API does not exist costs nothing. */
  render: () => ReactNode
}

/** WAI-ARIA tabs with roving focus. A tab strip that needs a mouse fails on a demo laptop. */
export function Tabs({ tabs }: { tabs: Tab[] }) {
  const base = useId()
  const [active, setActive] = useState(tabs[0].id)
  const strip = useRef<HTMLDivElement>(null)

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
    setActive(target.id)
    strip.current?.querySelector<HTMLButtonElement>(`#${CSS.escape(`${base}-${target.id}`)}`)?.focus()
  }

  const current = tabs.find((tab) => tab.id === active) ?? tabs[0]

  return (
    <div>
      <div
        ref={strip}
        role="tablist"
        aria-label="Case sections"
        onKeyDown={onKeyDown}
        className="flex flex-wrap gap-1 border-b border-[var(--border)]"
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
              onClick={() => setActive(tab.id)}
              className={`-mb-px rounded-t border-b-2 px-3 py-1.5 font-medium ${
                selected
                  ? 'border-[var(--accent)] text-[var(--text)]'
                  : 'border-transparent text-[var(--muted)] hover:text-[var(--text)]'
              }`}
            >
              {tab.label}
            </button>
          )
        })}
      </div>
      <div
        id={`${base}-${current.id}-panel`}
        role="tabpanel"
        aria-labelledby={`${base}-${current.id}`}
        tabIndex={0}
        className="pt-4"
      >
        {current.render()}
      </div>
    </div>
  )
}
