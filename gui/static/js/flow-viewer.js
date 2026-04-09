// =============================================================================
// flow-viewer.js — Protocol flow animation and step-through
// =============================================================================
// Used by: flows page
// Requires: common.js, topology.js, d3.v7

// --- State ---
let topoData = null;
let allFlows = [];
let currentFlow = null;
let currentStepIdx = -1;
let playing = false;
let playTimer = null;
let onDotArrived = null;
let viewMode = 'topology';  // 'topology' | 'sequence' | 'focused'

// Cached container dimensions — set once on init and resize.
// Prevents layout reflows from repeatedly reading clientWidth/clientHeight.
let _topoW = 0, _topoH = 0;
function _cacheTopoSize() {
  const c = document.getElementById('topo-container');
  if (c) { _topoW = c.clientWidth; _topoH = c.clientHeight; }
}

// =============================================================================
// View Mode
// =============================================================================
let _lastRenderedBase = null; // tracks what's currently in the SVG: 'topology' or 'sequence'

function setViewMode(mode) {
  const prevMode = viewMode;
  viewMode = mode;
  document.querySelectorAll('.vt-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === mode);
  });

  // Only re-render the base topology SVG when switching FROM sequence mode
  // (which replaced the SVG contents) TO topology/focused mode.
  const needsBase = (mode === 'topology' || mode === 'focused');
  if (needsBase && _lastRenderedBase !== 'topology') {
    renderFlowTopology();
    _lastRenderedBase = 'topology';
  }

  if (mode === 'sequence') {
    renderSequenceDiagram();
    _lastRenderedBase = 'sequence';
  } else {
    highlightForCurrentMode();
  }
}

function renderForCurrentMode() {
  // Full re-render — used by resize and init only
  if (viewMode === 'sequence') {
    renderSequenceDiagram();
    _lastRenderedBase = 'sequence';
  } else {
    renderFlowTopology();
    _lastRenderedBase = 'topology';
    highlightForCurrentMode();
  }
}

function highlightForCurrentMode() {
  if (viewMode === 'sequence') {
    renderSequenceDiagram();
  } else if (viewMode === 'focused') {
    highlightFlowFocused();
  } else {
    highlightFlow();
  }
}

// =============================================================================
// Initialization
// =============================================================================
async function initFlowViewer() {
  const [topoResp, flowsResp] = await Promise.all([
    fetch(`${API_BASE}/topology`),
    fetch(`${API_BASE}/flows`),
  ]);
  topoData = await topoResp.json();
  allFlows = await flowsResp.json();

  renderFlowList();
  _cacheTopoSize();
  renderFlowTopology();
  _lastRenderedBase = 'topology';
}

// =============================================================================
// Flow List (sidebar)
// =============================================================================
function renderFlowList() {
  const container = document.getElementById('flow-list');
  container.innerHTML = '';
  allFlows.forEach(f => {
    const card = document.createElement('div');
    card.className = 'flow-card';
    card.innerHTML = `
      <h3>${f.name}</h3>
      <p>${(f.description || '').substring(0, 100)}...</p>
      <span class="badge">${f.step_count} steps</span>
    `;
    card.onclick = () => selectFlow(f.id);
    container.appendChild(card);
  });
}

async function selectFlow(flowId) {
  const resp = await fetch(`${API_BASE}/flows/${flowId}`);
  currentFlow = await resp.json();
  currentStepIdx = -1;
  playing = false;

  // Update sidebar
  document.querySelectorAll('.flow-card').forEach(c => c.classList.remove('active'));
  const cards = document.querySelectorAll('.flow-card');
  const idx = allFlows.findIndex(f => f.id === flowId);
  if (idx >= 0 && cards[idx]) cards[idx].classList.add('active');

  renderStepList();
  document.getElementById('controls').style.display = 'flex';
  document.getElementById('step-list').style.display = 'block';
  updateStepCounter();
  updateDetailPanel();
  // Sequence mode needs a full re-render (different SVG layout per flow).
  // Topology/focused just need to re-highlight on the existing SVG.
  if (viewMode === 'sequence') {
    renderSequenceDiagram();
  } else {
    highlightForCurrentMode();
  }
}

