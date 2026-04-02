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
  renderFlowTopology();
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
  highlightFlow();
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
  highlightFlow();
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

  const container = document.getElementById('topo-container');
  const width = container.clientWidth;
  const height = container.clientHeight;

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

  const container = document.getElementById('topo-container');
  const width = container.clientWidth;
  const height = container.clientHeight;
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

// Handle window resize
window.addEventListener('resize', () => {
  renderFlowTopology();
  highlightFlow();
});
