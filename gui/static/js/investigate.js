// =============================================================================
// investigate.js — All investigation modals: v1.5, v3, v4/v5
// =============================================================================
// Used by: dashboard page, investigate page
// Requires: common.js

function truncate(s, max) {
  if (!s) return '';
  return s.length > max ? s.substring(0, max) + '...' : s;
}

// =============================================================================
// V1.5 Investigation
// =============================================================================

let invWs = null;

function openInvestigate() {
  const overlay = document.getElementById('inv-overlay');
  document.getElementById('inv-question').value = '';
  document.getElementById('inv-progress').style.display = 'none';
  document.getElementById('inv-progress').innerHTML = '';
  document.getElementById('inv-result').style.display = 'none';
  document.getElementById('inv-result').innerHTML = '';
  document.getElementById('inv-footer').style.display = 'none';
  document.getElementById('inv-status').textContent = '';
  document.getElementById('inv-send-btn').disabled = false;
  document.getElementById('inv-input').style.display = 'flex';
  overlay.classList.add('active');
  document.getElementById('inv-question').focus();
}

function sendInvestigation() {
  const input = document.getElementById('inv-question');
  const question = input.value.trim();
  if (!question) return;

  const sendBtn = document.getElementById('inv-send-btn');
  const progress = document.getElementById('inv-progress');
  const result = document.getElementById('inv-result');
  const footer = document.getElementById('inv-footer');
  const status = document.getElementById('inv-status');

  sendBtn.disabled = true;
  sendBtn.textContent = 'Working...';
  progress.style.display = 'block';
  progress.innerHTML = '';
  result.style.display = 'none';
  result.innerHTML = '';
  footer.style.display = 'flex';
  status.textContent = 'Connecting...';

  invWs = new WebSocket(`${WS_BASE}/ws/investigate`);

  invWs.onopen = () => {
    status.textContent = 'Investigating...';
    invWs.send(JSON.stringify({ question }));
  };

  invWs.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === 'status') {
      _addProgress('inv-progress', 'status', msg.message);
    } else if (msg.type === 'tool_call') {
      _addProgress('inv-progress', 'tool', `🔧 ${msg.name}(${truncate(msg.args, 80)})`);
    } else if (msg.type === 'tool_result') {
      _addProgress('inv-progress', 'result', `  ↳ ${msg.name}: ${truncate(msg.preview, 120)}`);
    } else if (msg.type === 'text') {
      _addProgress('inv-progress', 'text', msg.content);
    } else if (msg.type === 'diagnosis') {
      _renderDiagnosis('inv-result', msg);
      status.textContent = 'Investigation complete';
      status.style.color = 'var(--green)';
    } else if (msg.type === 'usage') {
      const existing = status.textContent;
      status.textContent = `${existing} · ${msg.total_tokens.toLocaleString()} tokens`;
    } else if (msg.type === 'error') {
      result.style.display = 'block';
      result.innerHTML = `<div style="color:var(--red)">Error: ${escapeHtml(msg.message)}</div>`;
      status.textContent = 'Failed';
      status.style.color = 'var(--red)';
    }
  };

  invWs.onerror = () => {
    status.textContent = 'WebSocket error';
    status.style.color = 'var(--red)';
    sendBtn.disabled = false;
    sendBtn.textContent = 'Investigate';
  };

  invWs.onclose = () => {
    sendBtn.disabled = false;
    sendBtn.textContent = 'Investigate';
    invWs = null;
  };
}

function closeInvestigation() {
  if (invWs) {
    invWs.close();
    invWs = null;
  }
  document.getElementById('inv-overlay').classList.remove('active');
}

// =============================================================================
// V3 Investigation
// =============================================================================

let inv3Ws = null;

function openInvestigateV3() {
  document.getElementById('inv3-question').value = '';
  document.getElementById('inv3-progress').style.display = 'none';
  document.getElementById('inv3-progress').innerHTML = '';
  document.getElementById('inv3-result').style.display = 'none';
  document.getElementById('inv3-result').innerHTML = '';
  document.getElementById('inv3-trace').style.display = 'none';
  document.getElementById('inv3-trace').innerHTML = '';
  document.getElementById('inv3-footer').style.display = 'none';
  document.getElementById('inv3-status').textContent = '';
  document.getElementById('inv3-send-btn').disabled = false;
  document.getElementById('inv3-send-btn').textContent = 'Investigate';
  document.getElementById('inv3-input').style.display = 'flex';
  document.getElementById('inv3-overlay').classList.add('active');
  document.getElementById('inv3-question').focus();
}