function renderStepList() {
  const container = document.getElementById('step-items');
  container.innerHTML = '';
  if (!currentFlow || !currentFlow.steps) return;

  currentFlow.steps.forEach((step, i) => {
    const item = document.createElement('div');
    item.className = 'step-item' + (i === currentStepIdx ? ' active' : i < currentStepIdx ? ' completed' : ' future');
    item.innerHTML = `
      <div class="step-num">${step.step_order}</div>
      <div class="step-info">
        <div class="step-label">${step.label}</div>
        <div class="step-proto">${step.protocol} / ${step.interface || '—'}</div>
      </div>
    `;
    item.onclick = () => goToStep(i);
    container.appendChild(item);
  });
}

// =============================================================================
// Playback Controls
// =============================================================================
function togglePlay() {
  if (playing) {
    playing = false;
    clearTimeout(playTimer);
    onDotArrived = null;
    d3.select('#topo-svg').selectAll('.flow-dot').interrupt();
    document.getElementById('btn-play').textContent = '▶ Play';
  } else {
    playing = true;
    document.getElementById('btn-play').textContent = '⏸ Pause';
    if (currentStepIdx < 0) currentStepIdx = 0;
    updateAll();
    scheduleNextStep();
  }
}

function scheduleNextStep() {
  if (!playing || !currentFlow) return;

  onDotArrived = function() {
    onDotArrived = null;
    if (!playing) return;
    playTimer = setTimeout(() => {
      if (!playing) return;
      if (currentStepIdx < currentFlow.steps.length - 1) {
        currentStepIdx++;
        updateAll();
        scheduleNextStep();
      } else {
        playing = false;
        document.getElementById('btn-play').textContent = '▶ Play';
      }
    }, 500);
  };
}

function stepNext() {
  if (!currentFlow) return;
  if (currentStepIdx < currentFlow.steps.length - 1) {
    currentStepIdx++;
    updateAll();
  }
}

function stepPrev() {
  if (!currentFlow) return;
  if (currentStepIdx > 0) {
    currentStepIdx--;
    updateAll();
  }
}

function goToStep(idx) {
  currentStepIdx = idx;
  if (playing) togglePlay();
  updateAll();
}

function updateAll() {
  renderStepList();
  updateStepCounter();
  updateDetailPanel();
  highlightForCurrentMode();
}

function updateStepCounter() {
  const total = currentFlow ? currentFlow.steps.length : 0;
  const current = currentStepIdx >= 0 ? currentStepIdx + 1 : 0;
  document.getElementById('step-counter').textContent = `Step ${current} / ${total}`;
}

// =============================================================================
// Detail Panel
// =============================================================================
function updateDetailPanel() {
  if (!currentFlow || currentStepIdx < 0) {
    document.getElementById('detail-title').textContent = currentFlow ? currentFlow.name : 'Select a flow';
    document.getElementById('detail-desc').textContent = currentFlow ? currentFlow.description : '';
    document.getElementById('detail-sections').innerHTML = '';
    return;
  }

  const step = currentFlow.steps[currentStepIdx];
  document.getElementById('detail-title').textContent =
    `Step ${step.step_order}: ${step.label}`;
  document.getElementById('detail-desc').textContent = step.description;

  let sections = '';

  if (step.detail) {
    sections += `<div class="detail-section"><h4>How it works</h4><p style="color:#c9d1d9;font-size:12px;line-height:1.6;">${step.detail.replace(/\n/g, '<br>')}</p></div>`;
  }

  const failures = step.failure_modes || [];
  if (failures.length > 0) {
    sections += `<div class="detail-section"><h4>What can go wrong</h4><ul>${failures.map(f => `<li>${f}</li>`).join('')}</ul></div>`;
  }

  const metrics = step.metrics_to_watch || [];
  if (metrics.length > 0) {
    sections += `<div class="detail-section"><h4>Metrics to watch</h4><ul>${metrics.map(m => `<li class="metric">${m}</li>`).join('')}</ul></div>`;
  }

  document.getElementById('detail-sections').innerHTML = sections;
}

