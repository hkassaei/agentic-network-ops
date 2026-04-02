// =============================================================================
// topology.js — D3.js topology renderer (single source of truth)
// =============================================================================
// Used by: topology page, flows page, dashboard
// Requires: d3.v7, common.js

const TOPO_SVG_W = 1200;
const TOPO_SVG_H = 420;
const TOPO_ROWS = 5;
const TOPO_SLOTS = 12;
const NODE_W = 72;
const NODE_H = 34;

const SBI_BUS_NFS = ['nrf','scp','ausf','udm','udr','amf','smf','pcf','nssf','bsf'];

const LAYER_COLORS = {
  core: '#4f8ff7', ims: '#26c6da', ran: '#ab47bc', ue: '#4caf50',
  data: '#8b90a5', infrastructure: '#8b90a5', observability: '#ff9800'
};

const PLANE_STYLES = {
  control:    { stroke: '#4f8ff7', dash: '',      width: 1.5 },
  data:       { stroke: '#4caf50', dash: '6,3',   width: 1.5 },
  signaling:  { stroke: '#26c6da', dash: '2,3',   width: 1.5 },
  management: { stroke: '#8b90a5', dash: '',       width: 1 },
};

// Shared state
let lastTopology = null;
let lastMetrics = {};

function gridToSvg(row, slot) {
  const x = (slot + 0.5) / TOPO_SLOTS * TOPO_SVG_W;
  const y = (row + 0.5) / TOPO_ROWS * TOPO_SVG_H;
  return { x, y };
}

// =============================================================================
// Main render function
// =============================================================================

/**
 * Render the network topology into an SVG element.
 *
 * @param {string} svgSelector - CSS selector for the SVG element (e.g. '#topo-svg')
 * @param {object} topo - Topology data from /api/topology
 * @param {object} opts - Options:
 *   - metrics: boolean — show metric badges below nodes (default true)
 *   - onNodeClick: function(nodeId) — click handler for nodes
 *   - onEdgeClick: function(edge) — click handler for edges
 *   - tooltipId: string — ID of tooltip element (default 'topo-tooltip')
 */
