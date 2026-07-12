// ---------------------------------------------------------------------------
// State Management
// ---------------------------------------------------------------------------
let currentSessionId = localStorage.getItem('futbot_session_id');
let isWaitingForReply = false;
let pipelineSocket = null;
let pipelineSocketSessionId = null;
let pipelineRun = { cards: new Map(), iteration: 0 };

const STAGE_LABELS = {
  collecting_context: 'Collecting Context',
  rewriting: 'Rewriting',
  orchestrating: 'Orchestrating',
  retrieving: 'Retrieving',
  drafting: 'Drafting',
  judging: 'Judging',
  responding: 'Responding',
};

// ---------------------------------------------------------------------------
// DOM Elements
// ---------------------------------------------------------------------------
const messagesContainer = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const welcomeScreen = document.getElementById('welcome-screen');
const sessionIdDisplay = document.getElementById('session-id-display');
const sidebar = document.getElementById('sidebar');
const pipelineStages = document.getElementById('pipeline-stages');
const pipelineRunBadge = document.getElementById('pipeline-run-badge');
const ingestBtn = document.getElementById('ingest-btn');
const ingestFileInput = document.getElementById('ingest-file-input');
const ingestStatus = document.getElementById('ingest-status');

let ingestPollTimer = null;

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------
function init() {
  if (!currentSessionId) {
    newSession();
  } else {
    sessionIdDisplay.textContent = currentSessionId.slice(0, 8) + '...';
    connectPipelineSocket();
    loadHistory();
  }
}

function newSession() {
  currentSessionId = 'sess_' + Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
  localStorage.setItem('futbot_session_id', currentSessionId);
  sessionIdDisplay.textContent = currentSessionId.slice(0, 8) + '...';
  messagesContainer.innerHTML = '';
  welcomeScreen.style.display = 'block';
  userInput.value = '';
  autoResize(userInput);
  resetPipelinePanel();
  connectPipelineSocket();
}

