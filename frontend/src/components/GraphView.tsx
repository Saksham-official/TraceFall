/**
 * The fund flow, drawn.
 *
 * Layout is breadth-first by hop depth, never force-directed: fund flow is inherently
 * layered by hop, and hop depth is the single most important thing to read off the
 * picture. A force-directed layout makes a prettier blob and hides that.
 *
 * **Colour carries risk; border style carries the attribution tier.** Colour is already
 * doing one job, and the tier distinction is too important to lose to colour-blindness or
 * a projector's rendering (NFR-18). Solid border is CONFIRMED, dashed is PROBABLE, faint
 * dotted is UNATTRIBUTED — and the node list beside the canvas says all of it in words.
 *
 * A canvas cannot be read by a screen reader, so the same nodes are listed as focusable
 * buttons next to it. That list is not a fallback — it is the accessible view, and it
 * selects the same node the canvas does.
 */

import cytoscape from 'cytoscape'
import { useEffect, useMemo, useRef, useState } from 'react'

import type { GraphNode, GraphPayload } from '../api/types'
import { truncateAddress } from '../lib/format'
import { Banner } from './ui'

const BAND_COLOUR: Record<string, string> = {
  LOW: '#cbd5e1',
  MEDIUM: '#fcd34d',
  HIGH: '#fb923c',
  CRITICAL: '#f87171',
}

const TIER_BORDER_STYLE: Record<string, string> = {
  CONFIRMED: 'solid',
  PROBABLE: 'dashed',
  UNATTRIBUTED: 'dotted',
}

export interface GraphViewProps {
  graph: GraphPayload
  riskByAddress?: Record<string, { score: number; band: string }>
  selected: string | null
  onSelect: (address: string | null) => void
}