// =============================================================================
// D3.js Flow Topology (simplified rendering for flows page)
// =============================================================================
function renderFlowTopology() {
  if (!topoData || !topoData.nodes) return;

  const svg = d3.select('#topo-svg');
  svg.selectAll('*').remove();

  const width = _topoW;
  const height = _topoH;

  svg.attr('viewBox', `0 0 ${width} ${height}`);

  const rows = 5, slots = 12;
  const nodeMap = {};

  topoData.nodes.forEach(n => {
    const x = (n.slot + 0.5) / slots * width;
    const y = (n.row + 0.5) / rows * height;
    nodeMap[n.id] = { ...n, x, y };
  });

  // Draw edges
  const edgeGroup = svg.append('g').attr('class', 'edges');
  topoData.edges.forEach(e => {
    if (e.logical) return;
    const src = nodeMap[e.source];
    const tgt = nodeMap[e.target];
    if (!src || !tgt) return;

    const color = e.active ? (LAYER_COLORS[src.layer] || '#8b90a5') : '#30363d';
    const opacity = e.active ? 0.4 : 0.15;

    edgeGroup.append('line')
      .attr('class', 'edge')
      .attr('data-source', e.source)
      .attr('data-target', e.target)
      .attr('data-protocol', e.protocol)
      .attr('x1', src.x).attr('y1', src.y)
      .attr('x2', tgt.x).attr('y2', tgt.y)
      .attr('stroke', color)
      .attr('stroke-opacity', opacity)
      .attr('stroke-dasharray', e.plane === 'data' ? '6,3' : e.plane === 'signaling' ? '3,3' : '');
  });

  // Draw nodes
  const nodeGroup = svg.append('g').attr('class', 'nodes');
  topoData.nodes.forEach(n => {
    const pos = nodeMap[n.id];
    if (!pos) return;

    const g = nodeGroup.append('g')
      .attr('class', 'node')
      .attr('data-id', n.id)
      .attr('transform', `translate(${pos.x - NODE_W/2}, ${pos.y - NODE_H/2})`);

    const borderColor = n.status === 'running'
      ? (LAYER_COLORS[n.layer] || '#8b90a5')
      : '#f85149';

    g.append('rect')
      .attr('width', NODE_W).attr('height', NODE_H)
      .attr('fill', '#21262d')
      .attr('stroke', borderColor)
      .attr('stroke-width', 1.5);

    g.append('text')
      .attr('x', NODE_W/2).attr('y', NODE_H/2 + 4)
      .text(n.label)
      .attr('fill', '#c9d1d9')
      .attr('font-size', '11px')
      .attr('text-anchor', 'middle');
  });

  // Flow animation layer (on top)
  svg.append('g').attr('class', 'flow-layer');
}

