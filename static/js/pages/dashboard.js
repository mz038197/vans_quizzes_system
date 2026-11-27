// 儀表板: 上課發題 panel (QR code, short link, copy, full-screen projector) and the
// 「投影 QR」 buttons on the Class Session cards. Links use the Class Session code.
// QR codes come from static/js/vendor/qrcode.js (qrcode-generator 1.4.4, MIT), not a CDN.
(() => {
  const $ = (id) => document.getElementById(id);
  const select = $('qr-bank');
  const stage = $('qr-stage');
  const copyButton = $('qr-copy');
  let opener = null;
  let copyTimer = null;

  const link = (code) => `${location.origin}/quiz/${code}`;

  function qrSvg(text) {
    const qr = qrcode(0, 'M');
    qr.addData(text);
    qr.make();
    return qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  }

  function shortLink(target, code) {
    target.textContent = `${location.host}/quiz/`;
    const b = document.createElement('b');
    b.textContent = code;
    target.appendChild(b);
  }

  function openStage(code, title) {
    opener = document.activeElement;
    $('qr-stage-title').textContent = title;
    $('qr-stage-img').innerHTML = qrSvg(link(code));
    shortLink($('qr-stage-url'), code);
    stage.hidden = false;
    document.body.classList.add('has-dialog');
    $('qr-close').focus();
    if (stage.requestFullscreen) stage.requestFullscreen().catch(() => {});
  }

  function closeStage() {
    if (stage.hidden) return;
    stage.hidden = true;
    document.body.classList.remove('has-dialog');
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    if (opener) opener.focus();
  }

  document.addEventListener('click', (e) => {
    const button = e.target.closest('[data-qr]');
    if (button) openStage(button.dataset.qr, button.dataset.title);
  });
  $('qr-close').addEventListener('click', closeStage);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeStage(); });
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement) closeStage(); });

  if (!select) return;

  function render() {
    $('qr-img').innerHTML = qrSvg(link(select.value));
    shortLink($('qr-url'), select.value);
  }

  function resetCopy() {
    copyButton.classList.remove('is-ok');
    copyButton.querySelector('span').textContent = '複製連結';
  }

  copyButton.addEventListener('click', async () => {
    if (await copyToClipboard(link(select.value))) {
      copyButton.classList.add('is-ok');
      copyButton.querySelector('span').textContent = '已複製';
      clearTimeout(copyTimer);
      copyTimer = setTimeout(resetCopy, 1500);
    } else {
      UI.toast(`無法複製，請手動複製：${link(select.value)}`, 'error');
    }
  });

  select.addEventListener('change', () => { resetCopy(); render(); });
  $('qr-full').addEventListener('click', () => openStage(select.value, select.selectedOptions[0].dataset.title));
  render();
})();