export function GraphView({ graph, riskByAddress = {}, selected, onSelect }: GraphViewProps) {
  const host = useRef<HTMLDivElement>(null)
  const instance = useRef<cytoscape.Core | null>(null)
  const [canvasFailed, setCanvasFailed] = useState(false)

  const elements = useMemo(() => {
    const nodes = graph.nodes.map((node) => ({
      data: {
        id: node.address,
        label: nodeLabel(node),
        depth: node.depth ?? 0,
        colour: BAND_COLOUR[riskByAddress[node.address]?.band ?? 'LOW'] ?? BAND_COLOUR.LOW,
        border: TIER_BORDER_STYLE[node.attribution_tier ?? 'UNATTRIBUTED'] ?? 'dotted',
        borderWidth: node.attribution_tier === 'UNATTRIBUTED' || !node.attribution_tier ? 1 : 3,
        shape: node.is_root ? 'round-rectangle' : 'ellipse',
      },
    }))
    const edges = graph.edges.map((edge) => ({
      data: {
        id: `${edge.from}->${edge.to}`,
        source: edge.from,
        target: edge.to,
        label: edge.transfer_count > 1 ? `${edge.transfer_count}×` : '',
      },
    }))
    return [...nodes, ...edges]
  }, [graph, riskByAddress])

  useEffect(() => {
    if (!host.current) return
    let cy: cytoscape.Core
    try {
      cy = cytoscape({
        container: host.current,
        elements,
        style: ([
          {
            selector: 'node',
            style: {
              label: 'data(label)',
              'background-color': 'data(colour)',
              'border-color': '#0f172a',
              'border-style': 'data(border)',
              'border-width': 'data(borderWidth)',
              shape: 'data(shape)',
              'font-size': 9,
              'text-valign': 'bottom',
              'text-margin-y': 4,
              'text-wrap': 'wrap',
              'text-max-width': '110px',
              color: '#334155',
              width: 26,
              height: 26,
            },
          },
          {
            selector: 'node:selected',
            style: { 'border-color': '#1d4ed8', 'border-width': 4, 'overlay-opacity': 0.1 },
          },
          {
            selector: 'edge',
            style: {
              label: 'data(label)',
              width: 1.6,
              'line-color': '#94a3b8',
              'target-arrow-color': '#94a3b8',
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              'arrow-scale': 0.9,
              'font-size': 8,
              color: '#64748b',
            },
          },
        ] as unknown) as cytoscape.StylesheetStyle[],
        layout: { name: 'breadthfirst', directed: true, spacingFactor: 1.3, padding: 24 },
        // Read-only: an investigator drags to look, never to edit the evidence.
        autoungrabify: true,
        wheelSensitivity: 0.2,
      })
    } catch {
      // No canvas — an old browser, a hardened one, or a headless renderer. The address
      // list below carries the same information, so say what happened and show that
      // rather than failing the whole screen.
      setCanvasFailed(true)
      return
    }
    cy.on('select', 'node', (event) => onSelect(event.target.id() as string))
    cy.on('unselect', 'node', () => onSelect(null))
    instance.current = cy
    return () => {
      cy.destroy()
      instance.current = null
    }
  }, [elements, onSelect])

  useEffect(() => {
    const cy = instance.current
    if (!cy) return
    cy.nodes().unselect()
    if (selected) cy.getElementById(selected).select()
  }, [selected])

  return (
    <div className="space-y-3">
      {graph.truncated && (
        <Banner tone="warning" title="This graph is truncated">
          Showing {graph.node_count} of {graph.total_nodes} addresses. {graph.omitted_node_count}{' '}
          were not drawn — raise the node limit to see them. Nothing was removed from the
          analysis, only from this picture.
        </Banner>
      )}
      {graph.unavailable_addresses.length > 0 && (
        <Banner tone="warning" title="Part of the trail could not be retrieved">
          {graph.unavailable_addresses.length} address(es) were reached but their transactions
          could not be fetched, so what left them is unknown. This is a gap in the analysis, not
          a finding that the funds stopped there.
        </Banner>
      )}

      {canvasFailed && (
        <Banner tone="info" title="The graph could not be drawn here">
          This browser did not provide a drawing canvas. Every address and its details are
          listed below — nothing about the analysis is missing, only the picture.
        </Banner>
      )}

      <div className={`grid gap-3 ${canvasFailed ? '' : 'lg:grid-cols-[1fr_280px]'}`}>
        <div
          ref={host}
          hidden={canvasFailed}
          role="img"
          aria-label={`Fund flow graph: ${graph.node_count} addresses, ${graph.edge_count} flows. The address list beside this graph carries the same information as text.`}
          className="h-[420px] rounded border border-[var(--border)] bg-[var(--surface)]"
        />
        <div className="space-y-1">
          <h3 className="text-xs font-semibold tracking-wide text-[var(--muted)] uppercase">
            Addresses in this trace
          </h3>
          <ul className="max-h-[392px] space-y-1 overflow-y-auto pr-1">
            {graph.nodes.map((node) => {
              const risk = riskByAddress[node.address]
              const active = node.address === selected
              return (
                <li key={node.address}>
                  <button
                    type="button"
                    onClick={() => onSelect(active ? null : node.address)}
                    aria-pressed={active}
                    className={`w-full rounded border px-2 py-1.5 text-left text-xs ${
                      active
                        ? 'border-[var(--accent)] bg-[var(--surface-2)]'
                        : 'border-[var(--border)] bg-[var(--surface)]'
                    }`}
                  >
                    <span className="block font-mono">{truncateAddress(node.address)}</span>
                    <span className="block text-[var(--muted)]">
                      hop {node.depth ?? 0}
                      {node.is_root && ' · suspect'}
                      {node.entity_name && ` · ${node.entity_name}`}
                      {node.attribution_tier && ` · ${node.attribution_tier}`}
                      {risk && ` · risk ${risk.score} ${risk.band}`}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      </div>

      <Legend />
    </div>
  )
}

function nodeLabel(node: GraphNode): string {
  // A name alone would make a PROBABLE inference and a CONFIRMED fact read identically
  // on the canvas — the deposit address and the exchange it sweeps to carry the same
  // entity name. The word "likely" is what keeps them apart at a glance, and it is on
  // the label rather than only in the border style.
  if (!node.entity_name) return truncateAddress(node.address)
  if (node.attribution_tier === 'CONFIRMED') return node.entity_name
  if (node.attribution_tier === 'PROBABLE') return `likely ${node.entity_name}`
  return truncateAddress(node.address)
}

function Legend() {
  return (
    <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-[var(--muted)]">
      <div className="flex items-center gap-1.5">
        <dt className="font-medium">Border:</dt>
        <dd>solid = confirmed · dashed = likely · dotted = unattributed</dd>
      </div>
      <div className="flex items-center gap-1.5">
        <dt className="font-medium">Fill:</dt>
        <dd>risk band — grey low, amber medium, orange high, red critical</dd>
      </div>
      <div className="flex items-center gap-1.5">
        <dt className="font-medium">Square:</dt>
        <dd>the suspect address</dd>
      </div>
    </dl>
  )
}