// =============================================================================
// Flow Highlighting + Dot Animation
// =============================================================================
function highlightFlow() {
  if (!topoData || !currentFlow) return;

  const svg = d3.select('#topo-svg');
  const flowLayer = svg.select('.flow-layer');
  flowLayer.selectAll('*').remove();

  // Reset all edges and nodes to dim
  svg.selectAll('.edge').attr('stroke-opacity', 0.15).attr('stroke-width', 1);
  svg.selectAll('.node rect').attr('stroke-width', 1.5).attr('fill', '#21262d');

  if (currentStepIdx < 0) return;

  const width = _topoW;
  const height = _topoH;
  const rows = 5, slots = 12;
  const halfW = NODE_W / 2, halfH = NODE_H / 2;

  function edgePoint(center, toward) {
    const dx = toward.x - center.x;
    const dy = toward.y - center.y;
    if (dx === 0 && dy === 0) return { x: center.x, y: center.y };
    const scaleX = halfW / Math.abs(dx || 0.001);
    const scaleY = halfH / Math.abs(dy || 0.001);
    const scale = Math.min(scaleX, scaleY);
    return { x: center.x + dx * scale, y: center.y + dy * scale };
  }

  function getPos(id) {
    const n = topoData.nodes.find(n => n.id === id);
    if (!n) return null;
    return {
      x: (n.slot + 0.5) / slots * width,
      y: (n.row + 0.5) / rows * height,
    };
  }

  // Highlight all steps up to current
  for (let i = 0; i <= currentStepIdx; i++) {
    const step = currentFlow.steps[i];
    const isCurrent = i === currentStepIdx;
    const color = isCurrent ? '#58a6ff' : '#238636';
    const opacity = isCurrent ? 1.0 : 0.5;

    const pathNodes = [step.from_component];
    if (step.via) pathNodes.push(...step.via);
    pathNodes.push(step.to_component);

    // Draw path segments
    for (let j = 0; j < pathNodes.length - 1; j++) {
      const fromCenter = getPos(pathNodes[j]);
      const toCenter = getPos(pathNodes[j + 1]);
      if (!fromCenter || !toCenter) continue;

      const from = edgePoint(fromCenter, toCenter);
      const to = edgePoint(toCenter, fromCenter);

      flowLayer.append('line')
        .attr('x1', from.x).attr('y1', from.y)
        .attr('x2', to.x).attr('y2', to.y)
        .attr('stroke', color)
        .attr('stroke-width', isCurrent ? 3 : 2)
        .attr('stroke-opacity', opacity);
    }

    // Animate dot on current step
    if (isCurrent && pathNodes.length >= 2) {
      const centers = pathNodes.map(id => getPos(id)).filter(p => p !== null);
      const waypoints = [];
      if (centers.length >= 2) {
        waypoints.push(edgePoint(centers[0], centers[1]));
        for (let w = 1; w < centers.length - 1; w++) {
          waypoints.push(centers[w]);
        }
        waypoints.push(edgePoint(centers[centers.length - 1], centers[centers.length - 2]));
      }
      if (waypoints.length >= 2) {
        const dot = flowLayer.append('circle')
          .attr('class', 'flow-dot')
          .attr('r', 5)
          .attr('cx', waypoints[0].x).attr('cy', waypoints[0].y);

        const PIXELS_PER_MS = 0.15;
        const segDurations = [];
        for (let w = 1; w < waypoints.length; w++) {
          const dx = waypoints[w].x - waypoints[w-1].x;
          const dy = waypoints[w].y - waypoints[w-1].y;
          segDurations.push(Math.sqrt(dx*dx + dy*dy) / PIXELS_PER_MS);
        }
        const savedStepIdx = i;
        const isLastStep = i === currentFlow.steps.length - 1;

        function animateForward() {
          let t = dot;
          for (let w = 1; w < waypoints.length; w++) {
            t = t.transition()
              .duration(segDurations[w - 1])
              .ease(d3.easeLinear)
              .attr('cx', waypoints[w].x).attr('cy', waypoints[w].y);
          }
          t.on('end', function() {
            if (onDotArrived) onDotArrived();
            if (isLastStep || playing) return;
            animateBackward();
          });
        }

        function animateBackward() {
          let t = d3.select(dot.node());
          for (let w = waypoints.length - 2; w >= 0; w--) {
            t = t.transition()
              .duration(segDurations[w])
              .ease(d3.easeLinear)
              .attr('cx', waypoints[w].x).attr('cy', waypoints[w].y);
          }
          t.on('end', function() {
            if (currentStepIdx === savedStepIdx) animateForward();
          });
        }

        animateForward();
      }
    }

    // Highlight involved nodes
    pathNodes.forEach(nid => {
      svg.selectAll(`.node[data-id="${nid}"] rect`)
        .attr('fill', isCurrent ? '#1f2937' : '#161b22')
        .attr('stroke-width', isCurrent ? 3 : 2);
    });
  }
}