// ---------------------------------------------------------------------------
// WebSocket — live pipeline status
// ---------------------------------------------------------------------------
function connectPipelineSocket() {
  if (!currentSessionId) return null;

  if (pipelineSocket && pipelineSocketSessionId === currentSessionId) {
    if (pipelineSocket.readyState === WebSocket.OPEN ||
        pipelineSocket.readyState === WebSocket.CONNECTING) {
      return pipelineSocket;
    }
  }

  if (pipelineSocket) {
    pipelineSocket.close();
    pipelineSocket = null;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${window.location.host}/ws/pipeline?session_id=${encodeURIComponent(currentSessionId)}`;
  pipelineSocketSessionId = currentSessionId;
  pipelineSocket = new WebSocket(url);

  pipelineSocket.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'connected' || data.type === 'ping') return;
      handlePipelineEvent(data);
    } catch (err) {
      console.error('Invalid pipeline event', err);
    }
  });

  pipelineSocket.addEventListener('close', () => {
    if (pipelineSocketSessionId !== currentSessionId) return;
    setTimeout(() => {
      if (pipelineSocketSessionId === currentSessionId) {
        connectPipelineSocket();
      }
    }, 2000);
  });

  return pipelineSocket;
}

function ensurePipelineSocket(timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    const socket = connectPipelineSocket();
    if (!socket) {
      reject(new Error('No session'));
      return;
    }
    if (socket.readyState === WebSocket.OPEN) {
      resolve(socket);
      return;
    }

    const onOpen = () => {
      cleanup();
      resolve(socket);
    };
    const onError = () => {
      cleanup();
      reject(new Error('WebSocket connection failed'));
    };
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error('WebSocket connection timed out'));
    }, timeoutMs);

    function cleanup() {
      socket.removeEventListener('open', onOpen);
      socket.removeEventListener('error', onError);
      clearTimeout(timer);
    }

    socket.addEventListener('open', onOpen);
    socket.addEventListener('error', onError);
  });
}

function handlePipelineEvent(event) {
  if (event.type === 'ping' || event.type === 'connected') return;

  if (event.type === 'pipeline_start') {
    resetPipelinePanel(false);
    setPipelineBadge('running', 'Running');
    return;
  }

  if (event.type === 'stage_update') {
    upsertTimelineStep(event);
    if (event.status === 'active') {
      setPipelineBadge('running', STAGE_LABELS[event.stage] || event.stage);
    }
    return;
  }

  if (event.type === 'pipeline_complete') {
    setPipelineBadge('complete', 'Complete');
    renderLoopSummary(event);
    return;
  }

  if (event.type === 'pipeline_error') {
    setPipelineBadge('error', 'Error');
    appendPipelineError(event.message || 'Unknown error');
  }
}

function resetPipelinePanel(showIdle = true) {
  pipelineRun = { cards: new Map(), iteration: 0, lastIteration: 0 };
  if (showIdle) {
    pipelineStages.innerHTML = `
      <div class="timeline-empty">
        <span class="timeline-empty-icon">⚽</span>
        <p>Send a message to watch each stage run — from context compression through retrieval and judging.</p>
      </div>
    `;
    setPipelineBadge('idle', 'Idle');
  } else {
    pipelineStages.innerHTML = '';
    setPipelineBadge('running', 'Running');
  }
}

function setPipelineBadge(kind, label) {
  pipelineRunBadge.className = `pipeline-badge ${kind}`;
  pipelineRunBadge.textContent = label;
}

function ensureIterationMarker(iteration) {
  const markerId = `iteration-${iteration}`;
  if (document.getElementById(markerId)) return;
  if (iteration <= 1) return;

  const marker = document.createElement('div');
  marker.id = markerId;
  marker.className = 'timeline-iteration-marker';
  marker.textContent = `Retry loop ${iteration}`;
  pipelineStages.appendChild(marker);
}

function upsertTimelineStep(event) {
  const empty = pipelineStages.querySelector('.timeline-empty');
  if (empty) empty.remove();

  ensureIterationMarker(event.iteration);

  const stepId = `step-${event.iteration}-${event.stage}`;
  let step = document.getElementById(stepId);

  if (!step) {
    step = document.createElement('div');
    step.id = stepId;
    step.className = 'timeline-step';
    step.innerHTML = `
      <div class="timeline-rail" aria-hidden="true">
        <span class="timeline-line"></span>
      </div>
      <div class="timeline-body">
        <button class="timeline-header" type="button" aria-expanded="false">
          <span class="timeline-title"></span>
          <span class="timeline-meta"></span>
          <span class="timeline-chevron" aria-hidden="true"></span>
        </button>
        <div class="timeline-details" hidden></div>
      </div>
    `;
    step.querySelector('.timeline-header').addEventListener('click', () => {
      toggleTimelineStep(step);
    });
    expandTimelineStep(step, false);
    pipelineStages.appendChild(step);
    pipelineRun.cards.set(stepId, step);
  }

  const titleEl = step.querySelector('.timeline-title');
  const metaEl = step.querySelector('.timeline-meta');
  const detailsEl = step.querySelector('.timeline-details');

  titleEl.textContent = STAGE_LABELS[event.stage] || event.stage;
  metaEl.textContent = event.iteration > 1 ? `Loop ${event.iteration}` : '';

  if (event.status === 'active') {
    step.dataset.status = 'active';
  } else {
    const failed = event.stage === 'judging' && event.details?.judge_status === 'FAIL';
    step.dataset.status = failed ? 'fail' : 'complete';
    detailsEl.innerHTML = formatStageDetails(event.stage, event.details || {});
    pipelineRun.iteration = Math.max(pipelineRun.iteration, event.iteration);
  }

  if (event.status === 'complete') {
    step.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
}

function expandTimelineStep(step, expanded) {
  const header = step.querySelector('.timeline-header');
  const details = step.querySelector('.timeline-details');
  header.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  details.hidden = !expanded;
  step.classList.toggle('expanded', expanded);
}

function toggleTimelineStep(step) {
  const header = step.querySelector('.timeline-header');
  const expanded = header.getAttribute('aria-expanded') === 'true';
  expandTimelineStep(step, !expanded);
}

function formatStageDetails(stage, details) {
  const rows = [];

  const add = (label, value) => {
    if (value === undefined || value === null || value === '') return;
    rows.push(`<div class="tl-detail"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`);
  };

  switch (stage) {
    case 'collecting_context':
      add('Snapshot', prettyJson(details.snapshot));
      add('Snapshot turn count', details.snapshot_turn_count);
      add('Hot messages', details.hot_message_count);
      break;
    case 'rewriting':
      add('Rewritten query', details.rewritten_query);
      add('Snapshot', prettyJson(details.snapshot));
      break;
    case 'orchestrating':
      add('Classification', details.classification);
      add('Rewritten query', details.rewritten_query);
      break;
    case 'retrieving':
      add('Query', details.query);
      add('Dense hits', details.dense_count);
      add('Sparse hits', details.sparse_count);
      add('Fused chunks', details.chunk_count);
      if (Array.isArray(details.chunks) && details.chunks.length) {
        const chunkHtml = details.chunks.map((c) =>
          `<div class="chunk-preview"><strong>${escapeHtml(c.title || c.chunk_id)}</strong><p>${escapeHtml(c.snippet)}</p></div>`
        ).join('');
        rows.push(`<div class="tl-detail tl-detail-block"><dt>Chunks</dt><dd class="tl-chunks">${chunkHtml}</dd></div>`);
      }
      break;
    case 'drafting':
      add('Draft answer', details.draft_answer);
      break;
    case 'judging':
      add('Verdict', details.judge_status);
      add('Reasoning', details.judge_reasoning);
      add('Retry count', details.retry_count);
      add('Will retry', details.will_retry ? 'Yes' : 'No');
      add('Max retries reached', details.reached_max_retries ? 'Yes' : 'No');
      if (Array.isArray(details.loop_traces) && details.loop_traces.length) {
        add('Loop traces', JSON.stringify(details.loop_traces, null, 2));
      }
      break;
    case 'responding':
      add('Response', details.response);
      break;
    default:
      add('Details', JSON.stringify(details, null, 2));
  }

  return rows.length ? `<dl class="tl-details-list">${rows.join('')}</dl>` : '<p class="tl-detail-empty">No details yet.</p>';
}

function renderLoopSummary(event) {
  const summary = document.createElement('div');
  summary.className = 'timeline-summary';
  summary.innerHTML = `
    <h3>Run complete</h3>
    <dl class="tl-details-list">
      <div class="tl-detail"><dt>Classification</dt><dd>${escapeHtml(event.classification || '—')}</dd></div>
      <div class="tl-detail"><dt>Iterations</dt><dd>${escapeHtml(String(event.total_iterations ?? '—'))}</dd></div>
      <div class="tl-detail"><dt>Max retries hit</dt><dd>${event.reached_max_retries ? 'Yes' : 'No'}</dd></div>
    </dl>
  `;
  pipelineStages.appendChild(summary);
}

function appendPipelineError(message) {
  const el = document.createElement('div');
  el.className = 'pipeline-error';
  el.textContent = message;
  pipelineStages.appendChild(el);
}

function prettyJson(value) {
  if (!value) return '';
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return String(value);
  }
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ---------------------------------------------------------------------------
// API Interaction
// ---------------------------------------------------------------------------

async function loadHistory() {
  try {
    const res = await fetch(`/api/session/${currentSessionId}`);
    if (!res.ok) return;
    const data = await res.json();

    if (data.messages && data.messages.length > 0) {
      welcomeScreen.style.display = 'none';
      messagesContainer.innerHTML = '';
      data.messages.forEach(msg => {
        appendMessage(msg.role, msg.content, false);
      });
      scrollToBottom();
    }
  } catch (err) {
    console.error("Failed to load history", err);
  }
}

async function sendMessage(textOverride = null) {
  if (isWaitingForReply) return;

  const text = textOverride || userInput.value.trim();
  if (!text) return;

  welcomeScreen.style.display = 'none';
  appendMessage('user', text, true);
  userInput.value = '';
  autoResize(userInput);

  setBusyState(true);
  const typingId = showTypingIndicator();
  scrollToBottom();

  try {
    await ensurePipelineSocket();
    resetPipelinePanel(false);

    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: currentSessionId,
        message: text
      })
    });

    removeElement(typingId);

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `HTTP error ${res.status}`);
    }

    const data = await res.json();
    appendMessage('assistant', data.reply, true);

  } catch (err) {
    removeElement(typingId);
    appendMessage('assistant', "⚠️ Sorry, I encountered an error. Please try again.", true);
    setPipelineBadge('error', 'Error');
    console.error(err);
  } finally {
    setBusyState(false);
    scrollToBottom();
    if (window.innerWidth > 768) userInput.focus();
  }
}

// ---------------------------------------------------------------------------
// UI Helpers
// ---------------------------------------------------------------------------

function sendSuggestion(text) {
  sendMessage(text);
}

function appendMessage(role, content, animate = false) {
  const div = document.createElement('div');
  div.className = `message msg-${role}`;

  if (role === 'assistant') {
    div.innerHTML = `
      <div class="msg-avatar">🤖</div>
      <div class="msg-content">${formatMarkdown(content)}</div>
    `;
  } else {
    div.textContent = content;
  }

  if (!animate) {
    div.style.animation = 'none';
  }

  messagesContainer.appendChild(div);
}

function showTypingIndicator() {
  const id = 'typing-' + Date.now();
  const div = document.createElement('div');
  div.id = id;
  div.className = 'typing-indicator';
  div.innerHTML = '<span class="typing-label">Thinking…</span>';
  messagesContainer.appendChild(div);
  return id;
}

function removeElement(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function scrollToBottom() {
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function setBusyState(isBusy) {
  isWaitingForReply = isBusy;
  sendBtn.disabled = isBusy;
  userInput.disabled = isBusy;
}

function autoResize(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = (textarea.scrollHeight) + 'px';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function toggleSidebar() {
  sidebar.classList.toggle('open');
}

// ---------------------------------------------------------------------------
// Knowledge base upload
// ---------------------------------------------------------------------------
function setIngestStatus(message, variant = '') {
  ingestStatus.textContent = message || '';
  ingestStatus.className = variant || '';
}

function setIngestBusy(isBusy) {
  ingestBtn.disabled = isBusy;
}

function triggerIngestPicker() {
  if (ingestFileInput) {
    ingestFileInput.value = '';
    ingestFileInput.click();
  }
}

function handleIngestFileSelect(event) {
  const file = event.target.files && event.target.files[0];
  if (file) {
    uploadIngestFile(file);
  }
}

function clearIngestPoll() {
  if (ingestPollTimer) {
    clearInterval(ingestPollTimer);
    ingestPollTimer = null;
  }
}

async function pollIngestStatus(eventId, filename) {
  clearIngestPoll();

  const poll = async () => {
    try {
      const response = await fetch(`/api/ingest/status/${eventId}`);
      if (!response.ok) {
        throw new Error('Could not check ingestion status.');
      }

      const data = await response.json();
      if (data.status === 'processing') {
        const total = data.images_total || 0;
        const done = data.images_processed || 0;
        const progress = total > 0 ? ` (${done}/${total} images)` : '';
        setIngestStatus(`Processing ${filename}${progress}… You can keep chatting.`, 'processing');
        return;
      }

      clearIngestPoll();
      setIngestBusy(false);

      if (data.status === 'success') {
        const chunks = data.chunk_count ?? 0;
        setIngestStatus(`Added ${filename} (${chunks} chunks indexed).`, 'success');
        return;
      }

      if (data.status === 'rejected') {
        setIngestStatus(data.error || 'File is not football-related and was rejected.', 'error');
        return;
      }

      setIngestStatus(data.error || `Failed to ingest ${filename}.`, 'error');
    } catch (err) {
      clearIngestPoll();
      setIngestBusy(false);
      setIngestStatus(err.message || 'Ingestion status check failed.', 'error');
    }
  };

  await poll();
  ingestPollTimer = setInterval(poll, 2500);
}

async function uploadIngestFile(file) {
  clearIngestPoll();
  setIngestBusy(true);
  setIngestStatus(`Uploading ${file.name}…`, 'processing');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('/api/ingest', {
      method: 'POST',
      body: formData,
    });

    let data = null;
    try {
      data = await response.json();
    } catch (_) {
      data = null;
    }

    if (response.status === 202 && data && data.status === 'processing') {
      setIngestStatus(data.message || `Processing ${file.name} in the background…`, 'processing');
      await pollIngestStatus(data.event_id, file.name);
      return;
    }

    setIngestBusy(false);

    if (response.ok && data && data.status === 'success') {
      const chunks = data.chunks_indexed ?? 0;
      setIngestStatus(`Added ${file.name} (${chunks} chunks indexed).`, 'success');
      return;
    }

    const detail = data && data.detail ? data.detail : data;
    const message = typeof detail === 'string'
      ? detail
      : (detail && (detail.message || detail.error)) || `Upload failed (${response.status}).`;

    setIngestStatus(message, 'error');
  } catch (err) {
    setIngestBusy(false);
    setIngestStatus(err.message || 'Upload failed.', 'error');
  } finally {
    if (ingestFileInput) {
      ingestFileInput.value = '';
    }
  }
}

function formatMarkdown(text) {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  html = html.replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  html = html.replace(/^---+$/gm, '<hr/>');
  html = html.replace(/^[\*\-] (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/^⚠️ WARNING: (.+)$/gm,
    '<div class="msg-warning">⚠️ <strong>WARNING:</strong> $1</div>');
  html = html.replace(/\n\n/g, '</p><p>');
  html = html.replace(/\n/g, '<br/>');

  return `<p>${html}</p>`;
}

document.addEventListener('DOMContentLoaded', init);
