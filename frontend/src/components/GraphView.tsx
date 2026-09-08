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

import type { ChainCode, GraphNode, GraphPayload } from '../api/types'
import { formatRaw, sharePercent, terminationLabel, truncateAddress } from '../lib/format'
import { AddressChip } from './AddressChip'
import { RiskBadge } from './RiskBadge'
import { TierBadge } from './TierBadge'
import {
  CrosshairIcon,
  MaximizeIcon,
  SearchIcon,
  XIcon,
  ZoomInIcon,
  ZoomOutIcon,
} from './icons'
import { Badge, Banner, IconButton, Meter } from './ui'

const TIER_BORDER_STYLE: Record<string, string> = {
  CONFIRMED: 'solid',
  PROBABLE: 'dashed',
  UNATTRIBUTED: 'dotted',
}

/** The canvas cannot read CSS classes, so the theme's tokens are read once per theme. */
function readPalette() {
  const css = getComputedStyle(document.documentElement)
  const get = (name: string) => css.getPropertyValue(name).trim()
  return {
    band: {
      LOW: get('--graph-low'),
      MEDIUM: get('--graph-medium'),
      HIGH: get('--graph-high'),
      CRITICAL: get('--graph-critical'),
    } as Record<string, string>,
    nodeBorder: get('--graph-node-border'),
    edge: get('--graph-edge'),
    edgeDim: get('--graph-edge-dim'),
    label: get('--graph-label'),
    accent: get('--accent'),
    bg: get('--graph-bg'),
  }
}

export interface GraphViewProps {
  graph: GraphPayload
  riskByAddress?: Record<string, { score: number; band: string }>
  selected: string | null
  onSelect: (address: string | null) => void
}

type Hover = { address: string; x: number; y: number } | null

