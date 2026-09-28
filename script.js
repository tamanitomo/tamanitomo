/* Platform tabs and copy buttons. Plain JavaScript; no external dependencies. */
(() => {
  'use strict';
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const status = document.querySelector('.copy-status');
  const initialStatus = status.textContent;
  let copyGeneration = 0;
  let resetTimer;

  function selectTab(tab, moveFocus = false) {
    copyGeneration += 1;
    clearTimeout(resetTimer);
    tabs.forEach((item) => {
      const active = item === tab;
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
      item.dataset.state = active ? 'active' : 'inactive';
      const panel = document.getElementById(item.getAttribute('aria-controls'));
      panel.hidden = !active;
      panel.dataset.state = item.dataset.state;
    });
    document.querySelectorAll('.copy-label').forEach((label) => { label.textContent = 'Copy'; });
    status.textContent = initialStatus;
    if (moveFocus) tab.focus();
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTab(tab));
    tab.addEventListener('keydown', (event) => {
      let target;
      if (event.key === 'ArrowRight') target = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') target = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') target = 0;
      else if (event.key === 'End') target = tabs.length - 1;
      else return;
      event.preventDefault();
      selectTab(tabs[target], true);
    });
  });

  document.querySelectorAll('.copy-button').forEach((button) => {
    button.addEventListener('click', async () => {
      const code = button.closest('[role="tabpanel"]').querySelector('code');
      const label = button.querySelector('.copy-label');
      const generation = ++copyGeneration;
      clearTimeout(resetTimer);
      try {
        if (!navigator.clipboard || !window.isSecureContext) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(code.textContent);
        if (generation !== copyGeneration) return;
        label.textContent = 'Copied';
        status.textContent = 'Commands copied to clipboard.';
        resetTimer = window.setTimeout(() => {
          label.textContent = 'Copy';
          status.textContent = initialStatus;
        }, 2500);
      } catch {
        if (generation !== copyGeneration) return;
        const range = document.createRange();
        range.selectNodeContents(code);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        status.textContent = 'Commands selected. Press Ctrl+C or Command+C, or use your device’s Copy action.';
      }
    });
  });
})();