// =============================================================================
// Sequence Diagram Renderer
// =============================================================================
function renderSequenceDiagram() {
  if (!topoData || !currentFlow) {
    renderFlowTopology();
    return;
  }

  const svg = d3.select('#topo-svg');
  svg.selectAll('*').remove();

  const width = _topoW;
  const height = _topoH;
  svg.attr('viewBox', `0 0 ${width} ${height}`);

  // Extract participating NFs in first-appearance order
  const ordered = [];
  const seen = new Set();
  currentFlow.steps.forEach(step => {
    [step.from_component, ...(step.via || []), step.to_component].forEach(id => {
      if (!seen.has(id)) { ordered.push(id); seen.add(id); }
    });
  });

  // Layout constants
  const MARGIN_X = 80;
  const HEADER_Y = 30;
  const HEADER_H = NODE_H;
  const LIFELINE_TOP = HEADER_Y + HEADER_H + 8;
  const colCount = ordered.length;
  const colSpacing = colCount > 1 ? (width - 2 * MARGIN_X) / (colCount - 1) : 0;
  const colX = ordered.map((_, i) => MARGIN_X + i * colSpacing);

  const totalSteps = currentFlow.steps.length;
  const availableH = height - LIFELINE_TOP - 20;
  const ROW_SPACING = Math.min(45, availableH / (totalSteps + 1));

  function rowY(stepIdx) { return LIFELINE_TOP + (stepIdx + 1) * ROW_SPACING; }

  // Build node lookup for layer colors
  const nodeInfo = {};
  topoData.nodes.forEach(n => { nodeInfo[n.id] = n; });

  // --- Arrowhead markers ---
  const defs = svg.append('defs');
  [['arrow-blue', '#58a6ff'], ['arrow-green', '#238636'], ['arrow-dim', '#30363d']].forEach(([id, color]) => {
    defs.append('marker').attr('id', id)
      .attr('viewBox', '0 0 10 10').attr('refX', 9).attr('refY', 5)
      .attr('markerWidth', 6).attr('markerHeight', 6).attr('orient', 'auto')
      .append('path').attr('d', 'M 0 0 L 10 5 L 0 10 z').attr('fill', color);
  });

  // --- Column headers ---
  const headerG = svg.append('g').attr('class', 'seq-header');
  ordered.forEach((id, i) => {
    const x = colX[i];
    const info = nodeInfo[id];
    const borderColor = info ? (LAYER_COLORS[info.layer] || '#8b90a5') : '#8b90a5';

    headerG.append('rect')
      .attr('x', x - NODE_W / 2).attr('y', HEADER_Y)
      .attr('width', NODE_W).attr('height', HEADER_H)
      .attr('fill', '#21262d').attr('stroke', borderColor).attr('stroke-width', 1.5);

    headerG.append('text')
      .attr('x', x).attr('y', HEADER_Y + HEADER_H / 2 + 4)
      .text(info ? info.label : id);
  });

  // --- Lifelines ---
  const lifelineG = svg.append('g');
  const lastRowY = rowY(totalSteps - 1) + 15;
  ordered.forEach((_, i) => {
    lifelineG.append('line').attr('class', 'seq-lifeline')
      .attr('x1', colX[i]).attr('y1', LIFELINE_TOP)
      .attr('x2', colX[i]).attr('y2', Math.max(lastRowY, LIFELINE_TOP + 40));
  });

  // --- Step arrows ---
  const arrowG = svg.append('g');
  const flowLayer = svg.append('g').attr('class', 'flow-layer');

  currentFlow.steps.forEach((step, i) => {
    const y = rowY(i);
    const fromIdx = ordered.indexOf(step.from_component);
    const toIdx = ordered.indexOf(step.to_component);
    if (fromIdx < 0 || toIdx < 0) return;

    const fromX = colX[fromIdx];
    const toX = colX[toIdx];

    // Determine style based on step state
    let color, markerRef, strokeW, opacity, labelFill;
    if (i === currentStepIdx) {
      color = '#58a6ff'; markerRef = 'url(#arrow-blue)'; strokeW = 2.5; opacity = 1; labelFill = '#c9d1d9';
    } else if (i < currentStepIdx) {
      color = '#238636'; markerRef = 'url(#arrow-green)'; strokeW = 1.5; opacity = 0.5; labelFill = '#8b90a5';
    } else {
      color = '#30363d'; markerRef = 'url(#arrow-dim)'; strokeW = 1; opacity = 0.25; labelFill = '#4a4f5e';
    }

    // Build waypoints for via intermediaries
    const pathNodeIds = [step.from_component, ...(step.via || []), step.to_component];
    const waypoints = pathNodeIds.map(id => ({ x: colX[ordered.indexOf(id)], y }));

    // Draw arrow segments
    for (let j = 0; j < waypoints.length - 1; j++) {
      const isLast = j === waypoints.length - 2;
      const seg = arrowG.append('line')
        .attr('x1', waypoints[j].x).attr('y1', waypoints[j].y)
        .attr('x2', waypoints[j + 1].x).attr('y2', waypoints[j + 1].y)
        .attr('stroke', color).attr('stroke-width', strokeW).attr('stroke-opacity', opacity);
      if (isLast) seg.attr('marker-end', markerRef);
    }

    // Via dots
    if (step.via && step.via.length > 0) {
      step.via.forEach(vId => {
        const vIdx = ordered.indexOf(vId);
        if (vIdx >= 0) {
          arrowG.append('circle')
            .attr('cx', colX[vIdx]).attr('cy', y).attr('r', 3)
            .attr('fill', color).attr('opacity', opacity);
        }
      });
    }

    // Step number
    arrowG.append('text').attr('class', 'seq-step-num')
      .attr('x', MARGIN_X - 12).attr('y', y + 4)
      .attr('fill', labelFill).attr('opacity', opacity)
      .text(step.step_order);

    // Label above arrow (protocol + label)
    const labelX = (fromX + toX) / 2;
    const labelY = y - 8;
    arrowG.append('text').attr('class', 'seq-arrow-label')
      .attr('x', labelX).attr('y', labelY)
      .attr('text-anchor', 'middle').attr('fill', labelFill).attr('opacity', opacity)
      .text(step.label);
  });

  // --- Dot animation on current step ---
  if (currentStepIdx >= 0 && currentStepIdx < totalSteps) {
    const step = currentFlow.steps[currentStepIdx];
    const y = rowY(currentStepIdx);
    const pathNodeIds = [step.from_component, ...(step.via || []), step.to_component];
    const waypoints = pathNodeIds.map(id => ({ x: colX[ordered.indexOf(id)], y }));

    if (waypoints.length >= 2) {
      const dot = flowLayer.append('circle')
        .attr('class', 'flow-dot').attr('r', 5)
        .attr('cx', waypoints[0].x).attr('cy', waypoints[0].y);

      const PIXELS_PER_MS = 0.15;
      const segDurations = [];
      for (let w = 1; w < waypoints.length; w++) {
        const dx = waypoints[w].x - waypoints[w - 1].x;
        segDurations.push(Math.abs(dx) / PIXELS_PER_MS);
      }

      const savedIdx = currentStepIdx;
      const isLastStep = currentStepIdx === totalSteps - 1;

      function animFwd() {
        let t = dot;
        for (let w = 1; w < waypoints.length; w++) {
          t = t.transition().duration(segDurations[w - 1]).ease(d3.easeLinear)
            .attr('cx', waypoints[w].x).attr('cy', waypoints[w].y);
        }
        t.on('end', function () {
          if (onDotArrived) onDotArrived();
          if (isLastStep || playing) return;
          animBwd();
        });
      }

      function animBwd() {
        let t = d3.select(dot.node());
        for (let w = waypoints.length - 2; w >= 0; w--) {
          t = t.transition().duration(segDurations[w]).ease(d3.easeLinear)
            .attr('cx', waypoints[w].x).attr('cy', waypoints[w].y);
        }
        t.on('end', function () {
          if (currentStepIdx === savedIdx) animFwd();
        });
      }

      animFwd();
    }
  }
}

