"""Drive the actual dock controller against delayed read-only feed responses."""

from tests.test_chat_dock import run_browser_contract

HARNESS = r"""
const assert = require('node:assert/strict');
const nodes = new Map(), listeners = new Map(), timers = new Map(), storage = new Map();
let timerId = 0;
class Node {
  constructor(id) {
    this.id = id; this.hidden = false; this.disabled = false; this.dataset = {};
    this.value = ''; this.textContent = ''; this.style = {}; this.rows = [];
    this.scrollTop = 0; this.scrollHeight = 1000; this.clientHeight = 200;
    const classes = new Set();
    this.classList = {add: x => classes.add(x), remove: x => classes.delete(x),
      toggle: (x, on) => on ? classes.add(x) : classes.delete(x)};
  }
  set innerHTML(value) {
    this.html = value;
    try { this.rows = JSON.parse(value); } catch {}
    this.children = [...value.matchAll(/data-message="([^"]+)"/g)].map(match => {
      const n = new Node('result'); n.dataset.message = match[1]; return n;
    });
  }
  get innerHTML() { return this.html || ''; }
  setAttribute(key, value) { this[key] = value; }
  addEventListener(key, fn) { this['on' + key] = fn; }
  focus() {}
  getBoundingClientRect() { return {top: 0, bottom: 200}; }
  querySelector(query) {
    if (query === '.bubble:last-child .message-body') return node('streamed');
    return node(this.id + query);
  }
  querySelectorAll(query) {
    if (query === '[data-message]') return this.children || [];
    return [];
  }
}
function node(id) { if (!nodes.has(id)) nodes.set(id, new Node(id)); return nodes.get(id); }
global.$ = node;
global.document = {
  hidden: false,
  body: {insertAdjacentHTML(_, html) {
    for (const match of html.matchAll(/id="([^"]+)"/g)) node(match[1]);
  }},
  addEventListener(kind, fn) { listeners.set('document:' + kind, fn); }
};
global.window = {addEventListener(kind, fn) { listeners.set(kind, fn); }};
global.setTimeout = fn => { timers.set(++timerId, fn); return timerId; };
global.clearTimeout = id => timers.delete(id);
global.sessionStorage = {getItem: k => storage.get(k), setItem: (k, v) => storage.set(k, v)};
global.INSTALLATION = 'test-install'; global.PROFILE = 'nova';
global.roster = [{id: 'nova', installed: true}, {id: 'rowan', installed: true}];
global.chatKey = kind => PROFILE + ':' + kind;
global.chatSession = null; global.chatLastDay = ''; global.token = ''; global.voiceReplyRequested = false;
global.chatName = () => PROFILE;
global.icon = () => ''; global.faceHtml = () => '';
global.esc = s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;');
global.chatMessagesHtml = rows => JSON.stringify(rows);
global.scoped = value => value;
const requests = [];
const row = (id, content = 'message ' + id) => ({id: String(id), source_message: String(id), content,
  revision: content, timestamp: id, cursor: 'cursor-' + id, role: 'assistant', session: 'web', channel: 'workspace'});
global.api = async path => ({messages: [row(1), row(2)], latest_cursor: 'cursor-2', next_cursor: 'older', session: 'web'});
global.post = async (path, data) => {
  requests.push([path, data]);
  return {messages: [], removed: [], after: data.after, more: false};
};
global.fetch = async () => { throw Error('A read must never send a chat turn'); };
const flush = async () => { for (let n = 0; n < 20; n++) await Promise.resolve(); };
require('./kit/app/static/chat-dock.js');
const dock = window.ChatDock;
"""


