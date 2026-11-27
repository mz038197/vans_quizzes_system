// Sign-in page (templates/index.html): breathing glows and the QR picture.
(() => {
  // Nine glows in six colours. Each one breathes over 9-16 s; after each breath (when it is dark)
  // it moves to a new random place. With reduced motion the CSS keeps them still.
  const box = document.querySelector('.lp-glow');
  if (box) {
    const COLORS = 6;
    const COUNT = 9;
    const rnd = (a, b) => a + Math.random() * (b - a);
    const place = (el) => {
      const size = rnd(260, 560);
      el.style.width = el.style.height = size + 'px';
      el.style.left = rnd(0, 100) + '%';
      el.style.top = rnd(5, 95) + '%';
      el.style.background = `radial-gradient(circle, var(--glow-${1 + Math.floor(Math.random() * COLORS)}) 0%, transparent 65%)`;
      el.style.setProperty('--peak', rnd(0.35, 0.7).toFixed(2));
    };
    for (let i = 0; i < COUNT; i++) {
      const el = document.createElement('span');
      el.className = 'lp-blob';
      place(el);
      const dur = rnd(9, 16);
      el.style.animationDuration = dur + 's';
      el.style.animationDelay = -rnd(0, dur) + 's';
      el.addEventListener('animationiteration', () => place(el));
      box.appendChild(el);
    }
  }

  // A QR-like picture (decoration only, it does not encode a link): three finder squares
  // and a fixed pseudo-random pattern, so the page needs no QR library.
  const qr = document.querySelector('.sc-qr-img');
  if (qr) {
    const N = 21;
    let seed = 7;
    const next = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
    const inFinder = (x, y) => (x < 8 && y < 8) || (x >= N - 8 && y < 8) || (x < 8 && y >= N - 8);
    const finderOn = (x, y) => {
      const fx = x >= N - 8 ? x - (N - 7) : x;
      const fy = y >= N - 8 ? y - (N - 7) : y;
      if (fx < 0 || fy < 0 || fx > 6 || fy > 6) return false;
      const ring = Math.min(fx, fy, 6 - fx, 6 - fy);
      return ring !== 1;
    };
    let d = '';
    for (let y = 0; y < N; y++) {
      for (let x = 0; x < N; x++) {
        const on = inFinder(x, y) ? finderOn(x, y) : next() < 0.5;
        if (on) d += `M${x} ${y}h1v1h-1z`;
      }
    }
    qr.innerHTML = `<svg viewBox="0 0 ${N} ${N}" shape-rendering="crispEdges" aria-hidden="true"><path fill="currentColor" d="${d}"/></svg>`;
  }
})();