// =============================================================================
// Focused Topology Renderer
// =============================================================================
function pointToSegmentDist(p, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.sqrt((p.x - a.x) ** 2 + (p.y - a.y) ** 2);
  let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / lenSq;
  t = Math.max(0, Math.min(1, t));
  const projX = a.x + t * dx, projY = a.y + t * dy;
  return Math.sqrt((p.x - projX) ** 2 + (p.y - projY) ** 2);
}

function curvedPath(fromPos, toPos, fromId, toId, allPositions) {
  const dx = toPos.x - fromPos.x;
  const dy = toPos.y - fromPos.y;
  const midX = (fromPos.x + toPos.x) / 2;
  const midY = (fromPos.y + toPos.y) / 2;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;

  // Check for obstructing node boxes on the straight-line path
  let maxObstruction = 0;
  let offsetDir = 1;
  for (const [nid, pos] of Object.entries(allPositions)) {
    if (nid === fromId || nid === toId) continue;
    const dist = pointToSegmentDist(pos, fromPos, toPos);
    if (dist < NODE_H + 10 && dist < len * 0.4) {
      if (dist > maxObstruction || maxObstruction === 0) {
        maxObstruction = dist;
        const cross = dx * (pos.y - fromPos.y) - dy * (pos.x - fromPos.x);
        offsetDir = cross > 0 ? -1 : 1;
      }
    }
  }

  const offset = maxObstruction > 0
    ? 50 * offsetDir
    : Math.min(15, len * 0.08) * (dy > 0 ? 1 : -1);
  const cpX = midX + (-dy / len) * offset;
  const cpY = midY + (dx / len) * offset;

  return `M ${fromPos.x} ${fromPos.y} Q ${cpX} ${cpY} ${toPos.x} ${toPos.y}`;
}

