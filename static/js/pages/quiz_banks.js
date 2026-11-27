// 題庫 page: the ⋯ menu on each Quiz Bank row (copy link, open/close, delete).
(() => {
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
