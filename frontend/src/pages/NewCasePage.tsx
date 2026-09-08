import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useCreateCase } from '../api/queries'
import { PRIORITIES } from '../api/types'
import type { Priority } from '../api/types'
import { ArrowLeftIcon, ArrowRightIcon } from '../components/icons'
import {
  Button,
  Card,
  ErrorNotice,
  Field,
  Select,
  Steps,
  TextArea,
  TextInput,
} from '../components/ui'

const STEPS = ['Case', 'Suspect address', 'Analysis']

export function NewCasePage() {
  const navigate = useNavigate()
  const create = useCreateCase()
  const [form, setForm] = useState({
    title: '',
    ncrp_reference: '',
    fir_reference: '',
    description: '',
    reported_loss_inr: '',
    incident_date: '',
    priority: 'MEDIUM' as Priority,
  })

  const set = (key: keyof typeof form) => (value: string) =>
    setForm((current) => ({ ...current, [key]: value }))

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      {
        title: form.title.trim(),
        ncrp_reference: form.ncrp_reference.trim() || null,
        fir_reference: form.fir_reference.trim() || null,
        description: form.description.trim() || null,
        reported_loss_inr: form.reported_loss_inr.trim() || null,
        incident_date: form.incident_date || null,
        priority: form.priority,
      },
      { onSuccess: (created) => navigate(`/cases/${created.id}/address`, { replace: true }) },
    )
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5">
      <div>
        <Link
          to="/"
          className="text-secondary inline-flex items-center gap-1 text-[var(--muted)] hover:text-[var(--text)]"
        >
          <ArrowLeftIcon /> Cases
        </Link>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <h1 className="text-h1">New case</h1>
          <Steps steps={STEPS} current={0} />
        </div>
        <p className="text-secondary mt-1 text-[var(--muted)]">
          A case holds one investigation. The suspect address comes next.
        </p>
      </div>

      <Card>
        <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
          <Field label="Title" required>
            {(props) => (
              <TextInput
                {...props}
                required
                minLength={3}
                maxLength={300}
                value={form.title}
                placeholder="USDT investment fraud — complainant Rohtak"
                onChange={(e) => set('title')(e.target.value)}
              />
            )}
          </Field>

          <fieldset className="grid gap-4 sm:grid-cols-2">
            <legend className="text-label mb-3">References</legend>
            <Field label="NCRP reference">
              {(props) => (
                <TextInput
                  {...props}
                  maxLength={64}
                  className="font-mono"
                  value={form.ncrp_reference}
                  onChange={(e) => set('ncrp_reference')(e.target.value)}
                />
              )}
            </Field>
            <Field label="FIR reference">
              {(props) => (
                <TextInput
                  {...props}
                  maxLength={64}
                  className="font-mono"
                  value={form.fir_reference}
                  onChange={(e) => set('fir_reference')(e.target.value)}
                />
              )}
            </Field>
          </fieldset>

          <Field label="Description" hint="No victim personal data. Reference numbers only.">
            {(props) => (
              <TextArea
                {...props}
                maxLength={20000}
                value={form.description}
                onChange={(e) => set('description')(e.target.value)}
              />
            )}
          </Field>

          <fieldset className="grid gap-4 sm:grid-cols-3">
            <legend className="text-label mb-3">Incident</legend>
            <Field label="Reported loss (INR)">
              {(props) => (
                <TextInput
                  {...props}
                  type="number"
                  min="0"
                  step="1"
                  inputMode="numeric"
                  className="text-num"
                  value={form.reported_loss_inr}
                  onChange={(e) => set('reported_loss_inr')(e.target.value)}
                />
              )}
            </Field>
            <Field label="Incident date">
              {(props) => (
                <TextInput
                  {...props}
                  type="date"
                  value={form.incident_date}
                  onChange={(e) => set('incident_date')(e.target.value)}
                />
              )}
            </Field>
            <Field label="Priority">
              {(props) => (
                <Select
                  {...props}
                  value={form.priority}
                  onChange={(e) => set('priority')(e.target.value)}
                >
                  {PRIORITIES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </fieldset>

          {create.isError && <ErrorNotice error={create.error} />}

          <div className="flex items-center justify-between gap-2 border-t border-[var(--border)] pt-4">
            <Link to="/">
              <Button type="button" variant="ghost">
                Cancel
              </Button>
            </Link>
            <Button type="submit" loading={create.isPending} icon={<ArrowRightIcon />}>
              {create.isPending ? 'Creating…' : 'Continue to address'}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
