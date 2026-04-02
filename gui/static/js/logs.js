// =============================================================================
// logs.js — Log viewer: WebSocket streaming, classification, timeline events
// =============================================================================
// Used by: dashboard page, logs page
// Requires: common.js

// --- State ---
let logSockets = {};

// --- Noise patterns ---
const NOISE_PATTERNS = [
  /^\d{2}:\d{2}:\d{2}\.\d+\s+\S+\.c\s+[.!]+/,         // pjsua source file debug lines
  /Module "mod-/,                                         // module registration
  /ALSA/,                                                 // audio subsystem
  /I\/O Queue created/,                                   // internal plumbing
  /SIP worker threads/,                                   // startup noise
  /select\(\)/,                                           // I/O implementation
  /^>>>/,                                                 // pjsua prompt markers
  /^\s*$/,                                                // blank lines
  /Buddy list:/,                                          // pjsua menu
  /^\s*-none-/,                                           // pjsua menu
  /^Choices:/,                                            // pjsua menu
  /^\s+\d+\s+For current/,                                // pjsua menu
  /^\s+URL\s+An URL/,                                     // pjsua menu
  /^\s+<Enter>/,                                          // pjsua menu
  /You currently have \d+ calls/,                         // pjsua menu
  /Account <sip:/,                                        // account internal
  /\.c\s+\.+(Acc|Registration|SIP transaction|Received|Sending|Timer|Binding)/,  // verbose internals
];

// --- Event extraction ---
function extractEvent(line) {
  let m;
  // UERANSIM NAS events
  if ((m = line.match(/Initial Registration is successful/)))
    return { text: 'Registered with 5G core', cat: 'success' };
  if ((m = line.match(/PDU Session establishment is successful PSI\[(\d+)\]/)))
    return { text: `PDU Session ${m[1]} established`, cat: 'network' };
  if ((m = line.match(/TUN interface\[(\w+), ([\d.]+)\] is up/)))
    return { text: `${m[1]} up (${m[2]})`, cat: 'network' };
  if ((m = line.match(/RRC connection established/)))
    return { text: 'RRC connected', cat: 'network' };

  // pjsua registration
  if ((m = line.match(/registration success, status=200/)))
    return { text: 'IMS registration successful', cat: 'success' };
  if ((m = line.match(/registration.*status=(\d+)/)))
    return { text: `IMS registration failed (${m[1]})`, cat: 'error' };

  // Call state changes
  if ((m = line.match(/Call (\d+) state changed to (\w+)/)))
    return { text: `Call ${m[1]}: ${m[2]}`, cat: 'call' };

  // SIP requests (TX)
  if ((m = line.match(/TX \d+ bytes Request msg (\w+)\/cseq=(\d+).*to .* ([\d.]+:\d+)/)))
    return { text: `TX ${m[1]} (cseq=${m[2]}) -> ${m[3]}`, cat: 'sip' };

  // SIP responses (RX)
  if ((m = line.match(/RX \d+ bytes Response msg (\d+)\/(\w+)\/cseq=(\d+)/)))
    return { text: `RX ${m[1]} ${m[2]} (cseq=${m[3]})`, cat: 'sip' };

  // SIP requests (RX)
  if ((m = line.match(/RX \d+ bytes Request msg (\w+)\/cseq=(\d+).*from .* ([\d.]+:\d+)/)))
    return { text: `RX ${m[1]} (cseq=${m[2]}) <- ${m[3]}`, cat: 'sip' };

  // IMS bearer
  if ((m = line.match(/IMS bearer established with IP: ([\d.]+)/)))
    return { text: `IMS bearer: ${m[1]}`, cat: 'network' };

  // Entrypoint banners
  if ((m = line.match(/IMS TUN interface is up with IP: ([\d.]+)/)))
    return { text: `IMS TUN up: ${m[1]}`, cat: 'network' };

  return null;
}

// --- Line classification ---
function classifyLine(line) {
  if (/Call \d+ state changed to/.test(line)) return 'call-state';
  if (/registration success|status=200.*OK/.test(line)) return 'highlight';
  if (/^(INVITE|REGISTER|BYE|CANCEL|ACK|UPDATE|PRACK|SUBSCRIBE|NOTIFY|OPTIONS|INFO|REFER|MESSAGE) sip:/i.test(line)) return 'sip-method';
  if (/^SIP\/2\.0 \d+/.test(line)) return 'sip-response';
  if (/\[(nas|rrc|app)\].*\[.*info/.test(line)) return 'ue-event';
  if (/error|fail/i.test(line) && !/Allow:/.test(line)) return 'error';
  if (/warn|timeout/i.test(line)) return 'warn';
  return '';
}

function isNoise(line) {
  return NOISE_PATTERNS.some(p => p.test(line));
}

function extractTime(line) {
  const m = line.match(/(\d{2}:\d{2}:\d{2})/);
  return m ? m[1] : '';
}

// --- Log WebSocket ---
function connectLogWS(ue) {
  const container = `e2e_${ue}`;
  const ws = new WebSocket(`${WS_BASE}/ws/logs/${container}`);
  logSockets[ue] = ws;

  const logArea = document.getElementById(`${ue}-logs`);
  const eventArea = document.getElementById(`${ue}-events`);

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'log') {
      appendLog(logArea, eventArea, msg.line);
    }
  };

  ws.onclose = () => {
    logSockets[ue] = null;
  };
}