function renderTopology(svgSelector, topo, opts = {}) {
  const showMetrics = opts.metrics !== false;
  const onNodeClick = opts.onNodeClick || function() {};
  const onEdgeClick = opts.onEdgeClick || function() {};
  const tooltipId = opts.tooltipId || 'topo-tooltip';

  const svg = d3.select(svgSelector);
  svg.selectAll('*').remove();
  svg.attr('viewBox', `0 0 ${TOPO_SVG_W} ${TOPO_SVG_H}`);

  // Build node position map
  const nodeMap = {};
  for (const n of topo.nodes) {
    const pos = gridToSvg(n.row, n.slot);
    nodeMap[n.id] = { ...n, cx: pos.x, cy: pos.y };
  }

  // --- SBI Bus ---
  const sbiNodes = SBI_BUS_NFS.filter(id => nodeMap[id]);
  if (sbiNodes.length >= 2) {
    const busY = gridToSvg(1, 0).y;
    const xs = sbiNodes.map(id => nodeMap[id].cx).sort((a, b) => a - b);
    const busX1 = xs[0] - 20;
    const busX2 = xs[xs.length - 1] + 20;
    const busLineY = busY - NODE_H / 2 - 14;

    const sbiEdgeInfo = { label: 'SBI Service Bus', protocol: 'HTTP/2', interface: 'SBI', plane: 'control', source: 'NRF/SCP', target: 'All Core NFs', active: true };

    const busG = svg.append('g').attr('class', 'topo-edge topo-edge-group');
    busG.append('line').attr('x1', busX1).attr('y1', busLineY).attr('x2', busX2).attr('y2', busLineY)
      .attr('stroke', 'transparent').attr('stroke-width', 14).style('pointer-events', 'stroke');
    busG.append('line').attr('x1', busX1).attr('y1', busLineY).attr('x2', busX2).attr('y2', busLineY)
      .attr('stroke', '#4f8ff7').attr('stroke-width', 2.5).attr('opacity', 0.5).style('pointer-events', 'none');
    busG.append('text').attr('x', (busX1 + busX2) / 2).attr('y', busLineY - 6)
      .attr('text-anchor', 'middle').attr('fill', '#4f8ff7').attr('font-size', 10).attr('opacity', 0.7)
      .style('pointer-events', 'none').text('SBI Service Bus');
    busG.on('mouseenter', (ev) => _showEdgeTooltip(ev, sbiEdgeInfo, tooltipId)).on('mouseleave', () => _hideTooltip(tooltipId));

    for (const id of sbiNodes) {
      const n = nodeMap[id];
      const stubG = svg.append('g').attr('class', 'topo-edge topo-edge-group');
      stubG.append('line').attr('x1', n.cx).attr('y1', n.cy - NODE_H / 2).attr('x2', n.cx).attr('y2', busLineY)
        .attr('stroke', 'transparent').attr('stroke-width', 14).style('pointer-events', 'stroke');
      stubG.append('line').attr('x1', n.cx).attr('y1', n.cy - NODE_H / 2).attr('x2', n.cx).attr('y2', busLineY)
        .attr('stroke', '#4f8ff7').attr('stroke-width', 1.5).attr('opacity', n.status === 'running' ? 0.5 : 0.15)
        .style('pointer-events', 'none');
      const stubInfo = { label: `SBI (${n.label})`, protocol: 'HTTP/2', interface: 'SBI', plane: 'control', source: id, target: 'NRF/SCP', active: n.status === 'running' };
      stubG.on('mouseenter', (ev) => _showEdgeTooltip(ev, stubInfo, tooltipId)).on('mouseleave', () => _hideTooltip(tooltipId));
    }
  }

  // --- Edges (non-SBI) ---
  for (const e of topo.edges) {
    if (e.protocol === 'SBI') continue;
    const src = nodeMap[e.source];
    const tgt = nodeMap[e.target];
    if (!src || !tgt) continue;

    const style = PLANE_STYLES[e.plane] || PLANE_STYLES.control;
    const g = svg.append('g').attr('class', `topo-edge topo-edge-group${e.active ? '' : ' edge-inactive'}`);

    if (e.logical) {
      const dx = tgt.cx - src.cx, dy = tgt.cy - src.cy;
      const d = `M ${src.cx} ${src.cy} C ${src.cx + dx*0.2-40} ${src.cy + dy*0.3}, ${tgt.cx - dx*0.2-40} ${tgt.cy - dy*0.3}, ${tgt.cx} ${tgt.cy}`;
      g.append('path').attr('d', d).attr('fill', 'none').attr('stroke', 'transparent').attr('stroke-width', 14).style('pointer-events', 'stroke');
      g.append('path').attr('d', d).attr('fill', 'none').attr('stroke', style.stroke).attr('stroke-width', 1)
        .attr('stroke-dasharray', '4,4').attr('opacity', e.active ? 0.35 : 0.1).style('pointer-events', 'none');
    } else {
      g.append('line').attr('x1', src.cx).attr('y1', src.cy).attr('x2', tgt.cx).attr('y2', tgt.cy)
        .attr('stroke', 'transparent').attr('stroke-width', 14).style('pointer-events', 'stroke');
      g.append('line').attr('x1', src.cx).attr('y1', src.cy).attr('x2', tgt.cx).attr('y2', tgt.cy)
        .attr('stroke', style.stroke).attr('stroke-width', style.width)
        .attr('stroke-dasharray', style.dash || null).attr('opacity', e.active ? 0.6 : 0.15)
        .style('pointer-events', 'none');
    }
    g.on('mouseenter', (ev) => _showEdgeTooltip(ev, e, tooltipId)).on('mouseleave', () => _hideTooltip(tooltipId))
     .on('click', (ev) => { ev.stopPropagation(); onEdgeClick(e); });
  }

  // --- Nodes ---
  for (const n of topo.nodes) {
    const nm = nodeMap[n.id];
    const x = nm.cx - NODE_W / 2, y = nm.cy - NODE_H / 2;
    const g = svg.append('g').attr('class', `topo-node${n.status !== 'running' ? ' node-down' : ''}`)
      .attr('data-node-id', n.id);

    g.append('rect').attr('x', x).attr('y', y).attr('width', NODE_W).attr('height', NODE_H).attr('rx', 6)
      .attr('fill', n.status === 'running' ? '#21262d' : '#1a1d27')
      .attr('stroke', LAYER_COLORS[n.layer] || '#8b90a5').attr('stroke-width', 1.5);

    g.append('circle').attr('cx', x + 10).attr('cy', y + 10).attr('r', 4)
      .attr('fill', n.health === 'healthy' ? '#4caf50' : '#ef5350').attr('class', 'status-dot');

    g.append('text').attr('x', nm.cx).attr('y', n.sublabel ? nm.cy - 1 : nm.cy + 4)
      .attr('text-anchor', 'middle').attr('fill', '#c9d1d9').attr('font-size', 11)
      .text(n.label);

    if (n.sublabel) {
      g.append('text').attr('x', nm.cx).attr('y', nm.cy + 12)
        .attr('text-anchor', 'middle').attr('fill', '#8b949e').attr('font-size', 9)
        .text(n.sublabel);
    }

    // Metric badge
    if (showMetrics) {
      const nodeMetrics = lastMetrics[n.id];
      if (nodeMetrics && nodeMetrics.badge) {
        g.append('text').attr('x', nm.cx).attr('y', y + NODE_H + 12)
          .attr('text-anchor', 'middle').attr('class', 'topo-badge')
          .text(nodeMetrics.badge);
      }
    }

    g.on('mouseenter', (ev) => _showNodeTooltip(ev, n, tooltipId))
     .on('mouseleave', () => _hideTooltip(tooltipId))
     .on('click', () => onNodeClick(n.id));
  }

  // Add flow overlay layer for flows page
  svg.append('g').attr('class', 'flow-layer');

  return nodeMap;
}

