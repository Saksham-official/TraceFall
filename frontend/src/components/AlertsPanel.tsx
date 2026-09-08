import { Link } from 'react-router-dom'

import { useAcknowledgeAlert, useOpenAlerts } from '../api/queries'
import type { Alert, AlertType } from '../api/types'
import { relativeTime } from '../lib/format'
import { HashChip } from './AddressChip'
import { AlertTriangleIcon, BanIcon, BellIcon, LayersIcon, LinkIcon } from './icons'
import { Badge, Button, Card, EmptyState, ErrorNotice, Skeleton } from './ui'

/**
 * What each alert type means, in the investigator's language rather than the enum's.
 * A `SANCTIONED_CONTACT` is only ever raised on a CONFIRMED dataset match, so the wording
 * may state it as a fact; nothing here is allowed to phrase an inference that way.
 */
const HEADLINE: Record<AlertType, string> = {
  SANCTIONED_CONTACT: 'Sanctioned address in this trace',
  MIXER_CONTACT: 'Funds reached a mixer',
  CRITICAL_RISK: 'Critical risk score',
  CROSS_CASE_MATCH: 'Also appears in another case',
}

const TYPE_ICON: Record<AlertType, typeof BanIcon> = {
  SANCTIONED_CONTACT: BanIcon,
  MIXER_CONTACT: LayersIcon,
  CRITICAL_RISK: AlertTriangleIcon,
  CROSS_CASE_MATCH: LinkIcon,
}

const SEVERITY_RANK: Record<Alert['severity'], number> = { HIGH: 0, MEDIUM: 1, LOW: 2 }

function AlertRow({ alert }: { alert: Alert }) {
  const acknowledge = useAcknowledgeAlert()
  const Icon = TYPE_ICON[alert.alert_type]
  const accent = {
    HIGH: 'border-l-[var(--risk-high-border)]',
    MEDIUM: 'border-l-[var(--risk-medium-border)]',
    LOW: 'border-l-[var(--border-strong)]',
  }[alert.severity]

  return (
    <li className={`border-b border-l-2 border-[var(--border)] px-3 py-2.5 last:border-b-0 ${accent}`}>
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 text-[var(--muted)]">
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {/* The severity word, never the colour alone (NFR-18). */}
            <Badge band={alert.severity} size="xs">
              {alert.severity}
            </Badge>
            <span className="text-secondary font-semibold">{HEADLINE[alert.alert_type]}</span>
            <span className="text-meta ml-auto whitespace-nowrap">{relativeTime(alert.created_at)}</span>
          </div>
          <p className="text-secondary mt-1 text-[var(--muted)]">{alert.trigger_reason}</p>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
            {alert.address && <HashChip hash={alert.address} label="address" head={6} tail={7} />}
            <Link
              to={`/cases/${alert.case_id}`}
              className="text-xs font-medium text-[var(--accent)] hover:underline"
            >
              Open case
            </Link>
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto"
              loading={acknowledge.isPending}
              onClick={() => acknowledge.mutate(alert.id)}
            >
              {acknowledge.isPending ? 'Acknowledging…' : 'Acknowledge'}
            </Button>
          </div>
          {acknowledge.isError && (
            <div className="mt-2">
              <ErrorNotice error={acknowledge.error} />
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

/**
 * Open alerts across every case the user may see (FR-101, FR-102).
 *
 * Acknowledging removes an alert from this list — it does not delete it. The record of who
 * first took responsibility, and when, stays on the row.
 */
export function AlertsPanel({ className = '' }: { className?: string }) {
  const alerts = useOpenAlerts()
  const items = [...(alerts.data?.items ?? [])].sort(
    (a, b) =>
      SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
      b.created_at.localeCompare(a.created_at),
  )

  return (
    <Card padding="none" className={className}>
      <h2 className="flex items-center gap-2 border-b border-[var(--border)] px-3 py-2.5 text-h3">
        <BellIcon className="h-4 w-4 text-[var(--muted)]" />
        Alerts
        {items.length > 0 && (
          // The space matters: without it the accessible name reads "Alerts7".
          <span className="text-num ml-auto rounded-full bg-[var(--surface-2)] px-2 py-0.5 text-xs font-medium text-[var(--muted)]">
            {' '}
            ({items.length})
          </span>
        )}
      </h2>
      {alerts.isPending && (
        <div role="status" aria-label="Loading alerts" className="space-y-3 p-3">
          <Skeleton lines={3} />
          <Skeleton lines={3} />
        </div>
      )}
      {alerts.isError && (
        <div className="p-3">
          <ErrorNotice error={alerts.error} onRetry={() => void alerts.refetch()} />
        </div>
      )}
      {alerts.isSuccess &&
        (items.length === 0 ? (
          <div className="p-3">
            <EmptyState title="No open alerts" icon={<BellIcon />} compact>
              <p>
                A sanctioned address, a mixer, or a critical risk score in any analysis appears
                here as soon as the pipeline finds it.
              </p>
            </EmptyState>
          </div>
        ) : (
          <ul className="max-h-[calc(100vh-14rem)] overflow-y-auto">
            {items.map((alert) => (
              <AlertRow key={alert.id} alert={alert} />
            ))}
          </ul>
        ))}
    </Card>
  )
}
