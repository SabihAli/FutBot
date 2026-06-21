// ---------------------------------------------------------------------------
// State Management
// ---------------------------------------------------------------------------
let currentSessionId = localStorage.getItem('futbot_session_id');
let isWaitingForReply = false;

// ---------------------------------------------------------------------------
// DOM Elements
// ---------------------------------------------------------------------------
const messagesContainer = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const welcomeScreen = document.getElementById('welcome-screen');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const sessionIdDisplay = document.getElementById('session-id-display');
const ingestBtn = document.getElementById('ingest-btn');
const ingestLabel = document.getElementById('ingest-label');
const ingestStatus = document.getElementById('ingest-status');
const sidebar = document.getElementById('sidebar');

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------
function init() {
  if (!currentSessionId) {
    newSession();
  } else {
    sessionIdDisplay.textContent = currentSessionId.slice(0, 8) + '...';
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
  
  // Update UI
  welcomeScreen.style.display = 'none';
  appendMessage('user', text, true);
  userInput.value = '';
  autoResize(userInput);
  
  // Show typing indicator
  setBusyState(true);
  const typingId = showTypingIndicator();
  scrollToBottom();
  
  try {
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
      throw new Error(`HTTP error ${res.status}`);
    }
    
    const data = await res.json();
    appendMessage('assistant', data.reply, true);
    
  } catch (err) {
    removeElement(typingId);
    appendMessage('assistant', "⚠️ Sorry, I encountered an error. Please try again.", true);
    console.error(err);
  } finally {
    setBusyState(false);
    scrollToBottom();
    // Re-focus input on desktop
    if (window.innerWidth > 768) userInput.focus();
  }
}

async function triggerIngest() {
  if (ingestBtn.disabled) return;
  
  ingestBtn.disabled = true;
  ingestLabel.textContent = "Syncing...";
  ingestStatus.textContent = "Scraping BBC, Guardian, Sky Sports...";
  
  try {
    const res = await fetch('/api/ingest', { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      ingestStatus.textContent = `Success: Indexed ${data.articles_ingested} articles (${data.total_chunks_indexed} chunks).`;
    } else {
      throw new Error(data.message || 'Ingestion failed');
    }
  } catch (err) {
    ingestStatus.textContent = `Error: ${err.message}`;
  } finally {
    ingestLabel.textContent = "Sync News";
    ingestBtn.disabled = false;
    setTimeout(() => {
      if (ingestStatus.textContent.startsWith('Success')) {
        ingestStatus.textContent = '';
      }
    }, 5000);
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
  div.innerHTML = `
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
  `;
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
  
  if (isBusy) {
    statusDot.className = 'dot yellow';
    statusText.textContent = 'Thinking...';
  } else {
    statusDot.className = 'dot green';
    statusText.textContent = 'Ready';
  }
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

// Full markdown renderer: headings, lists, bold, italic, code, hr
function formatMarkdown(text) {
  // Escape HTML entities first
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Code blocks (```...```)
  html = html.replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre><code>$1</code></pre>');

  // Inline code (`...`)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Headings (must be at start of line)
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Horizontal rule
  html = html.replace(/^---+$/gm, '<hr/>');

  // Unordered lists
  html = html.replace(/^[\*\-] (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');

  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

  // Bold and italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // WARNING block — style distinctly
  html = html.replace(/^⚠️ WARNING: (.+)$/gm,
    '<div class="msg-warning">⚠️ <strong>WARNING:</strong> $1</div>');

  // Paragraphs: double newlines
  html = html.replace(/\n\n/g, '</p><p>');
  // Single newlines
  html = html.replace(/\n/g, '<br/>');

  return `<p>${html}</p>`;
}

// Boot
document.addEventListener('DOMContentLoaded', init);
