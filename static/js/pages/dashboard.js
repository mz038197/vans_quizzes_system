// 儀表板: 上課發題 panel (QR code, short link, copy, full-screen projector).
// QR codes come from static/js/vendor/qrcode.js (qrcode-generator 1.4.4, MIT), not a CDN.
(() => {
  const $ = (id) => document.getElementById(id);
  const select = $('qr-bank');
  if (!select) return;

  const stage = $('qr-stage');
  const copyButton = $('qr-copy');
  let opener = null;
  let copyTimer = null;

  const link = () => `${location.origin}/quiz/${select.value}`;

  function qrSvg(text) {
    const qr = qrcode(0, 'M');
    qr.addData(text);
    qr.make();
    return qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  }

  function shortLink(target) {
    target.textContent = `${location.host}/quiz/`;
    const code = document.createElement('b');
    code.textContent = select.value;
    target.appendChild(code);
  }

  function render() {
    $('qr-img').innerHTML = qrSvg(link());
    shortLink($('qr-url'));
  }

  function resetCopy() {
    copyButton.classList.remove('is-ok');
    copyButton.querySelector('span').textContent = '複製連結';
  }

  copyButton.addEventListener('click', async () => {
    if (await copyToClipboard(link())) {
      copyButton.classList.add('is-ok');
      copyButton.querySelector('span').textContent = '已複製';
      clearTimeout(copyTimer);
      copyTimer = setTimeout(resetCopy, 1500);
    } else {
      UI.toast(`無法複製，請手動複製：${link()}`, 'error');
    }
  });

  function openStage() {
    opener = document.activeElement;
    $('qr-stage-title').textContent = select.selectedOptions[0].dataset.title;
    $('qr-stage-img').innerHTML = qrSvg(link());
    shortLink($('qr-stage-url'));
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

  select.addEventListener('change', () => { resetCopy(); render(); });
  $('qr-full').addEventListener('click', openStage);
  $('qr-close').addEventListener('click', closeStage);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeStage(); });
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement) closeStage(); });
  render();
})();