// =============================================================================
// Tooltip functions
// =============================================================================

function _showNodeTooltip(ev, node, tooltipId) {
  const tt = document.getElementById(tooltipId);
  if (!tt) return;
  const statusColor = node.health === 'healthy' ? 'var(--green)' : 'var(--red)';
  const m = lastMetrics[node.id];

  let metricsHtml = '';
  if (m && m.badge) {
    metricsHtml += `<div style="margin-top:4px;color:var(--accent);font-weight:600">${escapeHtml(m.badge)}</div>`;
  }
  if (m && m.metrics) {
    const entries = Object.entries(m.metrics).filter(([k]) => !k.startsWith('_')).slice(0, 5);
    metricsHtml += entries.map(([k, v]) => {
      const name = formatMetricName(k);
      const val = typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : v;
      return `<div class="tt-dim">${escapeHtml(name)}: ${val}</div>`;
    }).join('');
  }

  tt.innerHTML = `
    <div class="tt-label">${escapeHtml(node.label)}</div>
    <div class="tt-dim">Container: ${escapeHtml(node.id)}</div>
    <div>Status: <span style="color:${statusColor}">${escapeHtml(node.status)}</span></div>
    ${node.ip ? `<div class="tt-dim">IP: ${escapeHtml(node.ip)}</div>` : ''}
    <div class="tt-dim">Protocols: ${escapeHtml(node.protocols.join(', '))}</div>
    <div class="tt-dim">Role: ${escapeHtml(node.role)}</div>
    ${metricsHtml}
  `;
  _positionTooltip(ev, tt);
}

function _showEdgeTooltip(ev, edge, tooltipId) {
  const tt = document.getElementById(tooltipId);
  if (!tt) return;

  tt.innerHTML = `
    <div class="tt-label">${escapeHtml(edge.label)}</div>
    <div class="tt-dim">Protocol: ${escapeHtml(edge.protocol)}</div>
    ${edge.interface ? `<div class="tt-dim">Interface: ${escapeHtml(edge.interface)}</div>` : ''}
    <div class="tt-dim">Plane: ${escapeHtml(edge.plane)}</div>
    <div class="tt-dim">${escapeHtml(edge.source)} ↔ ${escapeHtml(edge.target)}</div>
    <div>${edge.active ? '<span style="color:var(--green)">Active</span>' : '<span style="color:var(--red)">Inactive</span>'}</div>
  `;
  _positionTooltip(ev, tt);
}

function _positionTooltip(ev, tt) {
  tt.style.display = 'block';
  const rect = tt.parentElement.getBoundingClientRect();
  let x = ev.clientX - rect.left + 12;
  let y = ev.clientY - rect.top + 12;
  if (x + 200 > rect.width) x = ev.clientX - rect.left - 200;
  if (y + 100 > rect.height) y = ev.clientY - rect.top - 100;
  tt.style.left = x + 'px';
  tt.style.top = y + 'px';
}

function _hideTooltip(tooltipId) {
  const tt = document.getElementById(tooltipId);
  if (tt) tt.style.display = 'none';
}

// =============================================================================
// Polling
// =============================================================================

async function pollTopology(svgSelector, opts) {
  try {
    const res = await fetch(`${API_BASE}/topology`);
    const data = await res.json();
    lastTopology = data;
    renderTopology(svgSelector, data, opts);
  } catch (e) { /* Silently skip */ }
}

async function pollMetrics() {
  try {
    const res = await fetch(`${API_BASE}/metrics`);
    lastMetrics = await res.json();
  } catch (e) { /* Silently skip */ }
}