function sendInvestigationV3() {
  const input = document.getElementById('inv3-question');
  const question = input.value.trim();
  if (!question) return;

  const sendBtn = document.getElementById('inv3-send-btn');
  const progress = document.getElementById('inv3-progress');
  const result = document.getElementById('inv3-result');
  const footer = document.getElementById('inv3-footer');
  const status = document.getElementById('inv3-status');

  sendBtn.disabled = true;
  sendBtn.textContent = 'Working...';
  progress.style.display = 'block';
  progress.innerHTML = '';
  result.style.display = 'none';
  result.innerHTML = '';
  footer.style.display = 'flex';
  status.textContent = 'Connecting to v3 pipeline...';

  inv3Ws = new WebSocket(`${WS_BASE}/ws/investigate-v3`);

  inv3Ws.onopen = () => {
    status.textContent = 'Context-isolated investigation in progress...';
    inv3Ws.send(JSON.stringify({ question }));
  };

  inv3Ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === 'status') {
      _addProgress('inv3-progress', 'status', msg.message);
    } else if (msg.type === 'phase_start') {
      _addProgress('inv3-progress', 'phase', `▶ ${msg.agent}`);
      status.textContent = `Running: ${msg.agent}`;
    } else if (msg.type === 'tool_call') {
      const agent = msg.agent ? `[${msg.agent}] ` : '';
      _addProgress('inv3-progress', 'tool', `  ${agent}🔧 ${msg.name}(${truncate(msg.args || '', 100)})`);
    } else if (msg.type === 'tool_result') {
      _addProgress('inv3-progress', 'result', `    ↳ ${msg.name}: ${truncate(msg.preview || '', 150)}`);
    } else if (msg.type === 'text') {
      const agent = msg.agent ? `[${msg.agent}] ` : '';
      _addProgress('inv3-progress', 'text', `  ${agent}${truncate(msg.content || '', 200)}`);
    } else if (msg.type === 'diagnosis') {
      _renderDiagnosis('inv3-result', msg);
      status.textContent = 'Investigation complete';
      status.style.color = 'var(--green)';
    } else if (msg.type === 'investigation_trace') {
      _renderTrace('inv3-trace', 'v3', msg.trace);
    } else if (msg.type === 'usage') {
      const existing = status.textContent;
      status.textContent = `${existing} · ${msg.total_tokens.toLocaleString()} tokens`;
    } else if (msg.type === 'error') {
      result.style.display = 'block';
      result.innerHTML = `<div style="color:var(--red)">Error: ${escapeHtml(msg.message)}</div>`;
      status.textContent = 'Failed';
      status.style.color = 'var(--red)';
    }
  };

  inv3Ws.onerror = () => {
    status.textContent = 'WebSocket error';
    status.style.color = 'var(--red)';
    sendBtn.disabled = false;
    sendBtn.textContent = 'Investigate';
  };

  inv3Ws.onclose = () => {
    sendBtn.disabled = false;
    sendBtn.textContent = 'Investigate';
    inv3Ws = null;
  };
}

function closeInvestigationV3() {
  if (inv3Ws) {
    inv3Ws.close();
    inv3Ws = null;
  }
  document.getElementById('inv3-overlay').classList.remove('active');
}

// =============================================================================
// V4/V5 Investigation (shared — uses same modal, different WS endpoints)
// =============================================================================

let inv4Ws = null;

function openInvestigateV4() {
  document.getElementById('inv4-question').value = '';
  document.getElementById('inv4-progress').style.display = 'none';
  document.getElementById('inv4-progress').innerHTML = '';
  document.getElementById('inv4-result').style.display = 'none';
  document.getElementById('inv4-result').innerHTML = '';
  document.getElementById('inv4-trace').style.display = 'none';
  document.getElementById('inv4-trace').innerHTML = '';
  document.getElementById('inv4-footer').style.display = 'none';
  document.getElementById('inv4-status').textContent = '';
  document.getElementById('inv4-send-btn').disabled = false;
  document.getElementById('inv4-send-btn').textContent = 'Investigate';
  document.getElementById('inv4-input').style.display = 'flex';
  document.getElementById('inv4-overlay').classList.add('active');
  document.getElementById('inv4-question').focus();
}

