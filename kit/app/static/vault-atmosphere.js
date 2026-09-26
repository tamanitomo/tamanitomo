/* Living Archive: additive presentation only.
 * Does not replace renderers, mount/destroy CodeMirror, call APIs, touch note text,
 * read/write browser storage, or alter revision, save, draft or conflict state.
 * Load after vault-editor.js. Removing this file + its stylesheet and reloading restores the UI.
 */
(() => {
  'use strict';
  const root = document.getElementById('vault');
  if (!root || window.VaultAtmosphere) return;
  const book = '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 8C11 4 6 5 3 6v19c5-2 9-1 13 2 4-3 8-4 13-2V6c-3-1-8-2-13 2Zm0 0v19M7 11l5 1M7 16l5 1M20 12l5-1M20 17l5-1"/></svg>';
  const disk = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 11h8M8 17h.01M12 17h4"/></svg>';
  const focusIcon = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 3H3v4m10-4h4v4M3 13v4h4m10-4v4h-4"/></svg>';
  let pending = false;

  function showFiles(show, returnFocus = false) {
    document.body.classList.toggle('vault-files-open', show);
    const trigger = root.querySelector('.va-browse');
    if (trigger) trigger.setAttribute('aria-expanded', String(show));
    if (show) root.querySelector('#vault-query')?.focus();
    else if (returnFocus) trigger?.focus();
  }
  function decorate() {
    pending = false;
    if (!root.querySelector('.obsidian-layout')) return;
    root.dataset.immersive = 'true';
    const views = root.querySelector('.vault-views');
    if (!root.querySelector('.va-masthead')) {
      const masthead = document.createElement('div');
      masthead.className = 'va-masthead';
      masthead.innerHTML = `<div class="va-heading"><div class="va-seal" aria-hidden="true">${book}</div><div><div class="va-eyebrow">The living archive</div><h1>The vault</h1><p>The notes, stories, and details that stay.</p></div></div><div class="va-masthead-actions"><button type="button" class="va-browse" aria-controls="vault-tree" aria-expanded="false">Browse files</button><button type="button" class="va-focus" aria-pressed="false" title="Hide the file rail without closing your notes">${focusIcon}<span>Focus</span></button></div>`;
      root.prepend(masthead);
      const actions = masthead.querySelector('.va-masthead-actions');
      if (views) actions.prepend(views); // move existing elements, preserving listeners
      masthead.querySelector('.va-focus').addEventListener('click', event => {
        const pressed = root.dataset.vaFocus !== 'true';
        root.dataset.vaFocus = String(pressed);
        event.currentTarget.setAttribute('aria-pressed', String(pressed));
        event.currentTarget.querySelector('span').textContent = pressed ? 'Exit focus' : 'Focus';
      });
      masthead.querySelector('.va-browse').addEventListener('click', () => {
        showFiles(!document.body.classList.contains('vault-files-open'));
      });
    }
    const browsing = !root.querySelector('#vault-folders')?.hidden;
    for (const control of root.querySelectorAll('.va-focus, .va-browse')) {
      if (control.hidden === browsing) control.hidden = !browsing;
    }
    const sidebar = root.querySelector('.vault-sidebar');
    const tree = root.querySelector('#vault-tree');
    if (sidebar && tree && !sidebar.querySelector('.va-collections-label')) {
      const label = document.createElement('div');
      label.className = 'va-collections-label';
      label.textContent = 'COLLECTIONS';
      tree.before(label);
      const footer = document.createElement('div');
      footer.className = 'va-rail-footer';
      footer.innerHTML = `${disk}<span>Files on your host.<br>Yours to keep.</span>`;
      sidebar.append(footer);
    }
    const empty = root.querySelector('.vault-empty-state:not(.va-empty)');
    if (empty) {
      empty.removeAttribute('style');
      empty.classList.add('va-empty');
      empty.innerHTML = `<div class="va-archive-mark" aria-hidden="true">${book}</div><h2>A little space for<br>what matters.</h2><p>Open a note, follow a familiar thread, or start a new page. This is where the details stay.</p><div class="va-empty-actions"><button type="button" data-va-action="new">Create a note</button><button type="button" data-va-action="browse">Browse notes</button></div><small>Markdown files · Obsidian-compatible</small>`;
      empty.querySelector('[data-va-action="new"]').addEventListener('click', () => root.querySelector('#new-note')?.click());
      empty.querySelector('[data-va-action="browse"]').addEventListener('click', () => {
        root.querySelector('[data-filter="notes"]')?.click();
        if (matchMedia('(max-width: 900px)').matches) showFiles(true);
        else root.querySelector('#vault-query')?.focus();
      });
    }
    // Never leave a stale toggle label after an existing native Files button runs.
    root.querySelector('.va-browse')?.setAttribute('aria-expanded', String(document.body.classList.contains('vault-files-open')));
    const focus = root.querySelector('.va-focus');
    if (focus) {
      const pressed = root.dataset.vaFocus === 'true';
      focus.setAttribute('aria-pressed', String(pressed));
      focus.querySelector('span').textContent = pressed ? 'Exit focus' : 'Focus';
    }
  }
  function queue() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(decorate);
  }
  const observer = new MutationObserver(records => {
    // Ignore editing, preview, save-status, tab and tree churn. Only shell changes
    // can create a missing header, sidebar, or empty state to decorate.
    if (records.some(record => {
      const el = record.target.nodeType === Node.ELEMENT_NODE ? record.target : record.target.parentElement;
      return !el?.closest('#vault-source, #vault-preview, #vault-save-status, .vault-doc-meta, #vault-tabs, #vault-tree, #vault-toc, .va-masthead, .va-rail-footer, .va-empty');
    })) queue();
  });
  observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden'] });
  const bodyObserver = new MutationObserver(() => {
    root.querySelector('.va-browse')?.setAttribute('aria-expanded', String(document.body.classList.contains('vault-files-open')));
  });
  bodyObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  root.addEventListener('click', event => {
    if (matchMedia('(max-width: 900px)').matches && event.target.closest('[data-vault-file]')) showFiles(false, true);
  });
  root.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.body.classList.contains('vault-files-open')) {
      showFiles(false, true);
      event.preventDefault();
    }
  });
  // No global keyboard shortcuts: preserve the editor and app's existing bindings.
  window.VaultAtmosphere = Object.freeze({ version: '1.0.0', refresh: queue });
  queue();
})();
