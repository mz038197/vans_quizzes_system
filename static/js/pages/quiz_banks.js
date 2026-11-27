// 題庫 page: the ⋯ menu on each Quiz Bank row (move, copy link, open/close, delete),
// the Folder dialogs (new, edit, delete), ticking rows for a bulk move, drag and drop
// onto Folder cards / chips / the 題庫 breadcrumb, and the 復原 toast after a move.
// Folder data comes from #folder-data.
(() => {
  const DATA = JSON.parse(document.getElementById('folder-data').textContent);
  const COLOR_NAMES = { blue: '藍', green: '綠', purple: '紫', amber: '橘', pink: '粉紅', cyan: '青' };
  const JSON_HEADERS = { 'Content-Type': 'application/json' };

  async function send(method, url, body) {
    try {
      const response = await fetch(url, { method, headers: JSON_HEADERS, body: body ? JSON.stringify(body) : undefined });
      const result = await response.json().catch(() => ({}));
      return { ok: response.ok, result };
    } catch (error) {
      return { ok: false, result: { error: '網路錯誤，請檢查連線' } };
    }
  }

  function make(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === 'text') node.textContent = v; else if (v !== null && v !== undefined) node.setAttribute(k, v);
    });
    (children || []).forEach((c) => node.append(c));
    return node;
  }

  /* New Folder / edit Folder. Resolves to the saved Folder, or null. */
  async function folderDialog(folder) {
    const nameId = 'fd-name';
    const input = make('input', { id: nameId, class: 'inp', type: 'text', maxlength: '100', autofocus: '', placeholder: '例如：七年級數學' });
    input.value = folder ? folder.name : '';
    const error = make('div', { class: 'err', role: 'alert' });
    const colors = make('div', { class: 'color-pick', role: 'radiogroup', 'aria-label': '顏色' });
    DATA.colors.forEach((color, i) => {
      const radio = make('input', { type: 'radio', name: 'fd-color', value: color });
      radio.checked = folder ? folder.color === color : i === 0;
      colors.append(make('label', { class: `fc-${color}`, title: COLOR_NAMES[color] || color }, [
        radio, make('span', { class: 'swatch', 'aria-hidden': 'true' }), make('span', { class: 'sr-only', text: COLOR_NAMES[color] || color }),
      ]));
    });
    const body = make('div', { class: 'stack' }, [
      make('div', { class: 'fld' }, [make('label', { for: nameId, text: '資料夾名稱' }), input, error]),
      make('div', { class: 'fld' }, [make('span', { class: 'label', text: '顏色' }), colors]),
    ]);
    let saving = false;
    const dlg = UI.dialog({
      title: folder ? '編輯資料夾' : '新增資料夾',
      body,
      cancelValue: null,
      actions: [
        { label: '取消', value: null },
        {
          label: folder ? '儲存' : '建立', kind: 'primary',
          value: () => { save(); return undefined; },
        },
      ],
    });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); save(); } });

    async function save() {
      if (saving) return;
      const name = input.value.trim();
      const color = (body.querySelector('input[name="fd-color"]:checked') || {}).value;
      if (!name) { showError('請輸入資料夾名稱'); return; }
      saving = true;
      const { ok, result } = folder
        ? await send('PUT', `/api/folders/${folder.id}`, { name, color })
        : await send('POST', '/api/folders', { name, color });
      saving = false;
      if (!ok) { showError(result.error || '儲存失敗，請稍後再試'); return; }
      dlg.close(result.folder);
    }
    function showError(text) {
      error.textContent = text;
      input.setAttribute('aria-invalid', 'true');
      input.focus();
    }
    return dlg.result;
  }

  function currentFolder() {
    return DATA.folders.find((f) => f.id === DATA.current) || null;
  }

  async function newFolder() {
    const folder = await folderDialog(null);
    if (!folder) return;
    UI.flash(`已建立資料夾「${folder.name}」`, 'ok');
    location.reload();
  }

  async function editFolder() {
    const folder = await folderDialog(currentFolder());
    if (!folder) return;
    UI.flash('資料夾已更新', 'ok');
    location.reload();
  }

  async function deleteFolder() {
    const folder = currentFolder();
    if (!folder) return;
    const ok = await UI.ask(
      `資料夾「${folder.name}」裡的題庫會移回「未分類」。\n題庫、題目和作答都不會被刪除。`,
      { title: '刪除資料夾', danger: true, okText: '刪除資料夾' },
    );
    if (!ok) return;
    const { ok: done, result } = await send('DELETE', `/api/folders/${folder.id}`);
    if (!done) { UI.toast(result.error || '刪除失敗，請稍後再試', 'error'); return; }
    UI.flash(result.message, 'ok');
    location.href = '/quiz-banks';
  }

  /* Moves survive the page reload: the toast with 復原 shows on the next page. */
  const UNDO_KEY = 'quiz_banks.undo';

  async function moveBanks(ids, folderId) {
    const { ok, result } = await send('POST', '/api/quiz-banks/move', { quiz_bank_ids: ids, folder_id: folderId });
    if (!ok) { UI.toast(result.error || '移動失敗，請稍後再試', 'error'); return; }
    try {
      sessionStorage.setItem(UNDO_KEY, JSON.stringify({ message: result.message, previous: result.previous }));
    } catch (err) {
      UI.flash(result.message, 'ok');
    }
    location.reload();
  }

  async function undoMove(previous) {
    const groups = new Map();
    previous.forEach((p) => {
      const key = p.folder_id === null ? '' : String(p.folder_id);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(p.id);
    });
    for (const [key, ids] of groups) {
      const { ok, result } = await send('POST', '/api/quiz-banks/move', { quiz_bank_ids: ids, folder_id: key === '' ? null : Number(key) });
      if (!ok) { UI.toast(result.error || '復原失敗，請稍後再試', 'error'); return; }
    }
    UI.flash('已復原', 'ok');
    location.reload();
  }

  (function showUndo() {
    let pending = null;
    try {
      pending = JSON.parse(sessionStorage.getItem(UNDO_KEY) || 'null');
      sessionStorage.removeItem(UNDO_KEY);
    } catch (err) { pending = null; }
    if (!pending || !Array.isArray(pending.previous)) return;
    UI.toast(pending.message, 'ok', { action: { label: '復原', onClick: () => undoMove(pending.previous) }, duration: 8000 });
  })();

  /* 移動到…: every Folder and 未分類, the current place marked, and 新增資料夾並移進去.
     what = { ids: [Number], title, here: folder id | null | undefined (mixed places) }. */
  function moveDialog(what) {
    const { ids, title, here } = what;
    const list = make('div', { class: 'move-list', role: 'list' });
    let dlg = null;
    function choice(label, folderId, color, icon) {
      const isHere = folderId === here;
      const button = make('button', { type: 'button', class: 'move-item' + (color ? ` fc-${color}` : ''), role: 'listitem' }, [
        color ? make('span', { class: 'fdot', 'aria-hidden': 'true' }) : make('i', { class: `fas ${icon}`, 'aria-hidden': 'true' }),
        make('span', { class: 'move-name', text: label }),
      ]);
      if (isHere) {
        button.disabled = true;
        button.setAttribute('aria-current', 'true');
        button.append(make('span', { class: 'muted small', text: '目前位置' }));
      }
      button.addEventListener('click', () => { dlg.close(true); moveBanks(ids, folderId); });
      return button;
    }
    list.append(choice('未分類', null, null, 'fa-inbox'));
    DATA.folders.forEach((f) => list.append(choice(f.name, f.id, f.color)));
    const create = make('button', { type: 'button', class: 'move-item move-new' }, [
      make('i', { class: 'fas fa-folder-plus', 'aria-hidden': 'true' }), make('span', { text: '新增資料夾並移進去' }),
    ]);
    create.addEventListener('click', async () => {
      dlg.close(true);
      const folder = await folderDialog(null);
      if (folder) moveBanks(ids, folder.id);
    });
    list.append(create);
    dlg = UI.dialog({
      title: `移動${title}`, body: list, cancelValue: null,
      actions: [{ label: '取消', value: null }],
    });
  }

  function folderOfRow(row) {
    return row.dataset.inFolder ? Number(row.dataset.inFolder) : null;
  }

  function moveWhat(rowList) {
    const places = new Set(rowList.map(folderOfRow));
    return {
      ids: rowList.map((r) => Number(r.dataset.bank)),
      title: rowList.length === 1 ? `「${rowList[0].dataset.title}」` : ` ${rowList.length} 個題庫`,
      here: places.size === 1 ? [...places][0] : undefined,
    };
  }

  /* ---- ticking rows and the bulk bar (the keyboard and touch way to move many) ---- */
  const rows = [...document.querySelectorAll('tr[data-bank]')];
  const pickAll = document.querySelector('[data-pick-all]');
  const bulkBar = document.getElementById('bulk-bar');
  const isPicked = (r) => r.querySelector('[data-pick]').checked;

  function pickedRows() {
    return rows.filter(isPicked);
  }

  function refreshPicks() {
    const picked = pickedRows();
    rows.forEach((r) => r.classList.toggle('is-picked', isPicked(r)));
    if (bulkBar) {
      bulkBar.hidden = picked.length === 0;
      document.getElementById('bulk-n').textContent = String(picked.length);
    }
    if (pickAll) {
      pickAll.checked = picked.length > 0 && picked.length === rows.length;
      pickAll.indeterminate = picked.length > 0 && picked.length < rows.length;
    }
  }

  document.addEventListener('change', (e) => {
    if (e.target.matches('[data-pick]')) refreshPicks();
    if (e.target.matches('[data-pick-all]')) {
      rows.forEach((r) => { r.querySelector('[data-pick]').checked = e.target.checked; });
      refreshPicks();
    }
  });
  if (bulkBar) {
    document.getElementById('bulk-move').addEventListener('click', () => moveDialog(moveWhat(pickedRows())));
    document.getElementById('bulk-clear').addEventListener('click', () => {
      rows.forEach((r) => { r.querySelector('[data-pick]').checked = false; });
      refreshPicks();
    });
  }
  refreshPicks();

  /* ---- drag and drop (native events). A target has data-drop="<Folder id>", or "" for 未分類. ---- */
  const rootCrumb = document.querySelector('nav.crumbs a');
  if (rootCrumb) rootCrumb.dataset.drop = '';
  let dragged = [];

  const dropTarget = (e) => (e.target.closest ? e.target.closest('[data-drop]') : null);

  document.addEventListener('dragstart', (e) => {
    const row = e.target.closest ? e.target.closest('tr[data-bank]') : null;
    if (!row) return;
    const picked = pickedRows();
    dragged = picked.includes(row) ? picked : [row];
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', dragged.map((r) => r.dataset.bank).join(','));
    dragged.forEach((r) => r.classList.add('is-dragging'));
  });
  document.addEventListener('dragend', () => {
    document.querySelectorAll('.is-dragging, .drop-ok').forEach((el) => el.classList.remove('is-dragging', 'drop-ok'));
    dragged = [];
  });
  document.addEventListener('dragover', (e) => {
    const target = dropTarget(e);
    if (!target || !dragged.length) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    target.classList.add('drop-ok');
  });
  document.addEventListener('dragleave', (e) => {
    const target = dropTarget(e);
    if (target && !target.contains(e.relatedTarget)) target.classList.remove('drop-ok');
  });
  document.addEventListener('drop', (e) => {
    const target = dropTarget(e);
    if (!target || !dragged.length) return;
    e.preventDefault();
    target.classList.remove('drop-ok');
    const folderId = target.dataset.drop === '' ? null : Number(target.dataset.drop);
    const moving = dragged.filter((r) => folderOfRow(r) !== folderId);
    if (moving.length) moveBanks(moving.map((r) => Number(r.dataset.bank)), folderId);
  });

  document.querySelectorAll('[data-folder-new]').forEach((b) => b.addEventListener('click', newFolder));
  document.querySelectorAll('[data-folder-edit]').forEach((b) => b.addEventListener('click', editFolder));
  document.querySelectorAll('[data-folder-delete]').forEach((b) => b.addEventListener('click', deleteFolder));

  let menu = null;
  let menuButton = null;

  function closeMenu() {
    if (!menu) return;
    menu.remove();
    menu = null;
    if (menuButton) {
      menuButton.setAttribute('aria-expanded', 'false');
      menuButton.focus();
      menuButton = null;
    }
  }

  function item(icon, label, onClick, danger) {
    const button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('role', 'menuitem');
    if (danger) button.className = 'danger';
    const i = document.createElement('i');
    i.className = `fas ${icon}`;
    i.setAttribute('aria-hidden', 'true');
    button.append(i, document.createTextNode(label));
    button.addEventListener('click', () => { closeMenu(); onClick(); });
    return button;
  }

  function openMenu(button) {
    const bank = button.dataset;
    const active = bank.active === 'true';
    closeMenu();
    menuButton = button;
    menu = document.createElement('div');
    menu.className = 'menu';
    menu.setAttribute('role', 'menu');
    menu.append(
      item('fa-folder-open', '移動到…', () => moveDialog(moveWhat([button.closest('tr[data-bank]')]))),
      item('fa-link', '複製連結', () => copyLink(bank.code)),
      item(active ? 'fa-lock' : 'fa-lock-open', active ? '停用題庫' : '啟用題庫', () => toggleBank(bank.id, active)),
      document.createElement('hr'),
      item('fa-trash', '刪除題庫', () => deleteBank(bank.id, bank.title), true),
    );
    document.body.appendChild(menu);
    const box = button.getBoundingClientRect();
    const left = Math.max(8, Math.min(box.right - menu.offsetWidth, window.innerWidth - menu.offsetWidth - 8));
    menu.style.left = `${left + window.scrollX}px`;
    menu.style.top = `${box.bottom + window.scrollY + 4}px`;
    button.setAttribute('aria-expanded', 'true');
    menu.querySelector('button').focus();
  }

  document.addEventListener('click', (e) => {
    const button = e.target.closest('[data-more]');
    if (button) {
      e.stopPropagation();
      if (menuButton === button) closeMenu(); else openMenu(button);
      return;
    }
    if (menu && !menu.contains(e.target)) closeMenu();
  });
  document.addEventListener('keydown', (e) => {
    if (!menu) return;
    if (e.key === 'Escape') { e.preventDefault(); closeMenu(); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const items = [...menu.querySelectorAll('button')];
      const at = items.indexOf(document.activeElement);
      const next = (at + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items[next].focus();
    }
  });

  async function copyLink(code) {
    const link = `${location.origin}/quiz/${code}`;
    if (await copyToClipboard(link)) {
      UI.toast(`已複製連結：${link}`, 'ok');
    } else {
      UI.toast(`無法複製，請手動複製：${link}`, 'error');
    }
  }

  async function toggleBank(id, active) {
    const action = active ? '停用' : '啟用';
    const message = active ? '停用後，學生打不開這個題庫的連結。' : '啟用後，學生可以用連結作答。';
    if (!(await UI.ask(message, { title: `${action}題庫`, okText: action }))) return;
    try {
      const response = await fetch(`/api/quiz-bank/${id}/toggle`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) { UI.toast('操作失敗，請稍後再試', 'error'); return; }
      UI.flash(`題庫已${action}`, 'ok');
      location.reload();
    } catch (error) {
      UI.toast('網路錯誤，請檢查連線', 'error');
    }
  }

  async function deleteBank(id, title) {
    const ok = await UI.ask(`「${title}」和它的所有題目會永久刪除，無法復原。`, {
      title: '刪除題庫', danger: true, okText: '刪除',
    });
    if (!ok) return;
    try {
      let response = await fetch(`/api/quiz-bank/${id}`, {
        method: 'DELETE', headers: { 'Content-Type': 'application/json' },
      });
      let result = await response.json();
      if (response.status === 409 && result.requires_confirm) {
        const sure = await UI.ask(
          `這個題庫已有 ${result.submission_count} 筆作答紀錄。\n刪除後題庫、題目與這些紀錄都會永久消失，無法復原。`,
          { title: '刪除題庫和作答紀錄', danger: true, okText: '全部刪除' },
        );
        if (!sure) return;
        response = await fetch(`/api/quiz-bank/${id}`, {
          method: 'DELETE', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirm: true }),
        });
        result = await response.json();
      }
      if (response.ok) {
        UI.flash(result.message, 'ok');
        location.reload();
      } else {
        UI.toast(result.error || '刪除失敗，請稍後再試', 'error');
      }
    } catch (error) {
      UI.toast('網路錯誤，請檢查連線', 'error');
    }
  }
})();