function sendInvestigationV4() {
  const input = document.getElementById('inv4-question');
  const question = input.value.trim();
  if (!question) return;

  const sendBtn = document.getElementById('inv4-send-btn');
  const progress = document.getElementById('inv4-progress');
  const result = document.getElementById('inv4-result');
  const footer = document.getElementById('inv4-footer');
  const status = document.getElementById('inv4-status');

  sendBtn.disabled = true;
  sendBtn.textContent = 'Working...';
  progress.style.display = 'block';
  progress.innerHTML = '';
  result.style.display = 'none';
  result.innerHTML = '';
  footer.style.display = 'flex';
  status.textContent = 'Connecting to v4 pipeline...';

  inv4Ws = new WebSocket(`${WS_BASE}/ws/investigate-v4`);

  inv4Ws.onopen = () => {
    status.textContent = 'Topology-aware investigation in progress...';
    inv4Ws.send(JSON.stringify({ question }));
  };

  inv4Ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === 'status') {
      _addProgress('inv4-progress', 'status', msg.message);
    } else if (msg.type === 'phase_start') {
      _addProgress('inv4-progress', 'phase', `▶ ${msg.agent}`);
      status.textContent = `Running: ${msg.agent}`;
    } else if (msg.type === 'tool_call') {
      const agent = msg.agent ? `[${msg.agent}] ` : '';
      _addProgress('inv4-progress', 'tool', `  ${agent}🔧 ${msg.name}(${truncate(msg.args || '', 100)})`);
    } else if (msg.type === 'tool_result') {
      _addProgress('inv4-progress', 'result', `    ↳ ${msg.name}: ${truncate(msg.preview || '', 150)}`);
    } else if (msg.type === 'text') {
      const agent = msg.agent ? `[${msg.agent}] ` : '';
      _addProgress('inv4-progress', 'text', `  ${agent}${truncate(msg.content || '', 200)}`);
    } else if (msg.type === 'diagnosis') {
      _renderDiagnosis('inv4-result', msg);
      status.textContent = 'Investigation complete';
      status.style.color = 'var(--green)';
    } else if (msg.type === 'investigation_trace') {
      _renderTrace('inv4-trace', 'v4', msg.trace);
    } else if (msg.type === 'usage') {
      const existing = status.textContent;
      status.textContent = `${existing} · ${msg.total_tokens.toLocaleString()} tokens`;
    } else if (msg.type === 'error') {
      result.style.display = 'block';
      result.innerHTML = `<div style="color:var(--red)">Error: ${escapeHtml(msg.message)}</div>`;
      status.textContent = 'Failed';
      status.style.color = 'var(--red)';
    }
  };

  inv4Ws.onerror = () => {
    status.textContent = 'WebSocket error';
    status.style.color = 'var(--red)';
    sendBtn.disabled = false;
    sendBtn.textContent = 'Investigate';
  };

  inv4Ws.onclose = () => {
    sendBtn.disabled = false;
    sendBtn.textContent = 'Investigate';
    inv4Ws = null;
  };
}

function closeInvestigationV4() {
  if (inv4Ws) {
    inv4Ws.close();
    inv4Ws = null;
  }
  document.getElementById('inv4-overlay').classList.remove('active');
}

// =============================================================================
// Shared rendering functions
// =============================================================================

function _addProgress(containerId, type, text) {
  const progress = document.getElementById(containerId);
  const line = document.createElement('div');
  line.style.marginBottom = '2px';
  if (type === 'phase') {
    line.style.color = 'var(--green)';
    line.style.fontWeight = '600';
    line.style.marginTop = '6px';
  } else if (type === 'tool') {
    line.style.color = 'var(--purple)';
  } else if (type === 'result') {
    line.style.color = 'var(--text-dim)';
    line.style.fontSize = '11px';
  } else if (type === 'status') {
    line.style.color = 'var(--accent)';
  }
  line.textContent = text;
  progress.appendChild(line);
  progress.scrollTop = progress.scrollHeight;
}