function highlightFlowFocused() {
  if (!topoData || !currentFlow) return;

  const svg = d3.select('#topo-svg');
  const flowLayer = svg.select('.flow-layer');
  flowLayer.selectAll('*').remove();

  // Reset CSS classes
  svg.selectAll('.node').classed('node-hidden', false).classed('node-dimmed', false).classed('node-spotlight', false);

  // Hide all base edges
  svg.selectAll('.edge').attr('stroke-opacity', 0);

  if (currentStepIdx < 0) return;

  const width = _topoW;
  const height = _topoH;
  const rows = 5, slots = 12;
  const halfW = NODE_W / 2, halfH = NODE_H / 2;

  function getPos(id) {
    const n = topoData.nodes.find(n => n.id === id);
    if (!n) return null;
    return { x: (n.slot + 0.5) / slots * width, y: (n.row + 0.5) / rows * height };
  }

  function edgePoint(center, toward) {
    const dx = toward.x - center.x, dy = toward.y - center.y;
    if (dx === 0 && dy === 0) return { ...center };
    const scaleX = halfW / Math.abs(dx || 0.001);
    const scaleY = halfH / Math.abs(dy || 0.001);
    const scale = Math.min(scaleX, scaleY);
    return { x: center.x + dx * scale, y: center.y + dy * scale };
  }

  // Collect all NFs in this flow
  const involvedNFs = new Set();
  currentFlow.steps.forEach(step => {
    involvedNFs.add(step.from_component);
    involvedNFs.add(step.to_component);
    if (step.via) step.via.forEach(v => involvedNFs.add(v));
  });

  // Current step's active NFs
  const step = currentFlow.steps[currentStepIdx];
  const activeNFs = new Set([step.from_component, step.to_component, ...(step.via || [])]);

  // Apply visibility classes
  svg.selectAll('.node').each(function () {
    const nodeId = d3.select(this).attr('data-id');
    if (!involvedNFs.has(nodeId)) {
      d3.select(this).classed('node-hidden', true);
    } else if (activeNFs.has(nodeId)) {
      d3.select(this).classed('node-spotlight', true);
    } else {
      d3.select(this).classed('node-dimmed', true);
    }
  });

  // Build position map for curve routing
  const allPositions = {};
  topoData.nodes.forEach(n => {
    if (involvedNFs.has(n.id)) {
      allPositions[n.id] = getPos(n.id);
    }
  });

  // Draw limited history: previous step + current step
  const stepsToRender = [];
  if (currentStepIdx > 0) stepsToRender.push({ idx: currentStepIdx - 1, isCurrent: false });
  stepsToRender.push({ idx: currentStepIdx, isCurrent: true });

  stepsToRender.forEach(({ idx, isCurrent }) => {
    const s = currentFlow.steps[idx];
    const color = isCurrent ? '#58a6ff' : '#238636';
    const strokeW = isCurrent ? 3 : 2;
    const opacity = isCurrent ? 1.0 : 0.4;

    const pathNodes = [s.from_component, ...(s.via || []), s.to_component];

    // Build full SVG path through all segments
    let fullPathD = '';
    for (let j = 0; j < pathNodes.length - 1; j++) {
      const fromCenter = getPos(pathNodes[j]);
      const toCenter = getPos(pathNodes[j + 1]);
      if (!fromCenter || !toCenter) continue;

      const from = edgePoint(fromCenter, toCenter);
      const to = edgePoint(toCenter, fromCenter);
      const segPath = curvedPath(from, to, pathNodes[j], pathNodes[j + 1], allPositions);

      if (j === 0) {
        fullPathD += segPath;
      } else {
        // Continue from current position with L to next start, then Q curve
        const parts = segPath.split(' ');
        // Skip the M command, use L to connect, then Q curve
        fullPathD += ` L ${parts[1]} ${parts[2]} Q ${parts[4]} ${parts[5]} ${parts[6]} ${parts[7]}`;
      }
    }

    if (fullPathD) {
      const pathEl = flowLayer.append('path')
        .attr('d', fullPathD)
        .attr('fill', 'none')
        .attr('stroke', color)
        .attr('stroke-width', strokeW)
        .attr('stroke-opacity', opacity);

      if (isCurrent) pathEl.attr('class', 'current-flow-path');
    }
  });

  // Highlight involved node rects
  stepsToRender.forEach(({ idx, isCurrent }) => {
    const s = currentFlow.steps[idx];
    const pathNodes = [s.from_component, ...(s.via || []), s.to_component];
    pathNodes.forEach(nid => {
      svg.selectAll(`.node[data-id="${nid}"] rect`)
        .attr('fill', isCurrent ? '#1f2937' : '#161b22')
        .attr('stroke-width', isCurrent ? 3 : 2);
    });
  });

  // Dot animation along curved path
  const currentPath = flowLayer.select('.current-flow-path').node();
  if (currentPath) {
    const pathLength = currentPath.getTotalLength();
    const duration = pathLength / 0.15;

    const startPt = currentPath.getPointAtLength(0);
    const dot = flowLayer.append('circle')
      .attr('class', 'flow-dot').attr('r', 5)
      .attr('cx', startPt.x).attr('cy', startPt.y);

    const savedIdx = currentStepIdx;
    const isLastStep = currentStepIdx === currentFlow.steps.length - 1;

    function animFwd() {
      dot.transition().duration(duration).ease(d3.easeLinear)
        .tween('pathFollow', function () {
          return function (t) {
            const pt = currentPath.getPointAtLength(t * pathLength);
            d3.select(this).attr('cx', pt.x).attr('cy', pt.y);
          };
        })
        .on('end', function () {
          if (onDotArrived) onDotArrived();
          if (isLastStep || playing) return;
          animBwd();
        });
    }

    function animBwd() {
      d3.select(dot.node()).transition().duration(duration).ease(d3.easeLinear)
        .tween('pathFollow', function () {
          return function (t) {
            const pt = currentPath.getPointAtLength((1 - t) * pathLength);
            d3.select(this).attr('cx', pt.x).attr('cy', pt.y);
          };
        })
        .on('end', function () {
          if (currentStepIdx === savedIdx) animFwd();
        });
    }

    animFwd();
  }
}

// Handle window resize
window.addEventListener('resize', () => {
  _cacheTopoSize();
  renderForCurrentMode();
});