export function GraphView({ graph, riskByAddress = {}, selected, onSelect }: GraphViewProps) {
  const host = useRef<HTMLDivElement>(null)
  const frame = useRef<HTMLDivElement>(null)
  const instance = useRef<cytoscape.Core | null>(null)
  const [canvasFailed, setCanvasFailed] = useState(false)
  const [hover, setHover] = useState<Hover>(null)
  const [filter, setFilter] = useState('')
  // Bumped when the theme attribute changes, so the canvas re-reads its palette.
  const [themeVersion, setThemeVersion] = useState(0)

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeVersion((v) => v + 1))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  const chain = (graph.asset_key?.split(':')[0] as ChainCode | undefined) ?? 'TRON'
  const decimals = graph.edges.find((edge) => edge.decimals !== null)?.decimals ?? null
  const symbol = graph.edges.find((edge) => edge.asset_symbol)?.asset_symbol ?? null
  const rootAmount = graph.nodes.find((node) => node.is_root)?.tainted_amount_raw ?? null

  const elements = useMemo(() => {
    const palette = readPalette()
    // Width is a visual weight only — never an amount path — so a float is acceptable here.
    const maxEdge = Math.max(1, ...graph.edges.map((edge) => Number(edge.tainted_amount_raw) || 0))
    const nodes = graph.nodes.map((node) => {
      const share = node.taint_share ?? 0
      const tier = node.attribution_tier ?? 'UNATTRIBUTED'
      return {
        data: {
          id: node.address,
          label: nodeLabel(node),
          depth: node.depth ?? 0,
          colour: palette.band[riskByAddress[node.address]?.band ?? 'LOW'] ?? palette.band.LOW,
          border: TIER_BORDER_STYLE[tier] ?? 'dotted',
          borderWidth: tier === 'UNATTRIBUTED' ? 1.5 : 3,
          borderColour: palette.nodeBorder,
          shape: node.is_root ? 'round-rectangle' : node.is_terminal ? 'round-hexagon' : 'ellipse',
          size: node.is_root ? 36 : 18 + Math.round(Math.min(1, Math.max(0, share)) * 18),
        },
      }
    })
    const edges = graph.edges.map((edge) => {
      const weight = Math.log1p(Number(edge.tainted_amount_raw) || 0) / Math.log1p(maxEdge)
      return {
        data: {
          id: `${edge.from}->${edge.to}`,
          source: edge.from,
          target: edge.to,
          label: edge.transfer_count > 1 ? `${edge.transfer_count}×` : '',
          width: 1 + weight * 3,
        },
      }
    })
    return { palette, list: [...nodes, ...edges] }
    // themeVersion is a deliberate dependency: it forces a palette re-read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, riskByAddress, themeVersion])

  useEffect(() => {
    if (!host.current) return
    const { palette, list } = elements
    let cy: cytoscape.Core
    try {
      cy = cytoscape({
        container: host.current,
        elements: list,
        style: ([
          {
            selector: 'node',
            style: {
              label: 'data(label)',
              'background-color': 'data(colour)',
              'border-color': 'data(borderColour)',
              'border-style': 'data(border)',
              'border-width': 'data(borderWidth)',
              shape: 'data(shape)',
              width: 'data(size)',
              height: 'data(size)',
              'font-family': 'JetBrains Mono Variable, JetBrains Mono, ui-monospace, monospace',
              'font-size': 9,
              'text-valign': 'bottom',
              'text-margin-y': 5,
              'text-wrap': 'ellipsis',
              'text-max-width': '120px',
              color: palette.label,
              'transition-property': 'opacity',
              'transition-duration': 120,
            },
          },
          {
            selector: 'node:selected',
            style: {
              'border-color': palette.accent,
              'border-width': 4,
              'overlay-color': palette.accent,
              'overlay-opacity': 0.12,
              'overlay-padding': 6,
            },
          },
          {
            selector: 'edge',
            style: {
              label: 'data(label)',
              width: 'data(width)',
              'line-color': palette.edge,
              'target-arrow-color': palette.edge,
              'target-arrow-shape': 'triangle',
              'curve-style': 'bezier',
              'arrow-scale': 0.8,
              'font-size': 8,
              color: palette.label,
              'text-background-color': palette.bg,
              'text-background-opacity': 1,
              'text-background-padding': '2px',
              'transition-property': 'opacity, line-color',
              'transition-duration': 120,
            },
          },
          { selector: '.dim', style: { opacity: 0.18 } },
          {
            selector: 'edge.path',
            style: { 'line-color': palette.accent, 'target-arrow-color': palette.accent, width: 3 },
          },
          { selector: 'node.path', style: { 'border-color': palette.accent } },
        ] as unknown) as cytoscape.StylesheetStyle[],
        layout: {
          name: 'breadthfirst',
          directed: true,
          roots: graph.root ? [graph.root] : undefined,
          spacingFactor: 1.15,
          padding: 28,
        },
        // Read-only: an investigator drags to look, never to edit the evidence.
        autoungrabify: true,
        minZoom: 0.2,
        maxZoom: 4,
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

    // Hover dims everything but the node's neighbourhood and shows the tooltip.
    cy.on('mouseover', 'node', (event) => {
      const node = event.target as cytoscape.NodeSingular
      const keep = node.closedNeighborhood()
      cy.elements().not(keep).addClass('dim')
      const pos = node.renderedPosition()
      setHover({ address: node.id(), x: pos.x, y: pos.y })
      if (host.current) host.current.style.cursor = 'pointer'
    })
    cy.on('mouseout', 'node', () => {
      cy.elements().removeClass('dim')
      setHover(null)
      if (host.current) host.current.style.cursor = ''
    })
    cy.on('pan zoom', () => setHover(null))

    instance.current = cy
    return () => {
      cy.destroy()
      instance.current = null
    }
  }, [elements, graph.root, onSelect])

  // Selection: mark the node and light the path back to the suspect.
  useEffect(() => {
    const cy = instance.current
    if (!cy) return
    cy.elements().removeClass('path')
    cy.nodes().unselect()
    if (!selected) return
    const node = cy.getElementById(selected)
    if (node.empty()) return
    node.select()
    node.predecessors().addClass('path')
  }, [selected])

  function zoom(factor: number) {
    const cy = instance.current
    if (!cy) return
    cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
  }
  function fit() {
    instance.current?.animate({ fit: { eles: instance.current.elements(), padding: 28 }, duration: 200 })
  }
  function centerRoot() {
    const cy = instance.current
    if (!cy || !graph.root) return
    const root = cy.getElementById(graph.root)
    if (root.empty()) return
    cy.animate({ center: { eles: root }, zoom: Math.max(cy.zoom(), 1.2), duration: 200 })
    onSelect(graph.root)
  }

  const selectedNode = selected ? graph.nodes.find((node) => node.address === selected) : undefined
  const hoverNode = hover ? graph.nodes.find((node) => node.address === hover.address) : undefined
  const query = filter.trim().toLowerCase()
  const listed = query
    ? graph.nodes.filter(
        (node) =>
          node.address.toLowerCase().includes(query) ||
          node.entity_name?.toLowerCase().includes(query),
      )
    : graph.nodes

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

      <div className={`grid gap-3 ${canvasFailed ? '' : 'lg:grid-cols-[minmax(0,1fr)_19rem]'}`}>
        <div ref={frame} hidden={canvasFailed} className="relative min-w-0">
          <div
            ref={host}
            role="img"
            aria-label={`Fund flow graph: ${graph.node_count} addresses, ${graph.edge_count} flows. The address list beside this graph carries the same information as text.`}
            className="h-[clamp(420px,60vh,720px)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--graph-bg)]"
          />

          <div className="absolute top-2 right-2 flex flex-col gap-1 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-1 shadow-[var(--shadow-sm)]">
            <IconButton label="Zoom in" size="sm" onClick={() => zoom(1.25)}>
              <ZoomInIcon />
            </IconButton>
            <IconButton label="Zoom out" size="sm" onClick={() => zoom(0.8)}>
              <ZoomOutIcon />
            </IconButton>
            <IconButton label="Fit to view" size="sm" onClick={fit}>
              <MaximizeIcon />
            </IconButton>
            <IconButton label="Centre on the suspect address" size="sm" onClick={centerRoot}>
              <CrosshairIcon />
            </IconButton>
          </div>

          <div className="absolute bottom-2 left-2 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)]/95 px-2.5 py-1.5 text-[0.6875rem] text-[var(--muted)] shadow-[var(--shadow-sm)] backdrop-blur">
            <Legend />
          </div>

          {hover && hoverNode && (
            <div
              role="tooltip"
              className="pointer-events-none absolute z-10 max-w-64 -translate-x-1/2 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-2.5 py-2 text-xs shadow-[var(--shadow-md)]"
              style={{ left: hover.x, top: hover.y + 22 }}
            >
              <p className="font-mono">{truncateAddress(hoverNode.address, 8, 8)}</p>
              {hoverNode.entity_name && (
                <p className="mt-0.5 font-medium">
                  {hoverNode.attribution_tier === 'PROBABLE' ? 'likely ' : ''}
                  {hoverNode.entity_name}
                </p>
              )}
              <p className="text-meta mt-0.5">
                hop {hoverNode.depth ?? 0}
                {formatRaw(hoverNode.tainted_amount_raw, decimals) &&
                  ` · ${formatRaw(hoverNode.tainted_amount_raw, decimals)} ${symbol ?? ''}`}
                {hoverNode.termination_reason && ` · ${terminationLabel(hoverNode.termination_reason)}`}
              </p>
            </div>
          )}
        </div>

        <aside className="flex min-w-0 flex-col gap-3">
          {selectedNode && (
            <NodeDetail
              node={selectedNode}
              chain={chain}
              decimals={decimals}
              symbol={symbol}
              rootAmount={rootAmount}
              risk={riskByAddress[selectedNode.address]}
              onClear={() => onSelect(null)}
            />
          )}

          <div className="flex min-h-0 flex-col rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)]">
            <h3 className="text-label px-3 pt-2.5 pb-1.5">Addresses in this trace</h3>
            <div className="border-b border-[var(--border)] px-2 pb-2">
              <label className="relative block">
                <span className="sr-only">Filter addresses</span>
                <SearchIcon className="pointer-events-none absolute top-1/2 left-2 h-3 w-3 -translate-y-1/2 text-[var(--muted)]" />
                <input
                  type="search"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Filter by address or entity"
                  className="h-7 w-full rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--bg)] pl-7 text-xs placeholder:text-[var(--muted)]/70 focus:border-[var(--accent)] focus:outline-none"
                />
              </label>
            </div>
            <ul className="max-h-[420px] overflow-y-auto p-1.5">
              {listed.map((node) => {
                const risk = riskByAddress[node.address]
                const active = node.address === selected
                return (
                  <li key={node.address}>
                    <button
                      type="button"
                      onClick={() => onSelect(active ? null : node.address)}
                      aria-pressed={active}
                      className={`transition-ui w-full rounded-[var(--radius-sm)] border px-2 py-1.5 text-left text-xs ${
                        active
                          ? 'border-[var(--accent)] bg-[var(--accent-soft)]'
                          : 'border-transparent hover:bg-[var(--surface-2)]'
                      }`}
                    >
                      <span className="flex items-center gap-2">
                        <span className="block flex-1 truncate font-mono">
                          {truncateAddress(node.address)}
                        </span>
                        {node.is_root && (
                          <Badge tone="accent" size="xs">
                            suspect
                          </Badge>
                        )}
                        {risk && (
                          <Badge band={risk.band as 'LOW'} size="xs">
                            {risk.band}
                          </Badge>
                        )}
                      </span>
                      <span className="text-meta mt-0.5 block truncate">
                        hop {node.depth ?? 0}
                        {node.entity_name && ` · ${node.entity_name}`}
                        {node.attribution_tier && ` · ${node.attribution_tier}`}
                        {risk && ` · risk ${risk.score}`}
                      </span>
                    </button>
                  </li>
                )
              })}
              {listed.length === 0 && (
                <li className="text-meta px-2 py-3 text-center">No address matches.</li>
              )}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  )
}

function NodeDetail({
  node,
  chain,
  decimals,
  symbol,
  rootAmount,
  risk,
  onClear,
}: {
  node: GraphNode
  chain: ChainCode
  decimals: number | null
  symbol: string | null
  rootAmount: string | null
  risk?: { score: number; band: string }
  onClear: () => void
}) {
  const amount = formatRaw(node.tainted_amount_raw, decimals)
  const share = rootAmount ? sharePercent(node.tainted_amount_raw, rootAmount) : null
  const stop = terminationLabel(node.termination_reason)
  return (
    <section
      aria-label="Selected address"
      className="fade-up rounded-[var(--radius-lg)] border border-[var(--accent)] bg-[var(--surface)] p-3 shadow-[var(--shadow-sm)]"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-label">Selected address</span>
        <IconButton label="Clear selection" size="sm" onClick={onClear}>
          <XIcon />
        </IconButton>
      </div>
      <div className="mt-1">
        <AddressChip address={node.address} chain={chain} size="md" />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {node.is_root && (
          <Badge tone="accent" size="xs">
            suspect address
          </Badge>
        )}
        {node.attribution_tier && (
          <TierBadge tier={node.attribution_tier} confidence={node.attribution_confidence} />
        )}
        {node.entity_name && (
          <span className="text-secondary font-semibold">
            {node.entity_name}
            {node.entity_type && (
              <span className="text-meta ml-1 font-normal uppercase">{node.entity_type}</span>
            )}
          </span>
        )}
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
        <div>
          <dt className="text-meta">Hop</dt>
          <dd className="text-num font-medium">{node.depth ?? 0}</dd>
        </div>
        <div>
          <dt className="text-meta">Attributed value</dt>
          <dd className="text-num font-medium">
            {amount ? `${amount} ${symbol ?? ''}` : `${node.tainted_amount_raw} raw`}
            {share !== null && <span className="text-meta ml-1">({share}%)</span>}
          </dd>
        </div>
        {risk && (
          <div className="col-span-2">
            <dt className="text-meta mb-1">Risk</dt>
            <dd className="flex items-center gap-2">
              <RiskBadge score={risk.score} band={risk.band as 'LOW'} />
              <Meter value={risk.score} band={risk.band as 'LOW'} className="flex-1" />
            </dd>
          </div>
        )}
        {stop && (
          <div className="col-span-2">
            <dt className="text-meta">Trace ended</dt>
            <dd className="font-medium">{stop}</dd>
          </div>
        )}
        {node.first_reached_at && (
          <div className="col-span-2">
            <dt className="text-meta">First reached</dt>
            <dd className="text-num">{new Date(node.first_reached_at).toLocaleString()}</dd>
          </div>
        )}
        {(node.omitted_successors > 0 || node.pruned_branches.length > 0) && (
          <div className="col-span-2">
            <dt className="text-meta">Not followed</dt>
            <dd>
              {node.pruned_branches.length > 0 && `${node.pruned_branches.length} pruned branch(es)`}
              {node.pruned_branches.length > 0 && node.omitted_successors > 0 && ' · '}
              {node.omitted_successors > 0 && `${node.omitted_successors} omitted from the picture`}
            </dd>
          </div>
        )}
      </dl>
    </section>
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
    <dl className="flex flex-wrap gap-x-4 gap-y-1">
      <div className="flex items-center gap-1.5">
        <dt className="font-medium">Border:</dt>
        <dd>solid = confirmed · dashed = likely · dotted = unattributed</dd>
      </div>
      <div className="flex items-center gap-1.5">
        <dt className="font-medium">Fill:</dt>
        <dd className="flex items-center gap-1.5">
          <Swatch colour="var(--graph-low)" /> low
          <Swatch colour="var(--graph-medium)" /> medium
          <Swatch colour="var(--graph-high)" /> high
          <Swatch colour="var(--graph-critical)" /> critical
        </dd>
      </div>
      <div className="flex items-center gap-1.5">
        <dt className="font-medium">Shape:</dt>
        <dd>square = suspect · hexagon = trace ended · size = attributed share</dd>
      </div>
    </dl>
  )
}

function Swatch({ colour }: { colour: string }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-2.5 w-2.5 rounded-full border border-[var(--graph-node-border)]/60"
      style={{ backgroundColor: colour }}
    />
  )
}