function _renderDiagnosis(containerId, diag) {
  const result = document.getElementById(containerId);
  result.style.display = 'block';

  const confidenceColor = { high: 'var(--green)', medium: 'var(--orange)', low: 'var(--red)' };
  const confColor = confidenceColor[diag.confidence] || 'var(--text-dim)';

  let html = `<div style="margin-bottom:16px"><h3 style="margin-bottom:8px;font-size:16px">Summary</h3><p>${escapeHtml(diag.summary)}</p></div>`;

  if (diag.timeline && diag.timeline.length > 0) {
    html += `<div style="margin-bottom:16px"><h3 style="margin-bottom:8px;font-size:16px">Timeline</h3><div style="font-family:'SF Mono',monospace;font-size:12px;background:var(--bg);padding:12px;border-radius:6px;max-height:200px;overflow-y:auto">`;
    for (const evt of diag.timeline) {
      html += `<div style="margin-bottom:4px"><span style="color:var(--text-dim)">${escapeHtml(evt.timestamp || '')}</span><span style="color:var(--green);margin:0 6px">[${escapeHtml(evt.container || '')}]</span><span>${escapeHtml(evt.event || '')}</span></div>`;
    }
    html += `</div></div>`;
  }

  html += `<div style="margin-bottom:16px"><h3 style="margin-bottom:8px;font-size:16px">Root Cause</h3><p style="background:var(--bg);padding:12px;border-radius:6px;border-left:3px solid var(--red);white-space:pre-wrap">${escapeHtml(diag.root_cause)}</p></div>`;

  if (diag.affected_components && diag.affected_components.length > 0) {
    html += `<div style="margin-bottom:16px"><h3 style="margin-bottom:8px;font-size:16px">Affected Components</h3><div style="display:flex;gap:6px;flex-wrap:wrap">`;
    for (const comp of diag.affected_components) {
      html += `<span style="background:var(--bg);padding:4px 10px;border-radius:4px;font-size:12px;border:1px solid var(--border)">${escapeHtml(comp)}</span>`;
    }
    html += `</div></div>`;
  }

  if (diag.recommendation) {
    html += `<div style="margin-bottom:16px"><h3 style="margin-bottom:8px;font-size:16px">Recommendation</h3><p style="background:var(--bg);padding:12px;border-radius:6px;border-left:3px solid var(--green);white-space:pre-wrap">${escapeHtml(diag.recommendation)}</p></div>`;
  }

  if (diag.explanation) {
    html += `<div style="margin-bottom:16px"><h3 style="margin-bottom:8px;font-size:16px">Detailed Explanation</h3><p style="white-space:pre-wrap">${escapeHtml(diag.explanation)}</p></div>`;
  }

  html += `<div style="text-align:right;font-size:13px">Confidence: <span style="color:${confColor};font-weight:600">${escapeHtml(diag.confidence)}</span></div>`;
  result.innerHTML = html;
}