def test_incoming_sync_preserves_draft_session_scroll_and_reconciles_removals():
    run_browser_contract(HARNESS + r"""
(async () => {
  storage.set('nova:session', 'my-device-session');
  dock.open(); await flush();
  node('chat-message').value = 'unfinished reply'; node('chat-message').oninput();
  node('chat-dock-log').scrollTop = 123;
  global.post = async (path, data) => {
    requests.push([path, data]);
    return {messages: [row(1, 'edited elsewhere'), row(3, 'from Telegram')], removed: ['2'], after: 'cursor-3', more: false, session: 'never-adopt-this'};
  };
  await dock.refresh();
  assert.deepEqual(node('chat-dock-log').rows.map(r => r.content), ['edited elsewhere', 'from Telegram']);
  assert.equal(node('chat-message').value, 'unfinished reply');
  assert.equal(storage.get('nova:draft'), 'unfinished reply');
  assert.equal(chatSession, 'my-device-session');
  assert.equal(node('chat-dock-log').scrollTop, 123);
  assert.equal(node('chat-dock-new').hidden, false);
  assert.deepEqual(Object.keys(requests[0][1].known), ['1', '2']);
  node('chat-dock-new').onclick();
  assert.equal(node('chat-dock-new').hidden, true);
  global.post = async (_, data) => ({messages: [], removed: ['1', '3'], after: data.after, more: false});
  await dock.refresh();
  assert.ok(node('chat-dock-log').innerHTML.includes('A little space to talk'));
})().catch(error => {console.error(error); process.exitCode = 1;});
""")


def test_sync_ignores_profile_switch_away_and_back_and_refreshes_on_reconnect():
    run_browser_contract(HARNESS + r"""
(async () => {
  dock.open(); await flush();
  let finish;
  global.post = () => new Promise(resolve => { finish = resolve; });
  const pending = dock.refresh(); await flush();
  PROFILE = 'rowan'; dock.sync();
  PROFILE = 'nova'; dock.sync();
  finish({messages: [row(99, 'stale response')], removed: [], after: 'cursor-99', more: false});
  await pending;
  assert.ok(!node('chat-dock-log').innerHTML.includes('stale response'));
  let reads = 0;
  global.api = async () => { reads++; return {messages: [row(4)], latest_cursor: 'cursor-4', next_cursor: null}; };
  global.post = async () => { reads++; return {messages: [row(5)], removed: [], after: 'cursor-5', more: false}; };
  listeners.get('online')(); await flush();
  assert.equal(reads, 1);
  document.hidden = true;
  listeners.get('document:visibilitychange')();
  assert.equal(timers.size, 0);
  document.hidden = false;
  listeners.get('document:visibilitychange')(); await flush();
  assert.equal(reads, 2);
  assert.ok(timers.size > 0);
})().catch(error => {console.error(error); process.exitCode = 1;});
""")


def test_stale_refresh_cannot_overwrite_streaming_reply_or_repeat_chat():
    run_browser_contract(HARNESS + r"""
(async () => {
  dock.open(); await flush();
  let finishRead, finishTurn, sends = 0;
  global.post = () => new Promise(resolve => { finishRead = resolve; });
  const pending = dock.refresh(); await flush();
  global.fetch = async () => {
    sends++;
    return {ok: true, body: new ReadableStream({start(controller) { finishTurn = controller; }})};
  };
  node('chat-message').value = 'run once';
  const turn = node('chat-form').onsubmit({preventDefault() {}});
  await flush();
  finishRead({messages: [row(99, 'old read')], removed: ['1'], after: 'cursor-99', more: false});
  await pending;
  assert.ok(!node('chat-dock-log').innerHTML.includes('old read'));
  assert.equal(dock.busy, true);
  global.post = async (_, data) => ({messages: [row(3, 'run once'), row(4, 'completed')], removed: [], after: 'cursor-4', more: false});
  finishTurn.enqueue(new TextEncoder().encode('event: final\ndata: {"response":"completed","session":"web"}\n\n'));
  finishTurn.close(); await turn; await flush();
  assert.equal(sends, 1);
  assert.equal(dock.busy, false);
  assert.equal(node('chat-message').value, '');
  assert.equal(node('chat-dock-log').rows.filter(r => !r.id).length, 0);
  assert.equal(node('chat-dock-log').rows.at(-1).content, 'completed');
})().catch(error => {console.error(error); process.exitCode = 1;});
""")


