/* One persistent composer. Navigation never interrupts a streaming reply.
   Hermes owns the transcript; browser storage holds only the draft and session. */
(function () {
  'use strict';

  const state = {open: false, busy: false, loaded: false, loading: false, cursor: null, latest: null, unseen: false, recovering: false, refreshing: 0};
  let root, log, box, send, status, historyButton;
  let scope = '', scopeVersion = 0, readEpoch = 0, rows = [], refreshTimer;
  let searchEpoch = 0, searchCursor = null, searchMatches = [], searchContextRows = [], searchParams = null;
  const scopeKey = () => scope + ':' + scopeVersion;
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
            <button type="button" class="chat-dock-control" id="chat-dock-find"
              aria-label="Search conversation" title="Search conversation" aria-expanded="false">${icon('search')}</button>
            <button type="button" class="chat-dock-control" id="chat-dock-minimise"
              aria-label="Minimize chat" title="Minimize chat">−</button>
            <button type="button" class="chat-dock-control" id="chat-dock-close"
              aria-label="Close chat" title="Close chat">${icon('close')}</button>
          </header>
          <button type="button" id="chat-dock-history" class="chat-dock-history" hidden>Earlier messages</button>
          <button type="button" id="chat-dock-new" class="chat-dock-history" hidden>New messages ↓</button>
          <div id="chat-dock-log" class="chat-log chat-dock-log" role="log"
            aria-label="Conversation" aria-live="polite" aria-relevant="additions"></div>
          <section id="chat-dock-search" class="chat-dock-search" aria-label="Search conversation" hidden>
            <form id="chat-search-form" class="chat-search-form">
              <label class="sr-only" for="chat-search-text">Exact text</label>
              <input id="chat-search-text" type="search" maxlength="200" placeholder="Find exact text…">
              <div class="chat-search-filters">
                <label>Day<input id="chat-search-day" type="date"></label>
                <label>Channel<select id="chat-search-channel"><option value="all">All channels</option><option value="workspace">Tamanitomo</option><option value="terminal">Terminal</option><option value="telegram">Telegram</option></select></label>
                <button class="quiet" type="submit">Find</button>
              </div>
            </form>
            <p id="chat-search-status" class="dim small" role="status">Search text, a day, or a channel. Dates use your companion’s timezone.</p>
            <div id="chat-search-results" class="chat-search-results"></div>
            <button type="button" id="chat-search-more" class="chat-dock-history" hidden>More results</button>
            <button type="button" id="chat-search-back" class="chat-dock-history">Back to conversation</button>
          </section>
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
    $('chat-dock-find').onclick = () => setSearch($('chat-dock-search').hidden);
    $('chat-search-back').onclick = () => setSearch(false);
    $('chat-search-form').onsubmit = event => { event.preventDefault(); searchHistory(false); };
    $('chat-search-more').onclick = () => searchHistory(true);
    $('chat-dock-new').onclick = () => { setSearch(false); scrollBottom(); clearUnread(); };
    log.addEventListener('scroll', () => { if (state.open && nearBottom()) clearUnread(); });
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
    if (!available) {
      scope = '';
      scopeVersion++;
      readEpoch++;
      clearTimeout(refreshTimer);
      return;
    }
    const nextScope = INSTALLATION + ':' + PROFILE;
    if (scope !== nextScope) {
      scope = nextScope;
      scopeVersion++;
      readEpoch++;
      searchEpoch++;
      rows = [];
      state.loaded = false;
      state.busy = false;
      state.loading = false;
      state.recovering = false;
      box.readOnly = false;
      send.disabled = false;
      state.cursor = null;
      state.latest = null;
      state.unseen = false;
      state.refreshing = 0;
      searchCursor = null;
      searchMatches = [];
      searchContextRows = [];
      searchParams = null;
      $('chat-search-text').value = '';
      $('chat-search-day').value = '';
      $('chat-search-channel').value = 'all';
      $('chat-search-results').innerHTML = '';
      setSearch(false);
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
    $('chat-dock-new').hidden = !state.unseen || !state.open || !$('chat-dock-search').hidden;
    if (stored('operation') && !state.busy && !state.recovering) resume();
    scheduleRefresh();
  }

  function open() {
    sync();
    if (root.hidden) return;
    state.open = true;
    state.unseen = false;
    root.classList.remove('is-closed');
    root.classList.add('is-open');
    $('chat-dock-panel').hidden = false;
    $('chat-dock-launcher').hidden = true;
    $('chat-dock-launcher').setAttribute('aria-expanded', 'true');
    if (!state.busy) box.value = stored('draft');
    sync();
    grow();
    scrollBottom();
    box.focus({preventScroll: true});
    if (!state.loaded && !state.loading) loadHistory(false);
    else refreshHistory();
  }

  function collapse(closed) {
    state.open = false;
    root.classList.toggle('is-closed', closed);
    root.classList.remove('is-open');
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

  function clearUnread() {
    if (!state.unseen) return;
    state.unseen = false;
    sync();
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    if (root?.hidden || typeof document === 'undefined' || document.hidden) return;
    refreshTimer = setTimeout(async () => {
      await refreshHistory();
      scheduleRefresh();
    }, state.open ? 5000 : 15000);
  }

  function scrollAnchor() {
    const top = log.getBoundingClientRect().top;
    const node = [...log.querySelectorAll('[data-source-message]')]
      .find(el => el.getBoundingClientRect().bottom > top);
    return {id: node?.dataset.sourceMessage, offset: node ? node.getBoundingClientRect().top - top : 0, top: log.scrollTop};
  }

  function restoreAnchor(anchor) {
    const node = [...log.querySelectorAll('[data-source-message]')]
      .find(el => el.dataset.sourceMessage === anchor.id);
    log.scrollTop = node
      ? log.scrollTop + node.getBoundingClientRect().top - log.getBoundingClientRect().top - anchor.offset
      : anchor.top;
  }

  async function refreshHistory() {
    if (!root || root.hidden || document.hidden || state.busy || state.loading || state.refreshing || state.recovering) return;
    if (!state.loaded) return loadHistory(false);
    const capturedScope = scopeKey(), epoch = ++readEpoch;
    state.refreshing = epoch;
    const current = () => scopeKey() === capturedScope && readEpoch === epoch && !state.busy;
    historyButton.disabled = true;
    const knownRows = rows.filter(row => row.id);
    const merged = new Map(knownRows.map(row => [String(row.id), row]));
    const batches = [];
    for (let start = 0; start < knownRows.length; start += 200) batches.push(knownRows.slice(start, start + 200));
    if (!batches.length) batches.push([]);
    let after = state.latest, arrived = false, changed = false, received = false;
    try {
      for (const batch of batches) {
        let known = Object.fromEntries(batch.map(row => [String(row.id), row.revision || '']));
        let more = true, pages = 0;
        while (more && pages++ < 10) {
          const page = await post('/feed/sync', {after, known});
          if (!current()) return;
          for (const id of page.removed || []) changed = merged.delete(String(id)) || changed;
          for (const row of page.messages || []) {
            const previous = merged.get(String(row.id));
            arrived ||= !previous;
            changed ||= !previous || previous.revision !== row.revision;
            merged.set(String(row.id), row);
            received = true;
          }
          after = page.after;
          more = page.more;
          known = {};
        }
      }
      if (!current()) return;
      state.latest = after;
      if (changed) {
        const follow = state.open && $('chat-dock-search').hidden && nearBottom();
        const anchor = scrollAnchor();
        // Server records replace optimistic bubbles once the submitted turn is recorded.
        const pending = received ? [] : rows.filter(row => !row.id);
        rows = [...merged.values()].sort((a, b) => a.timestamp - b.timestamp || Number(a.id) - Number(b.id));
        rows.push(...pending);
        renderRows();
        if (follow) scrollBottom(); else restoreAnchor(anchor);
        if (arrived && !follow) state.unseen = true;
      }
      // Search can display older messages absent from the loaded feed. Verify
      // those IDs too, including context neighbors, before keeping cached text.
      const searchVersion = searchEpoch;
      const cached = new Map([...searchContextRows, ...searchMatches].map(row => [String(row.id), row.revision || '']));
      const entries = [...cached];
      for (let start = 0; start < entries.length; start += 200) {
        const page = await post('/feed/sync', {after: state.latest, known: Object.fromEntries(entries.slice(start, start + 200))});
        if (!current()) return;
        if (searchEpoch !== searchVersion) break;
        if ((page.removed || []).some(id => cached.has(String(id))) ||
            (page.messages || []).some(row => cached.has(String(row.id)) && cached.get(String(row.id)) !== row.revision)) {
          searchEpoch++;
          searchMatches = []; searchContextRows = []; searchCursor = null;
          renderSearchResults();
          $('chat-search-status').textContent = 'Conversation history changed. Search again to see the current results.';
          break;
        }
      }
      root.querySelector('.chat-dock-presence').textContent = 'A continuing conversation';
    } catch (error) {
      if (current()) {
        root.querySelector('.chat-dock-presence').textContent = 'Updates unavailable · reconnecting';
      }
    } finally {
      if (scopeKey() === capturedScope && state.refreshing === epoch) {
        state.refreshing = 0;
        historyButton.disabled = state.busy || state.loading;
        sync();
      }
    }
  }

  function setSearch(opened) {
    searchEpoch++;
    $('chat-dock-search').hidden = !opened;
    $('chat-dock-log').hidden = opened;
    historyButton.hidden = opened || !state.cursor;
    $('chat-dock-find').setAttribute('aria-expanded', String(opened));
    $('chat-dock-new').hidden = opened || !state.unseen || !state.open;
    if (opened) $('chat-search-text').focus({preventScroll: true});
  }

  function renderSearchResults() {
    searchContextRows = [];
    const host = $('chat-search-results');
    host.innerHTML = searchMatches.map(row => `<button type="button" class="chat-search-result" data-message="${esc(row.id)}">
      <small>${esc(new Date(row.timestamp * 1000).toLocaleString())} · ${esc(row.channel === 'workspace' ? 'Tamanitomo' : row.channel)} · ${esc(row.role === 'user' ? 'You' : chatName())}</small>
      <span>${esc(row.excerpt)}</span><small>Read surrounding messages →</small></button>`).join('');
    for (const button of host.querySelectorAll('[data-message]')) button.onclick = () => searchContext(button.dataset.message);
    $('chat-search-more').hidden = !searchCursor;
  }

  async function searchHistory(older) {
    const epoch = ++searchEpoch, capturedScope = scopeKey();
    const current = () => epoch === searchEpoch && scopeKey() === capturedScope;
    if (!older) {
      searchParams = {query: $('chat-search-text').value.trim(), day: $('chat-search-day').value, channel: $('chat-search-channel').value};
      searchCursor = null;
      searchMatches = [];
      renderSearchResults();
    }
    const params = new URLSearchParams({...searchParams, ...(older && searchCursor ? {before: searchCursor} : {})});
    $('chat-search-status').textContent = 'Searching conversation…';
    $('chat-search-more').disabled = true;
    try {
      const page = await api('/feed/search?' + params);
      if (!current()) return;
      searchMatches.push(...page.matches);
      searchCursor = page.next_cursor;
      renderSearchResults();
      $('chat-search-status').textContent = `${searchMatches.length} result${searchMatches.length === 1 ? '' : 's'}${searchCursor ? ' loaded' : ''} · Dates in ${page.timezone}`;
    } catch (error) {
      if (current()) $('chat-search-status').textContent = error.message;
    } finally {
      if (current()) $('chat-search-more').disabled = false;
    }
  }

  async function searchContext(id) {
    const epoch = ++searchEpoch, capturedScope = scopeKey();
    $('chat-search-status').textContent = 'Reading surrounding messages…';
    try {
      const page = await api('/feed/context/' + encodeURIComponent(id));
      if (epoch !== searchEpoch || scopeKey() !== capturedScope) return;
      searchContextRows = page.messages || [];
      chatLastDay = '';
      $('chat-search-results').innerHTML = '<button type="button" class="chat-dock-history" id="chat-search-return">← Search results</button><div class="chat-log chat-search-context">' + chatMessagesHtml(page.messages) + '</div>';
      $('chat-search-return').onclick = () => { searchEpoch++; renderSearchResults(); $('chat-search-status').textContent = `${searchMatches.length} results`; };
      for (const bubble of $('chat-search-results').querySelectorAll('[data-source-message]')) {
        if (bubble.dataset.sourceMessage === page.selected) bubble.classList.add('is-search-match');
      }
      $('chat-search-more').hidden = true;
      $('chat-search-status').textContent = 'Surrounding messages. Your current conversation and draft stay in place.';
    } catch (error) {
      if (epoch === searchEpoch && scopeKey() === capturedScope) $('chat-search-status').textContent = error.message;
    }
  }

  async function loadHistory(older) {
    if (state.loading || state.refreshing || (older && (!state.cursor || state.busy))) return;
    state.loading = true;
    const capturedScope = scopeKey(), epoch = ++readEpoch;
    const height = log.scrollHeight, top = log.scrollTop;
    historyButton.disabled = true;
    historyButton.hidden = false;
    historyButton.textContent = 'Reading conversation…';
    // Finish the short history read before appending an optimistic turn.
    send.disabled = true;
    try {
      const page = await api('/feed?limit=60' + (older ? '&before=' + encodeURIComponent(state.cursor) : ''));
      if (scopeKey() !== capturedScope || epoch !== readEpoch) return;
      rows = older ? [...(page.messages || []), ...rows] : (page.messages || []);
      state.cursor = page.next_cursor || null;
      if (!older) state.latest = page.latest_cursor || null;
      state.loaded = true;
      if (!chatSession && page.session) {
        chatSession = page.session;
        save('session', chatSession);
      }
      renderRows();
      if (older) log.scrollTop = top + log.scrollHeight - height;
      else scrollBottom();
      historyButton.hidden = !$('chat-dock-search').hidden || !state.cursor;
      historyButton.textContent = 'Earlier messages';
    } catch (error) {
      if (scopeKey() !== capturedScope || epoch !== readEpoch) return;
      status.textContent = 'History unavailable: ' + error.message;
      historyButton.textContent = 'Retry conversation history';
    } finally {
      if (scopeKey() !== capturedScope || epoch !== readEpoch) return;
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
    while (scopeKey() === capturedScope) {
      const row = await api('/operations/' + encodeURIComponent(id));
      if (scopeKey() !== capturedScope) return;
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
    const capturedScope = scopeKey();
    try {
      if (!state.loaded) await loadHistory(false);
      if (scopeKey() === capturedScope) await submit(null, stored('operation'));
    } finally {
      if (scopeKey() === capturedScope) state.recovering = false;
    }
  }

  async function submit(event, operationId = null) {
    event?.preventDefault();
    const restored = Boolean(operationId);
    if (!restored && stored('operation')) { resume(); return; }
    const message = (restored ? stored('draft') : box.value).trim();
    if ((!restored && (!message || send.disabled)) || state.busy) return;
    const capturedScope = scopeKey();
    const sessionKey = chatKey('session'), draftKey = chatKey('draft'), operationStorageKey = chatKey('operation');
    const saveTurn = (key, value) => { try { sessionStorage.setItem(key, value); } catch (_) {} };
    let terminal = false;
    readEpoch++;
    setSearch(false);
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
        if (scopeKey() !== capturedScope) return;
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
      if (scopeKey() !== capturedScope) return;
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
      if (scopeKey() !== capturedScope) return;
      state.unseen = !state.open;
      status.textContent = 'Enter to send · Shift+Enter for a new line';
      if (typeof speakBrowserReply === 'function') {
        speakBrowserReply(final).catch((error) => { if (scopeKey() === capturedScope) status.textContent = 'Reply received. Voice unavailable: ' + error.message; });
      }
    } catch (error) {
      if (scopeKey() !== capturedScope) return;
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
      if (scopeKey() !== capturedScope) return;
      state.busy = false;
      send.disabled = false;
      box.readOnly = false;
      historyButton.disabled = false;
      grow();
      const recovering = state.recovering;
      state.recovering = true;
      sync();
      state.recovering = recovering;
      if (terminal) refreshHistory();
    }
  }

  window.ChatDock = {open, minimise: () => collapse(false), sync, refresh: refreshHistory, readStream,
    get isOpen() { return state.open; }, get busy() { return state.busy; }, get historyLoading() { return state.loading; }};
  const navigate = window.productNavigate;
  window.productNavigate = (name) => { navigate?.(name); sync(); };
  window.addEventListener('appearance-change', sync);
  window.addEventListener('online', () => { refreshHistory(); scheduleRefresh(); });
  window.addEventListener('focus', () => refreshHistory());
  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refreshHistory();
    scheduleRefresh();
  });
})();
