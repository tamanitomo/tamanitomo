/* One persistent composer. Navigation never interrupts a streaming reply.
   Hermes owns the transcript; browser storage holds only the draft and session. */
(function () {
  'use strict';

  const state = {open: false, busy: false, loaded: false, loading: false, cursor: null, unseen: false, recovering: false};
  let root, log, box, send, status, historyButton;
  let scope = '', rows = [];
  const stored = (kind) => {
    try { return sessionStorage.getItem(chatKey(kind)) || ''; } catch (_) { return ''; }
  };
  const save = (kind, value) => {
    try { sessionStorage.setItem(chatKey(kind), value); } catch (_) { /* Private browsing may deny storage. */ }
  };
  const nearBottom = () => log.scrollHeight - log.scrollTop - log.clientHeight < 100;
  const scrollBottom = () => { log.scrollTop = log.scrollHeight; };
  const cleanReply = (text) => String(text || '').replace(/<(think|reasoning)>[\s\S]*?(<\/\1>|$)/gi, '');

  function mount() {
    if (root) return;
    document.body.insertAdjacentHTML('beforeend', `
      <aside id="chat-dock" class="chat-dock" hidden aria-label="Companion chat">
        <button type="button" id="chat-dock-launcher" class="chat-dock-launcher"
          aria-controls="chat-dock-panel" aria-expanded="false" aria-label="Open chat">
          ${icon('chat')}<span class="chat-dock-launcher-label">Chat</span>
          <span class="chat-dock-unread" hidden aria-label="New reply"></span>
        </button>
        <section id="chat-dock-panel" class="chat-dock-panel" role="region"
          aria-labelledby="chat-dock-title" hidden>
          <header class="chat-dock-header">
            <span class="chat-dock-face"></span>
            <div class="chat-dock-heading"><strong id="chat-dock-title"></strong>
              <span class="chat-dock-presence">A continuing conversation</span></div>
            <button type="button" class="chat-dock-control" id="chat-dock-minimise"
              aria-label="Minimize chat" title="Minimize chat">−</button>
            <button type="button" class="chat-dock-control" id="chat-dock-close"
              aria-label="Close chat" title="Close chat">${icon('close')}</button>
          </header>
          <button type="button" id="chat-dock-history" class="chat-dock-history" hidden>Earlier messages</button>
          <div id="chat-dock-log" class="chat-log chat-dock-log" role="log"
            aria-label="Conversation" aria-live="polite" aria-relevant="additions"></div>
          <form id="chat-form" class="chat-composer chat-dock-composer">
            <label class="sr-only" for="chat-message">Your message</label>
            <textarea id="chat-message" rows="1" required maxlength="30000" placeholder="Message your companion"></textarea>
            <button id="send-message" class="chat-send" type="submit" aria-label="Send message">${icon('arrow_right')}</button>
          </form>
          <p id="chat-dock-status" class="chat-dock-status" role="status">Enter to send · Shift+Enter for a new line</p>
        </section>
      </aside>`);
    root = $('chat-dock');
    log = $('chat-dock-log');
    box = $('chat-message');
    send = $('send-message');
    status = $('chat-dock-status');
    historyButton = $('chat-dock-history');
    $('chat-dock-launcher').onclick = open;
    $('chat-dock-minimise').onclick = () => collapse(false);
    $('chat-dock-close').onclick = () => collapse(true);
    historyButton.onclick = () => loadHistory(Boolean(state.cursor));
    $('chat-form').onsubmit = submit;
    box.oninput = () => { save('draft', box.value); grow(); };
    box.onkeydown = (event) => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        if (!send.disabled) $('chat-form').requestSubmit();
      }
    };
    root.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') { event.preventDefault(); collapse(false); }
    });
    if (typeof mountBrowserVoice === 'function') mountBrowserVoice();
  }

  function grow() {
    box.style.height = 'auto';
    box.style.height = Math.min(box.scrollHeight, 128) + 'px';
  }

  function sync() {
    mount();
    const available = Boolean(PROFILE && roster.find((profile) => profile.id === PROFILE)?.installed);
    root.hidden = !available;
    if (!available) return;
    const nextScope = INSTALLATION + ':' + PROFILE;
    if (scope !== nextScope) {
      scope = nextScope;
      rows = [];
      state.loaded = false;
      state.busy = false;
      state.loading = false;
      state.recovering = false;
      box.readOnly = false;
      send.disabled = false;
      state.cursor = null;
      box.value = stored('draft');
      chatSession = stored('session') || null;
      renderRows();
    }
    $('chat-dock-title').textContent = chatName();
    root.querySelector('.chat-dock-face').innerHTML = faceHtml(chatName(), 'chat-dock-avatar');
    box.placeholder = 'Message ' + chatName();
    $('chat-dock-launcher').setAttribute('aria-label', 'Chat with ' + chatName() + (state.unseen ? ', new reply' : ''));
    root.querySelector('.chat-dock-unread').hidden = !state.unseen;
    root.querySelector('.chat-dock-launcher-label').textContent = state.busy ? 'Replying…' : state.unseen ? 'New reply' : 'Chat';
    if (stored('operation') && !state.busy && !state.recovering) resume();
  }

  function open() {
    sync();
    if (root.hidden) return;
    state.open = true;
    state.unseen = false;
    root.classList.remove('is-closed');
    $('chat-dock-panel').hidden = false;
    $('chat-dock-launcher').hidden = true;
    $('chat-dock-launcher').setAttribute('aria-expanded', 'true');
    if (!state.busy) box.value = stored('draft');
    sync();
    grow();
    scrollBottom();
    box.focus({preventScroll: true});
    if (!state.loaded && !state.loading) loadHistory(false);
  }

  function collapse(closed) {
    state.open = false;
    root.classList.toggle('is-closed', closed);
    $('chat-dock-panel').hidden = true;
    $('chat-dock-launcher').hidden = false;
    $('chat-dock-launcher').setAttribute('aria-expanded', 'false');
    if (typeof stopBrowserVoice === 'function') stopBrowserVoice();
    sync();
    $('chat-dock-launcher').focus({preventScroll: true});
  }

  function renderRows() {
    chatLastDay = '';
    log.innerHTML = rows.length ? chatMessagesHtml(rows) : '<p class="chat-dock-empty">A little space to talk, wherever you are.</p>';
  }

  async function loadHistory(older) {
    if (state.loading || (older && !state.cursor)) return;
    state.loading = true;
    const capturedScope = scope;
    const height = log.scrollHeight, top = log.scrollTop;
    historyButton.disabled = true;
    historyButton.hidden = false;
    historyButton.textContent = 'Reading conversation…';
    // Finish the short history read before appending an optimistic turn.
    send.disabled = true;
    try {
      const page = await api('/feed?limit=60' + (older ? '&before=' + encodeURIComponent(state.cursor) : ''));
      if (scope !== capturedScope) return;
      rows = older ? [...(page.messages || []), ...rows] : (page.messages?.length ? page.messages : rows);
      state.cursor = page.next_cursor || null;
      state.loaded = true;
      if (!chatSession && page.session) {
        chatSession = page.session;
        save('session', chatSession);
      }
      renderRows();
      if (older) log.scrollTop = top + log.scrollHeight - height;
      else scrollBottom();
      historyButton.hidden = !state.cursor;
      historyButton.textContent = 'Earlier messages';
    } catch (error) {
      if (scope !== capturedScope) return;
      status.textContent = 'History unavailable: ' + error.message;
      historyButton.textContent = 'Retry conversation history';
    } finally {
      if (scope !== capturedScope) return;
      state.loading = false;
      historyButton.disabled = false;
      send.disabled = state.busy;
    }
  }

  /* Decode SSE by frame, not by network chunk: UTF-8 characters and CRLF lines can
     be split across reads. An incomplete response is never mistaken for success. */
  async function readStream(response, receive) {
    if (!response.body) throw Error('This browser cannot read the reply stream.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const frames = () => {
      let boundary;
      while ((boundary = buffer.search(/\r?\n\r?\n/)) !== -1) {
        const match = buffer.slice(boundary).match(/^\r?\n\r?\n/)[0];
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + match.length);
        let name = 'message';
        const data = [];
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith('event:')) name = line.slice(6).trim();
          if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
        }
        if (data.length) receive(name, JSON.parse(data.join('\n')));
      }
    };
    try {
      while (true) {
        const {done, value} = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
        frames();
        if (done) break;
      }
    } catch (error) {
      await reader.cancel().catch(() => {});
      throw error;
    } finally { reader.releaseLock(); }
  }

  async function readOperation(id, receive, capturedScope) {
    let seen = '';
    while (scope === capturedScope) {
      const row = await api('/operations/' + encodeURIComponent(id));
      if (scope !== capturedScope) return;
      if (row.stream_text && row.stream_text !== seen) {
        const next = String(row.stream_text);
        receive('progress', {text: next});
        seen = next;
      }
      if (row.status === 'complete') { receive('final', row.result || {}); return; }
      if (row.status === 'failed' || row.error) { receive('error', {error: row.error || 'The reply could not finish.'}); return; }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }

  async function resume() {
    state.recovering = true;
    const capturedScope = scope;
    try {
      if (!state.loaded) await loadHistory(false);
      if (scope === capturedScope) await submit(null, stored('operation'));
    } finally {
      if (scope === capturedScope) state.recovering = false;
    }
  }

  async function submit(event, operationId = null) {
    event?.preventDefault();
    const restored = Boolean(operationId);
    if (!restored && stored('operation')) { resume(); return; }
    const message = (restored ? stored('draft') : box.value).trim();
    if ((!restored && (!message || send.disabled)) || state.busy) return;
    const capturedScope = scope;
    const sessionKey = chatKey('session'), draftKey = chatKey('draft'), operationStorageKey = chatKey('operation');
    const saveTurn = (key, value) => { try { sessionStorage.setItem(key, value); } catch (_) {} };
    let terminal = false;
    state.busy = true;
    if (!restored) saveTurn(draftKey, box.value);
    send.disabled = true;
    box.readOnly = true;
    box.value = '';
    grow();
    historyButton.disabled = true;
    const user = {role: 'user', content: message, timestamp: Date.now() / 1000, source: 'desktop'};
    const reply = {role: 'assistant', content: '', timestamp: Date.now() / 1000, source: 'desktop'};
    if (!restored) rows.push(user);
    rows.push(reply);
    renderRows();
    const replyNode = log.querySelector('.bubble:last-child .message-body');
    scrollBottom();
    status.classList.remove('is-error');
    status.textContent = restored ? 'Checking the previous reply…' : 'Waiting for ' + chatName() + '…';
    sync();
    let final = null;
    try {
      const headers = {'content-type': 'application/json', accept: 'text/event-stream'};
      if (token) {
        headers['x-tamanitomo-token'] = token;
        headers['x-companion-token'] = token;
      }
      const receive = (name, data) => {
        if (name === 'operation' && data.id) {
          operationId = data.id;
          saveTurn(operationStorageKey, operationId);
        }
        if (name === 'session' && data.id) saveTurn(sessionKey, data.id);
        if (scope !== capturedScope) return;
        if (name === 'delta' || name === 'progress') {
          const follow = nearBottom();
          reply.content = name === 'progress' ? String(data.text || '') : reply.content + String(data.text || '');
          replyNode.textContent = cleanReply(reply.content);
          status.textContent = 'Replying…';
          if (follow) scrollBottom();
        } else if (name === 'session' && data.id) chatSession = data.id;
        else if (name === 'final') { terminal = true; final = data; }
        else if (name === 'error') { terminal = true; throw Error(data.error || data.detail || 'Reply interrupted.'); }
      };
      if (restored) await readOperation(operationId, receive, capturedScope);
      else {
        const response = await fetch(scoped('/api/chat'), {
          method: 'POST', headers, body: JSON.stringify({message, session: chatSession})
        });
        if (!response.ok) {
          const error = await response.json().catch(() => ({}));
          if (response.status === 401 && error.pin_required) { initPinModal(); showPinModal(); }
          terminal = true;
          throw Error(error.detail || error.error || 'Request failed: ' + response.status);
        }
        try { await readStream(response, receive); }
        catch (error) { if (terminal || !operationId) throw error; }
        if (!terminal && operationId) await readOperation(operationId, receive, capturedScope);
      }
      if (scope !== capturedScope) return;
      if (!final) throw Error('The connection ended before the reply finished.');
      if (final.session) { chatSession = final.session; saveTurn(sessionKey, chatSession); }
      const recorded = (final.messages || []).filter((row) => row.role === 'assistant').at(-1);
      reply.content = cleanReply(recorded?.content || final.response || reply.content);
      reply.attachments = recorded?.attachments || [];
      const follow = nearBottom();
      renderRows();
      if (follow) scrollBottom();
      saveTurn(draftKey, '');
      if (restored) await loadHistory(false);
      if (scope !== capturedScope) return;
      state.unseen = !state.open;
      status.textContent = 'Enter to send · Shift+Enter for a new line';
      if (typeof speakBrowserReply === 'function') {
        speakBrowserReply(final).catch((error) => { if (scope === capturedScope) status.textContent = 'Reply received. Voice unavailable: ' + error.message; });
      }
    } catch (error) {
      if (scope !== capturedScope) return;
      if (error.status === 404) terminal = true;
      voiceReplyRequested = false;
      box.value = stored('draft') || message;
      reply.content = cleanReply(reply.content);
      if (!reply.content) rows.pop();
      renderRows();
      status.textContent = error.message + ' Your draft is saved. Review the conversation before retrying.';
      status.classList.add('is-error');
    } finally {
      if (terminal) saveTurn(operationStorageKey, '');
      if (scope !== capturedScope) return;
      state.busy = false;
      send.disabled = false;
      box.readOnly = false;
      historyButton.disabled = false;
      grow();
      const recovering = state.recovering;
      state.recovering = true;
      sync();
      state.recovering = recovering;
    }
  }

  window.ChatDock = {open, minimise: () => collapse(false), sync, readStream,
    get isOpen() { return state.open; }, get busy() { return state.busy; }, get historyLoading() { return state.loading; }};
  const navigate = window.productNavigate;
  window.productNavigate = (name) => { navigate?.(name); sync(); };
  window.addEventListener('appearance-change', sync);
})();