def test_search_preserves_draft_and_session_and_escapes_result_text():
    run_browser_contract(HARNESS + r"""
(async () => {
  storage.set('nova:session', 'my-session');
  dock.open(); await flush();
  node('chat-message').value = 'keep this draft'; node('chat-message').oninput();
  node('chat-dock-find').onclick();
  node('chat-search-text').value = 'exact %_';
  node('chat-search-day').value = '2026-10-09';
  node('chat-search-channel').value = 'telegram';
  const paths = [];
  global.api = async path => {
    paths.push(path);
    if (path.includes('/context/')) return {messages: [row(7)], selected: '7'};
    return {matches: [{...row(7), excerpt: '<img onerror="bad">', channel: 'telegram'}], next_cursor: null, timezone: 'UTC'};
  };
  node('chat-search-form').onsubmit({preventDefault() {}}); await flush();
  assert.ok(paths[0].includes('query=exact+%25_'));
  assert.ok(paths[0].includes('day=2026-10-09'));
  assert.ok(paths[0].includes('channel=telegram'));
  assert.ok(node('chat-search-results').innerHTML.includes('&lt;img'));
  node('chat-search-results').children[0].onclick(); await flush();
  assert.equal(paths[1], '/feed/context/7');
  assert.equal(chatSession, 'my-session');
  assert.equal(node('chat-message').value, 'keep this draft');
  assert.equal(storage.get('nova:draft'), 'keep this draft');
  node('chat-search-back').onclick();
  assert.equal(node('chat-dock-log').hidden, false);
})().catch(error => {console.error(error); process.exitCode = 1;});
""")


def test_search_only_results_and_context_neighbors_are_revalidated_for_removal():
    run_browser_contract(HARNESS + r"""
(async () => {
  dock.open(); await flush();
  node('chat-message').value = 'keep draft'; node('chat-message').oninput();
  node('chat-dock-find').onclick(); node('chat-search-text').value = 'private';
  global.api = async path => path.includes('/context/')
    ? {messages: [row(6, 'private neighboring message'), row(7, 'private selected message')], selected: '7'}
    : {matches: [{...row(7, 'private selected message'), excerpt: 'private search excerpt'}], next_cursor: null, timezone: 'UTC'};
  node('chat-search-form').onsubmit({preventDefault() {}}); await flush();
  node('chat-search-results').children[0].onclick(); await flush();
  assert.ok(node('chat-search-results').innerHTML.includes('private neighboring message'));
  let checked = false;
  global.post = async (_, data) => {
    if ('6' in data.known) {
      checked = true; assert.ok('7' in data.known);
      return {messages: [], removed: ['6'], after: data.after, more: false};
    }
    return {messages: [], removed: [], after: data.after, more: false};
  };
  await dock.refresh();
  assert.equal(checked, true);
  assert.ok(!node('chat-search-results').innerHTML.includes('private'));
  assert.match(node('chat-search-status').textContent, /Search again/);
  assert.deepEqual(node('chat-dock-log').rows.map(r => r.id), ['1', '2']);
  assert.equal(node('chat-message').value, 'keep draft');
  node('chat-search-return').onclick();
  assert.ok(!node('chat-search-results').innerHTML.includes('private search excerpt'));
})().catch(error => {console.error(error); process.exitCode = 1;});
""")


def test_edited_cached_search_text_is_cleared_without_inserting_old_rows_into_feed():
    run_browser_contract(HARNESS + r"""
(async () => {
  dock.open(); await flush();
  node('chat-dock-find').onclick(); node('chat-search-text').value = 'retired claim';
  global.api = async () => ({matches: [{...row(7, 'retired claim'), excerpt: 'retired claim'}], next_cursor: null, timezone: 'UTC'});
  node('chat-search-form').onsubmit({preventDefault() {}}); await flush();
  global.post = async (_, data) => ({messages: '7' in data.known ? [row(7, 'corrected claim')] : [], removed: [], after: data.after, more: false});
  await dock.refresh();
  assert.ok(!node('chat-search-results').innerHTML.includes('retired claim'));
  assert.deepEqual(node('chat-dock-log').rows.map(r => r.id), ['1', '2']);
})().catch(error => {console.error(error); process.exitCode = 1;});
""")
