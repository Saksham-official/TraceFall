/**
 * The public front door. Every claim on this page is one the product can keep — the
 * wording is bounded by docs/LIMITATIONS.md §13.
 */

import { Link } from 'react-router-dom'

import { LogoMark, Wordmark } from '../components/Logo'
import { TierBadge } from '../components/TierBadge'
import {
  ActivityIcon,
  ArrowRightIcon,
  BuildingIcon,
  FileTextIcon,
  GitBranchIcon,
  HashIcon,
  LayersIcon,
  ShieldCheckIcon,
  WalletIcon,
} from '../components/icons'
import { Button, Meter } from '../components/ui'

const PIPELINE = [
  { Icon: WalletIcon, title: 'Suspect wallet', body: 'The address the victim reported, with the amount and time they sent.' },
  { Icon: ActivityIcon, title: 'Blockchain activity', body: 'Every transfer touching the address, retrieved and stored as evidence.' },
  { Icon: GitBranchIcon, title: 'Fund flow', body: 'Value followed forward hop by hop, with proportional attribution.' },
  { Icon: LayersIcon, title: 'Patterns', body: 'Fan-out, fan-in, rapid movement and peel chains, named in plain words.' },
  { Icon: BuildingIcon, title: 'Attribution', body: 'Which exchange received the funds, and how sure the evidence lets us be.' },
  { Icon: ShieldCheckIcon, title: 'Risk', body: 'A transparent score with every contributing signal itemised.' },
  { Icon: FileTextIcon, title: 'Report', body: 'A PDF for the case file with an appendix of transaction hashes.' },
]

const CAPABILITIES = [
  {
    Icon: GitBranchIcon,
    title: 'Traces fund flows across multiple hops',
    body: 'On TRON and Ethereum, USDT first. Branches below the taint threshold and past the fan-out cap are reported as pruned, never silently dropped.',
  },
  {
    Icon: BuildingIcon,
    title: 'Identifies addresses associated with known exchanges',
    body: 'Curated public datasets for confirmed matches. A behavioural deposit-address heuristic for likely ones — with its confidence and its signals shown.',
  },
  {
    Icon: ShieldCheckIcon,
    title: 'Shows where on-chain tracing ends',
    body: 'At an exchange, a mixer, a bridge or a swap, the trace stops and says so. That is the point where a legal request begins.',
  },
]

const HONEST = [
  'Every entity claim carries exactly one tier. They are never collapsed — not in the database, the API, the screen or the report.',
  'Every conclusion expands to its signals, its transactions, and the stored raw response with its hash and retrieval time.',
  'No model ships. Every number is deterministic, inspectable, and explainable in one sentence.',
  'Partial data, pruned branches and unavailable stages are surfaced on screen, never folded into a smaller answer.',
]

const NOT_CLAIMED = [
  'It does not identify people. That needs KYC records held by the exchange.',
  'It does not decide that fraud occurred. That is a court’s decision.',
  'It does not freeze or recover funds, and holds no keys.',
  'It does not trace through mixers, across bridges, or past a token swap automatically.',
]