function _renderTrace(containerId, prefix, trace) {
  const container = document.getElementById(containerId);
  if (!trace || !trace.phases || trace.phases.length === 0) return;
  container.style.display = 'block';

  const phases = trace.phases;
  const totalTokens = trace.total_tokens?.total || 0;
  const durationSec = ((trace.duration_ms || 0) / 1000).toFixed(1);
  const maxTokens = Math.max(...phases.map(p => p.tokens?.total || 0), 1);

  let html = `<div style="margin-bottom:8px;cursor:pointer;user-select:none" onclick="this.parentElement.querySelector('.trace-body').classList.toggle('trace-collapsed')">
    <span style="color:var(--green);font-weight:600">Investigation Trace</span>
    <span style="color:var(--text-dim);margin-left:8px">${phases.length} agents · ${totalTokens.toLocaleString()} tokens · ${durationSec}s</span>
    <span style="color:var(--text-dim);margin-left:4px;font-size:10px">▼ click to toggle</span>
  </div>`;

  html += `<div class="trace-body" style="background:var(--bg);border-radius:6px;padding:10px;border:1px solid var(--border)">`;
  html += `<div style="display:grid;grid-template-columns:180px 70px 100px 50px 50px 1fr;gap:6px;padding:4px 0;border-bottom:1px solid var(--border);color:var(--text-dim);font-size:11px;margin-bottom:4px">
    <span>Agent</span><span style="text-align:right">Duration</span><span style="text-align:right">Tokens</span><span style="text-align:right">Tools</span><span style="text-align:right">LLM</span><span style="padding-left:8px">Token Distribution</span>
  </div>`;

  for (const p of phases) {
    const dur = ((p.duration_ms || 0) / 1000).toFixed(1);
    const tok = p.tokens?.total || 0;
    const prompt = p.tokens?.prompt || 0;
    const completion = p.tokens?.completion || 0;
    const thinking = p.tokens?.thinking || 0;
    const tools = (p.tool_calls || []).length;
    const llm = p.llm_calls || 0;
    const barPct = Math.max((tok / maxTokens) * 100, 1);
    const promptPct = tok > 0 ? (prompt / tok) * 100 : 0;
    const completionPct = tok > 0 ? (completion / tok) * 100 : 0;
    const thinkingPct = tok > 0 ? (thinking / tok) * 100 : 0;
    const rowId = prefix + '-trace-row-' + p.agent_name.replace(/\W/g, '_');

    html += `<div style="display:grid;grid-template-columns:180px 70px 100px 50px 50px 1fr;gap:6px;padding:4px 0;align-items:center;cursor:pointer;border-bottom:1px solid var(--border)" onclick="document.getElementById('${rowId}').style.display = document.getElementById('${rowId}').style.display === 'none' ? 'block' : 'none'">
      <span style="color:var(--green);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(p.agent_name)}">${escapeHtml(p.agent_name)}</span>
      <span style="text-align:right;color:var(--text-dim)">${dur}s</span>
      <span style="text-align:right">${tok.toLocaleString()}</span>
      <span style="text-align:right;color:var(--purple)">${tools}</span>
      <span style="text-align:right;color:var(--orange)">${llm}</span>
      <div style="padding-left:8px;display:flex;align-items:center;gap:4px">
        <div style="flex:1;height:14px;background:var(--surface2);border-radius:3px;overflow:hidden;display:flex" title="Prompt: ${prompt.toLocaleString()} · Completion: ${completion.toLocaleString()}${thinking > 0 ? ' · Thinking: ' + thinking.toLocaleString() : ''}">
          <div style="width:${promptPct}%;background:var(--accent);min-width:${prompt > 0 ? 2 : 0}px"></div>
          <div style="width:${completionPct}%;background:var(--green);min-width:${completion > 0 ? 2 : 0}px"></div>
          ${thinking > 0 ? `<div style="width:${thinkingPct}%;background:var(--orange);min-width:2px"></div>` : ''}
        </div>
        <span style="font-size:10px;color:var(--text-dim);white-space:nowrap;width:40px;text-align:right">${Math.round(barPct)}%</span>
      </div>
    </div>`;

    html += `<div id="${rowId}" style="display:none;padding:6px 12px;background:var(--surface);border-bottom:1px solid var(--border);font-size:11px">`;
    html += `<div style="margin-bottom:4px;color:var(--text-dim)">Tokens: <span style="color:var(--accent)">prompt ${prompt.toLocaleString()}</span> · <span style="color:var(--green)">completion ${completion.toLocaleString()}</span>${thinking > 0 ? ` · <span style="color:var(--orange)">thinking ${thinking.toLocaleString()}</span>` : ''}</div>`;
    if (p.state_keys_written && p.state_keys_written.length > 0) {
      html += `<div style="margin-bottom:4px;color:var(--text-dim)">State: ${p.state_keys_written.map(k => `<span style="color:var(--yellow)">${escapeHtml(k)}</span>`).join(', ')}</div>`;
    }
    if (p.tool_calls && p.tool_calls.length > 0) {
      html += `<div style="margin-bottom:2px;color:var(--text-dim)">Tool calls:</div>`;
      for (const tc of p.tool_calls) {
        const size = tc.result_size > 0 ? ` → ${(tc.result_size / 1024).toFixed(1)}KB` : '';
        html += `<div style="padding-left:12px;color:var(--purple)">${escapeHtml(tc.name)}(<span style="color:var(--text-dim)">${escapeHtml(truncate(tc.args || '', 80))}</span>)${size}</div>`;
      }
    }
    if (p.output_summary) {
      html += `<div style="margin-top:4px;color:var(--text-dim)">Output: <span style="color:var(--text)">${escapeHtml(truncate(p.output_summary, 200))}</span></div>`;
    }
    html += `</div>`;
  }

  html += `<div style="margin-top:8px;font-size:10px;color:var(--text-dim);display:flex;gap:12px">
    <span><span style="display:inline-block;width:10px;height:10px;background:var(--accent);border-radius:2px;vertical-align:middle"></span> prompt</span>
    <span><span style="display:inline-block;width:10px;height:10px;background:var(--green);border-radius:2px;vertical-align:middle"></span> completion</span>
    <span><span style="display:inline-block;width:10px;height:10px;background:var(--orange);border-radius:2px;vertical-align:middle"></span> thinking</span>
  </div>`;
  html += `</div>`;
  container.innerHTML = html;
}
