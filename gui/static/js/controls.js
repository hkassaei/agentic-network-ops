// =============================================================================
// controls.js — Stack deploy/teardown, UE actions, modal
// =============================================================================
// Used by: dashboard page
// Requires: common.js

// --- Deploy / Teardown ---
function deployStack() {
  openModal('Deploying Stack...', 'ws/deploy');
}

function deployUEs() {
  openModal('Deploying UEs...', 'ws/deploy-ues');
}

function teardownUEs() {
  openModal('Tearing Down UEs...', 'ws/teardown-ues');
}

function teardownStack() {
  openModal('Tearing Down Full Stack...', 'ws/teardown-stack');
}

function deployOntologyDB() {
  openModal('Deploying Ontology DB...', 'ws/deploy-ontology');
}

function reseedOntology() {
  openModal('Re-seeding Ontology...', 'ws/reseed-ontology');
}

function openModal(title, wsPath) {
  const overlay = document.getElementById('modal-overlay');
  const body = document.getElementById('modal-body');
  const statusEl = document.getElementById('modal-status');
  const closeBtn = document.getElementById('modal-close-btn');

  document.getElementById('modal-title').textContent = title;
  body.textContent = '';
  statusEl.textContent = 'Running...';
  statusEl.style.color = 'var(--text-dim)';
  closeBtn.disabled = true;
  overlay.classList.add('active');

  const ws = new WebSocket(`${WS_BASE}/${wsPath}`);

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'progress') {
      body.textContent += msg.line + '\n';
      body.scrollTop = body.scrollHeight;
    } else if (msg.type === 'done') {
      if (msg.success) {
        statusEl.textContent = 'Completed successfully';
        statusEl.style.color = 'var(--green)';
      } else {
        statusEl.textContent = `Failed: ${msg.message || 'Unknown error'}`;
        statusEl.style.color = 'var(--red)';
      }
      closeBtn.disabled = false;
      pollStatus();
    } else if (msg.type === 'error') {
      statusEl.textContent = msg.message;
      statusEl.style.color = 'var(--red)';
      closeBtn.disabled = false;
    }
  };

  ws.onerror = () => {
    statusEl.textContent = 'WebSocket error';
    statusEl.style.color = 'var(--red)';
    closeBtn.disabled = false;
  };

  ws.onclose = () => {
    closeBtn.disabled = false;
  };
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('active');
  pollStatus();
}

// --- UE actions ---
async function ueAction(ue, action) {
  const btn = document.getElementById(`btn-${ue}-${action}`);
  const origText = btn.textContent;
  btn.textContent = '...';
  btn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/ue/${ue}/${action}`, { method: 'POST' });
    const data = await res.json();
    if (!data.ok) {
      alert(`Action failed: ${data.error}`);
    }
  } catch (e) {
    alert(`Error: ${e.message}`);
  }

  btn.textContent = origText;
  btn.disabled = false;
}
