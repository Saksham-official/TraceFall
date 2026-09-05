import { Link } from 'react-router-dom'

import { useAcknowledgeAlert, useOpenAlerts } from '../api/queries'
import type { Alert, AlertType } from '../api/types'
import { relativeTime, truncateAddress } from '../lib/format'
import { Button, Card, EmptyState, ErrorNotice, Spinner } from './ui'

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

function AlertRow({ alert }: { alert: Alert }) {
  const acknowledge = useAcknowledgeAlert()
  return (
    <li className="border-b border-[var(--border)] p-3 last:border-b-0">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {/* The severity word, never the colour alone (NFR-18). */}
        <span className={`risk-${alert.severity} rounded border px-1.5 py-0.5 text-xs font-medium`}>
          {alert.severity}
        </span>
        <span className="font-medium">{HEADLINE[alert.alert_type]}</span>
        <span className="ml-auto text-xs text-[var(--muted)]">
          {relativeTime(alert.created_at)}
        </span>
      </div>
      <p className="mt-1 text-sm text-[var(--muted)]">{alert.trigger_reason}</p>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
        {alert.address && (
          <code title={alert.address} className="font-mono">
            {truncateAddress(alert.address)}
          </code>
        )}
        <Link to={`/cases/${alert.case_id}`} className="underline">
          Open case
        </Link>
        <Button
          variant="secondary"
          className="ml-auto"
          disabled={acknowledge.isPending}
          onClick={() => acknowledge.mutate(alert.id)}
        >
          {acknowledge.isPending ? 'Acknowledging…' : 'Acknowledge'}
        </Button>
      </div>
      {acknowledge.isError && <ErrorNotice error={acknowledge.error} />}
    </li>
  )
}

/**
 * Open alerts across every case the user may see (FR-101, FR-102).
 *
 * Acknowledging removes an alert from this list — it does not delete it. The record of who
 * first took responsibility, and when, stays on the row.
 */
export function AlertsPanel() {
  const alerts = useOpenAlerts()
  const items = alerts.data?.items ?? []

  return (
    <Card className="p-0">
      <h2 className="border-b border-[var(--border)] px-3 py-2 font-semibold">
        Alerts
        {items.length > 0 && (
          <span className="ml-1.5 text-[var(--muted)]">{items.length}</span>
        )}
      </h2>
      {alerts.isPending && <Spinner label="Loading alerts…" />}
      {alerts.isError && <ErrorNotice error={alerts.error} onRetry={() => void alerts.refetch()} />}
      {alerts.isSuccess &&
        (items.length === 0 ? (
          <div className="p-3">
            <EmptyState title="No open alerts">
              <p>
                A sanctioned address, a mixer, or a critical risk score in any analysis appears
                here as soon as the pipeline finds it.
              </p>
            </EmptyState>
          </div>
        ) : (
          <ul>
            {items.map((alert) => (
              <AlertRow key={alert.id} alert={alert} />
            ))}
          </ul>
        ))}
    </Card>
  )
}
