(() => {
  if (window.__alasAosWebView) return;
  window.__alasAosWebView = true;

  const style = document.createElement('style');
  style.textContent = `
    body.alasaos-manage #pywebio-scope-ROOT {
      height: auto !important;
      min-height: 0 !important;
    }
    body.alasaos-manage #input-container {
      position: fixed !important;
      top: var(--alasaos-viewport-top, 0px) !important;
      left: 0 !important;
      right: 0 !important;
      bottom: auto !important;
      height: var(--alasaos-viewport-height) !important;
      margin: 0 !important;
      padding: 12px 0 !important;
      box-sizing: border-box;
      display: flex;
      align-items: center;
      background: rgba(0, 0, 0, .25);
      box-shadow: none !important;
    }
    body.alasaos-manage #input-container:not(:has(form)) { display: none; }
    body.alasaos-manage #input-cards {
      max-height: 100%;
      overflow-y: auto;
      overscroll-behavior: contain;
    }
    body.alasaos-manage #end-space { height: 0 !important; }
    body.alasaos-manage #pywebio-scope-config_table button { white-space: nowrap; }
    body.alasaos-manage #pywebio-scope-config_table th:last-child { text-align: center; }
    .alasaos-config-actions { display: flex; align-items: center; justify-content: center; gap: 6px; }
    .alasaos-config-actions button { margin: 0 !important; }
  `;
  document.head.appendChild(style);
  if (new URL(location.href).searchParams.get('app') === 'manage') {
    document.body.classList.add('alasaos-manage');
    // Disable PyWebIO's draggable bottom panel; this host uses a centered form.
    if (window.WebIO?._state) WebIO._state.FixedInputPanel = false;
  }
  const resize = () => {
    const viewport = window.visualViewport;
    document.documentElement.style.setProperty('--alasaos-viewport-height',
      Math.max(1, viewport ? viewport.height : innerHeight) + 'px');
    document.documentElement.style.setProperty('--alasaos-viewport-top',
      (viewport ? viewport.offsetTop : 0) + 'px');
  };
  resize();
  window.addEventListener('resize', resize);
  window.visualViewport?.addEventListener('resize', resize);
  window.visualViewport?.addEventListener('scroll', resize);

  // PyWebIO exports an in-memory Blob through FileSaver, not an HTTP download.
  // A prompt supplies the frame origin to WebChromeClient without exposing a
  // JavaScript interface to every iframe. Android handles this prompt silently.
  window.saveAs = (blob, name) => {
    if (!(blob instanceof Blob) || blob.size > 8 * 1024 * 1024) {
      window.prompt('alasaos-export:' + name, '');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => window.prompt('alasaos-export:' + name, reader.result);
    reader.onerror = () => window.prompt('alasaos-export:' + name, '');
    reader.readAsDataURL(blob);
  };

  const addDeleteButtons = () => {
    if (!document.body.classList.contains('alasaos-manage')) return;
    document.querySelectorAll('#pywebio-scope-config_table tbody tr').forEach(row => {
      const cells = row.querySelectorAll('td');
      if (cells.length !== 3 || row.querySelector('.alasaos-delete-config')) return;
      const name = cells[0].textContent.trim();
      const mod = cells[1].textContent.trim();
      const config = name + (mod === 'alas' ? '' : '.' + mod);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-outline-danger btn-sm alasaos-delete-config';
      button.textContent = '删除';
      button.onclick = () => window.prompt('alasaos-delete:' + config, '');
      const actions = document.createElement('div');
      actions.className = 'alasaos-config-actions';
      while (cells[2].firstChild) actions.appendChild(cells[2].firstChild);
      actions.appendChild(button);
      cells[2].appendChild(actions);
    });
  };

  // Task scopes are cleared and refilled by separate server messages. Keep the
  // last grid tracks until that short burst settles, so empty lists do not
  // redistribute all of the mobile overview's space between messages.
  let scheduler, grids = [], tracks = [], timer = null;
  const capture = () => {
    if (timer === null) tracks = grids.map(el => getComputedStyle(el).gridTemplateRows);
  };
  const sizes = new ResizeObserver(capture);
  const bind = current => {
    clearTimeout(timer);
    timer = null;
    sizes.disconnect();
    scheduler = current;
    grids = current ? [current, ...['running', 'pending', 'waiting'].map(id =>
      document.getElementById('pywebio-scope-' + id)).filter(Boolean)] : [];
    capture();
    grids.forEach(el => sizes.observe(el));
  };
  const mutations = new MutationObserver(records => {
    addDeleteButtons();
    const current = document.getElementById('pywebio-scope-schedulers');
    if (current !== scheduler) {
      bind(current);
      return;
    }
    if (!scheduler || !records.some(record => {
      const target = record.target.nodeType === 1 ? record.target : record.target.parentElement;
      return target?.closest('#pywebio-scope-running_tasks, #pywebio-scope-pending_tasks, #pywebio-scope-waiting_tasks');
    })) return;
    if (timer === null) grids.forEach((el, i) => {
      if (tracks[i] && tracks[i] !== 'none') el.style.setProperty('grid-template-rows', tracks[i]);
    });
    clearTimeout(timer);
    timer = setTimeout(() => {
      grids.forEach(el => el.style.removeProperty('grid-template-rows'));
      timer = null;
      capture();
    }, 120);
  });
  bind(document.getElementById('pywebio-scope-schedulers'));
  addDeleteButtons();
  mutations.observe(document.body, {childList: true, subtree: true});
})();