function appendLog(logArea, eventArea, text) {
  const div = document.createElement('div');
  div.className = 'log-line';

  const cls = classifyLine(text);
  if (cls) div.classList.add(cls);

  if (isNoise(text)) {
    div.classList.add('noise');
  }

  div.textContent = text;
  logArea.appendChild(div);

  // Extract events for timeline
  const event = extractEvent(text);
  if (event) {
    addTimelineEvent(eventArea, extractTime(text), event.text, event.cat);
  }

  // Keep max 2000 lines
  while (logArea.children.length > 2000) {
    logArea.removeChild(logArea.firstChild);
  }

  logArea.scrollTop = logArea.scrollHeight;
}

function addTimelineEvent(area, time, text, cat) {
  const div = document.createElement('div');
  div.className = `event evt-${cat}`;
  div.innerHTML = `<div class="event-time">${time}</div><div class="event-text">${escapeHtml(text)}</div>`;
  area.appendChild(div);

  while (area.children.length > 200) {
    area.removeChild(area.firstChild);
  }

  area.scrollTop = area.scrollHeight;
}

// --- Log filter toggle ---
function toggleLogFilter(ue, showAll) {
  const logArea = document.getElementById(`${ue}-logs`);
  const btnFiltered = document.getElementById(`btn-${ue}-filtered`);
  const btnAll = document.getElementById(`btn-${ue}-all`);

  if (showAll) {
    logArea.classList.add('show-all');
    btnAll.classList.add('active');
    btnFiltered.classList.remove('active');
  } else {
    logArea.classList.remove('show-all');
    btnFiltered.classList.add('active');
    btnAll.classList.remove('active');
  }
  logArea.scrollTop = logArea.scrollHeight;
}

function clearLogs(ue) {
  document.getElementById(`${ue}-logs`).innerHTML = '';
  document.getElementById(`${ue}-events`).innerHTML = '';
}

// --- AI explain ---
async function explainLogs(ue) {
  const btn = document.getElementById(`btn-${ue}-ai`);
  const logArea = document.getElementById(`${ue}-logs`);

  const lines = [];
  for (const el of logArea.children) {
    if (!el.classList.contains('noise')) {
      lines.push(el.textContent);
    }
  }

  if (lines.length === 0) {
    alert('No logs to explain.');
    return;
  }

  const overlay = document.getElementById('ai-overlay');
  const body = document.getElementById('ai-body');
  document.getElementById('ai-title').textContent = `AI Explanation — ${ue.toUpperCase()}`;
  body.textContent = 'Analyzing logs...';
  overlay.classList.add('active');

  btn.disabled = true;
  btn.textContent = '...';

  try {
    const res = await fetch(`${API_BASE}/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ logs: lines.join('\n') }),
    });
    const data = await res.json();
    if (data.ok) {
      body.textContent = data.explanation;
    } else {
      body.textContent = `Error: ${data.error}`;
    }
  } catch (e) {
    body.textContent = `Error: ${e.message}`;
  }

  btn.disabled = false;
  btn.textContent = 'AI Explain';
}

async function explainDetailLogs() {
  const btn = document.getElementById('detail-ai-btn');
  const logArea = document.getElementById('detail-log-area');
  if (!logArea || !detailNodeId) return;

  const lines = [];
  for (const el of logArea.children) {
    lines.push(el.textContent);
  }

  if (lines.length === 0) {
    alert('No logs to explain.');
    return;
  }

  const node = lastTopology?.nodes?.find(n => n.id === detailNodeId);
  const label = node?.label || detailNodeId;

  const overlay = document.getElementById('ai-overlay');
  const body = document.getElementById('ai-body');
  document.getElementById('ai-title').textContent = `AI Explanation — ${label}`;
  body.textContent = 'Analyzing logs...';
  overlay.classList.add('active');

  btn.disabled = true;
  btn.textContent = '...';

  try {
    const res = await fetch(`${API_BASE}/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ logs: lines.join('\n'), container: detailNodeId }),
    });
    const data = await res.json();
    if (data.ok) {
      body.textContent = data.explanation;
    } else {
      body.textContent = `Error: ${data.error}`;
    }
  } catch (e) {
    body.textContent = `Error: ${e.message}`;
  }

  btn.disabled = false;
  btn.textContent = 'AI Explain';
}

function closeAiModal() {
  document.getElementById('ai-overlay').classList.remove('active');
}