export function WelcomePage() {
  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--surface)]/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <Link to="/welcome" className="flex items-center gap-2 text-[0.9375rem]">
            <LogoMark />
            <Wordmark />
          </Link>
          <nav className="flex items-center gap-2">
            <a href="#how" className="text-secondary hidden px-2 text-[var(--muted)] hover:text-[var(--text)] sm:inline">
              How it works
            </a>
            <a href="#honest" className="text-secondary hidden px-2 text-[var(--muted)] hover:text-[var(--text)] sm:inline">
              Honest by design
            </a>
            <Link to="/login">
              <Button size="sm">Sign in</Button>
            </Link>
          </nav>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="relative overflow-hidden border-b border-[var(--border)] bg-[var(--surface)]">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 opacity-40"
            style={{
              backgroundImage:
                'linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)',
              backgroundSize: '32px 32px',
              maskImage: 'radial-gradient(ellipse at 50% 0%, black 10%, transparent 70%)',
            }}
          />
          <div className="relative mx-auto grid max-w-6xl gap-12 px-6 py-20 lg:grid-cols-[1.1fr_1fr] lg:items-center">
            <div>
              <p className="text-label mb-3 text-[var(--accent)]">Blockchain intelligence for cybercrime investigators</p>
              <h1 className="text-display text-[2.5rem] leading-[2.9rem] sm:text-[3rem] sm:leading-[3.4rem]">
                Investigate crypto crime faster.
              </h1>
              <p className="mt-5 max-w-xl text-[1.0625rem] leading-7 text-[var(--muted)]">
                A victim reports a wallet address. TraceFall follows the money, names the exchange
                that received it with the evidence behind the claim, and produces a report an
                investigator can act on — in about ninety seconds against a cached snapshot.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link to="/login">
                  <Button icon={<ArrowRightIcon />}>Sign in to investigate</Button>
                </Link>
                <a href="#how">
                  <Button variant="secondary">See how it works</Button>
                </a>
              </div>
              <p className="text-meta mt-6">
                Read-only against every blockchain · no keys held · no victim data stored
              </p>
            </div>

            {/* Product vignette: a real finding, drawn as the product draws it. */}
            <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg)] p-4 shadow-[var(--shadow-md)]">
              <div className="flex items-center justify-between">
                <span className="text-label">Where the money went</span>
                <span className="risk-HIGH inline-flex items-baseline gap-1.5 rounded-[var(--radius-sm)] border px-2 py-0.5 text-xs">
                  <span className="font-semibold">67</span>
                  <span className="font-semibold tracking-wide uppercase">High</span>
                </span>
              </div>
              <ul className="mt-3 space-y-2">
                {[
                  { addr: 'TXn8kL…gH5jK2m', tier: 'CONFIRMED' as const, entity: 'Exchange hot wallet', share: '62%' },
                  { addr: 'TQn9Y2…KcbLSE', tier: 'PROBABLE' as const, entity: 'Exchange deposit address', share: '23%', conf: 0.87 },
                  { addr: 'TLFqEh…kgRnWf', tier: 'UNATTRIBUTED' as const, entity: 'Funds have not moved', share: '15%' },
                ].map((row) => (
                  <li
                    key={row.addr}
                    className="flex items-center gap-3 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2"
                  >
                    <code className="font-mono text-xs">{row.addr}</code>
                    <span className="text-secondary min-w-0 flex-1 truncate text-[var(--muted)]">
                      {row.entity}
                    </span>
                    <TierBadge tier={row.tier} confidence={row.conf} />
                    <span className="text-num w-10 text-right text-xs font-medium">{row.share}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-3">
                <div className="mb-1 flex justify-between text-xs text-[var(--muted)]">
                  <span>Risk signals</span>
                  <span>4 of 11 fired</span>
                </div>
                <Meter value={67} band="HIGH" />
              </div>
              <p className="text-meta mt-3">
                Illustrative layout. Three tiers, always shown apart.
              </p>
            </div>
          </div>
        </section>

        {/* Pipeline */}
        <section id="how" className="mx-auto max-w-6xl px-6 py-16">
          <h2 className="text-h1">From a wallet address to a report</h2>
          <p className="text-secondary mt-2 max-w-2xl text-[var(--muted)]">
            Seven stages, each deterministic. The same input always gives the same output, and
            every stage leaves evidence the next one can be checked against.
          </p>
          <ol className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
            {PIPELINE.map(({ Icon, title, body }, index) => (
              <li
                key={title}
                className="relative rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-4"
              >
                <div className="flex items-center justify-between">
                  <span className="flex h-8 w-8 items-center justify-center rounded-[var(--radius)] bg-[var(--accent-soft)] text-[var(--accent)]">
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="text-num font-mono text-xs text-[var(--muted)]">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                </div>
                <p className="mt-3 font-semibold">{title}</p>
                <p className="text-meta mt-1">{body}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* Capabilities */}
        <section className="border-y border-[var(--border)] bg-[var(--surface)]">
          <div className="mx-auto max-w-6xl px-6 py-16">
            <h2 className="text-h1">What it does</h2>
            <div className="mt-8 grid gap-4 md:grid-cols-3">
              {CAPABILITIES.map(({ Icon, title, body }) => (
                <article
                  key={title}
                  className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg)] p-5"
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-[var(--radius)] bg-[var(--accent-soft)] text-[var(--accent)]">
                    <Icon className="h-4 w-4" />
                  </span>
                  <h3 className="mt-4 text-h2">{title}</h3>
                  <p className="text-secondary mt-2 text-[var(--muted)]">{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* Honest by design */}
        <section id="honest" className="mx-auto grid max-w-6xl gap-10 px-6 py-16 lg:grid-cols-2">
          <div>
            <h2 className="text-h1">Honest by design</h2>
            <p className="text-secondary mt-2 text-[var(--muted)]">
              The failure this prevents is concrete: an investigator sending a legal request to the
              wrong institution because an interface presented a guess as a fact.
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              <TierBadge tier="CONFIRMED" size="md" />
              <TierBadge tier="PROBABLE" confidence={0.87} size="md" />
              <TierBadge tier="UNATTRIBUTED" size="md" />
            </div>
            <ul className="mt-6 space-y-3">
              {HONEST.map((line) => (
                <li key={line} className="flex gap-3">
                  <HashIcon className="mt-1 h-3.5 w-3.5 shrink-0 text-[var(--accent)]" />
                  <span className="text-secondary">{line}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-6">
            <h3 className="text-h2">What it does not claim</h3>
            <p className="text-secondary mt-1 text-[var(--muted)]">
              Knowing where the system stops is what makes everything before that point
              trustworthy.
            </p>
            <ul className="mt-4 space-y-3">
              {NOT_CLAIMED.map((line) => (
                <li key={line} className="text-secondary flex gap-3">
                  <span aria-hidden="true" className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--border-strong)]" />
                  {line}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Closing CTA */}
        <section className="border-t border-[var(--border)] bg-[var(--surface)]">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-12">
            <div>
              <h2 className="text-h1">Open a case. Paste the address.</h2>
              <p className="text-secondary mt-1 text-[var(--muted)]">
                The answer, with its evidence, in minutes rather than days.
              </p>
            </div>
            <Link to="/login">
              <Button icon={<ArrowRightIcon />}>Sign in</Button>
            </Link>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-6">
        <span className="flex items-center gap-2 text-[var(--muted)]">
          <LogoMark className="h-5 w-5" />
          <Wordmark className="text-sm" />
        </span>
        <p className="text-meta">
          Reproducible analysis of public blockchain data. Admissibility is determined by courts
          and agency procedure.
        </p>
      </footer>
    </div>
  )
}
