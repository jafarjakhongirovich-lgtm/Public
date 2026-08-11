/* ===========================================================================
   Логика презентации: камера, слайды, анимации, интерактив.
   =========================================================================== */
(function () {
  const cv = document.getElementById('scene');
  const R = new Renderer(cv);
  const car = buildCar();
  R.meshes = car.meshes;

  const isSmall = () => window.innerWidth < 880;

  /* --- положения камеры по слайдам --------------------------------------- */
  const CAMS = {
    hero:     { az: -0.78, el: 0.150, dist: 10.4, t: [0.00, 0.70, 0], rot: 0.050, spin: 0.9 },
    engine:   { az:  2.30, el: 0.28,  dist: 6.8,  t: [-1.62, 0.70, 0], rot: 0.014, spin: 0.0, xray: 1 },
    perf:     { az: -0.44, el: 0.055, dist: 9.2,  t: [0.30, 0.60, 0], rot: 0.020, spin: 9.0 },
    aero:     { az:  2.34, el: 0.28,  dist: 8.2,  t: [-1.40, 1.05, 0], rot: 0.012, spin: 2.4, hlWing: 1 },
    chassis:  { az: -2.10, el: -0.02, dist: 8.8,  t: [0.85, 0.42, 0], rot: 0.016, spin: 1.6, hlWheel: 1 },
    mass:     { az: -1.20, el: 0.58,  dist: 10.2, t: [0.00, 0.72, 0], rot: 0.030, spin: 0.6 },
    dims:     { az: -1.5708, el: 0.02, dist: 10.6, t: [0.00, 0.68, 0], rot: 0,    spin: 0.0, dims: 1 },
    ring:     { az: -0.55, el: 0.10,  dist: 9.4,  t: [0.10, 0.64, 0], rot: 0.045, spin: 12.0 },
    weissach: { az:  2.05, el: 0.24,  dist: 8.8,  t: [-0.85, 0.84, 0], rot: 0.020, spin: 1.0 },
    finale:   { az: -0.95, el: 0.22,  dist: 13.6, t: [0.00, 0.72, 0], rot: 0.070, spin: 3.0, sx: 0 }
  };

  const slides = Array.from(document.querySelectorAll('.slide'));
  let current = 0;

  /* --- состояние сцены (сглаживается покадрово) --------------------------- */
  const goal = {
    az: CAMS.hero.az, el: CAMS.hero.el, dist: CAMS.hero.dist,
    tx: 0, ty: 0.72, tz: 0,
    xray: 0, hlWing: 0, hlWheel: 0, dims: 0, spin: CAMS.hero.spin,
    shiftX: 0, shiftY: 0
  };
  const cur = Object.assign({}, goal);
  let autoRot = CAMS.hero.rot;
  let orbit = 0;              // накопленный угол автовращения, сбрасывается на смене слайда
  let rotOn = true, spinOn = true;
  let spinAngle = 0, spinSpeed = CAMS.hero.spin;
  let drsOpen = false, wingAngle = 0, wingGoal = 0;

  function applySlide(i) {
    const key = slides[i].dataset.cam;
    const c = CAMS[key] || CAMS.hero;
    goal.az = c.az; goal.el = c.el;
    goal.dist = c.dist * (isSmall() ? 0.86 : 1);
    goal.tx = c.t[0]; goal.ty = c.t[1]; goal.tz = c.t[2];
    goal.xray = c.xray || 0;
    goal.hlWing = c.hlWing || 0;
    goal.hlWheel = c.hlWheel || 0;
    goal.dims = c.dims || 0;
    goal.spin = c.spin;
    goal.shiftX = c.sx !== undefined ? c.sx : baseShiftX;
    goal.shiftY = c.sy !== undefined ? c.sy : baseShiftY;
    autoRot = c.rot || 0;
    orbit = 0;
    manualAz = 0;
    manualEl = 0;
    document.getElementById('dimlayer').classList.toggle('on', !!c.dims);
    document.querySelectorAll('#dots button').forEach((b, k) => b.classList.toggle('on', k === i));
    document.getElementById('progress').style.width =
      ((i / (slides.length - 1)) * 100).toFixed(1) + '%';
    if (key === 'aero') { setTimeout(() => { if (!drsOpen) toggleDrs(true); }, 900); }
  }

  /* --- точки навигации ---------------------------------------------------- */
  const dots = document.getElementById('dots');
  slides.forEach((s, i) => {
    const b = document.createElement('button');
    b.innerHTML = '<i></i>';
    b.setAttribute('aria-label', 'Слайд ' + (i + 1));
    b.onclick = () => goTo(i);
    dots.appendChild(b);
  });

  const deck = document.getElementById('deck');
  function goTo(i) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    slides[i].scrollIntoView({ behavior: 'smooth' });
  }
  document.getElementById('prevBtn').onclick = () => goTo(current - 1);
  document.getElementById('nextBtn').onclick = () => goTo(current + 1);
  window.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'PageDown' || e.key === ' ') { e.preventDefault(); goTo(current + 1); }
    if (e.key === 'ArrowUp' || e.key === 'PageUp') { e.preventDefault(); goTo(current - 1); }
    if (e.key === 'Home') goTo(0);
    if (e.key === 'End') goTo(slides.length - 1);
  });

  /* --- появление панелей и запуск счётчиков ------------------------------- */
  const seen = new WeakSet();
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.intersectionRatio > 0.55) {
        const i = slides.indexOf(e.target);
        if (i !== current) { current = i; applySlide(i); }
        e.target.classList.add('on');
        if (!seen.has(e.target)) { seen.add(e.target); runNumbers(e.target); }
      }
    }
  }, { root: deck, threshold: [0, 0.55, 0.9] });
  slides.forEach((s) => io.observe(s));

  /* --- анимация чисел ------------------------------------------------------ */
  function fmt(n, dec) {
    const s = Math.abs(n).toFixed(dec);
    const parts = s.split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    return parts.length > 1 ? parts[0] + ',' + parts[1] : parts[0];
  }
  function runNumbers(root) {
    root.querySelectorAll('[data-count]').forEach((el) => {
      const target = parseFloat(el.dataset.count);
      const dec = parseInt(el.dataset.dec || '0', 10);
      const dur = 1400;
      const t0 = performance.now();
      const step = (now) => {
        const p = Math.min(1, (now - t0) / dur);
        const e = 1 - Math.pow(1 - p, 3);
        el.textContent = fmt(target * e, dec);
        if (p < 1) requestAnimationFrame(step);
        else el.textContent = fmt(target, dec);
      };
      requestAnimationFrame(step);
    });
    root.querySelectorAll('.fill').forEach((el, i) => {
      setTimeout(() => { el.style.width = el.dataset.w + '%'; }, 180 + i * 130);
    });
  }

  /* --- тахометр ------------------------------------------------------------ */
  const rpmArc = document.getElementById('rpmArc');
  const rpmNeedle = document.getElementById('rpmNeedle');
  const rpmVal = document.getElementById('rpmVal');
  const GC = 66, GR = 56;
  function gaugePoint(frac, r) {
    const a = (-135 + 270 * frac) * Math.PI / 180;
    return [GC + Math.sin(a) * r, GC - Math.cos(a) * r];
  }
  function arcPath(f0, f1, r) {
    const p0 = gaugePoint(f0, r), p1 = gaugePoint(f1, r);
    const large = (f1 - f0) * 270 > 180 ? 1 : 0;
    return `M ${p0[0].toFixed(2)} ${p0[1].toFixed(2)} A ${r} ${r} 0 ${large} 1 ${p1[0].toFixed(2)} ${p1[1].toFixed(2)}`;
  }
  if (rpmArc) {
    const red = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    red.setAttribute('d', arcPath(0.944, 1, GR));
    red.setAttribute('fill', 'none');
    red.setAttribute('stroke', '#d8483c');
    red.setAttribute('stroke-width', '9');
    red.setAttribute('stroke-linecap', 'round');
    rpmArc.parentNode.insertBefore(red, rpmArc);
  }
  function updateGauge(t) {
    // цикл: раскрутка до отсечки -> удержание -> сброс
    const period = 5.2;
    const p = (t % period) / period;
    let rpm;
    if (p < 0.45) rpm = 9000 * Math.pow(p / 0.45, 0.72);
    else if (p < 0.62) rpm = 9000 - Math.sin((p - 0.45) / 0.17 * Math.PI * 4) * 120;
    else rpm = 9000 * Math.max(0, 1 - (p - 0.62) / 0.28) + 800 * Math.min(1, (p - 0.62) / 0.28);
    rpm = Math.max(0, Math.min(9000, rpm));
    const frac = rpm / 9000;
    if (rpmArc) rpmArc.setAttribute('d', frac > 0.005 ? arcPath(0, frac, GR) : '');
    if (rpmNeedle) {
      const q = gaugePoint(frac, 44);
      rpmNeedle.setAttribute('d', `M ${GC} ${GC} L ${q[0].toFixed(2)} ${q[1].toFixed(2)}`);
    }
    if (rpmVal) rpmVal.textContent = fmt(Math.round(rpm / 50) * 50, 0);
  }

  /* --- DRS ----------------------------------------------------------------- */
  const drsFlag = document.getElementById('drsFlag');
  const drsBtn = document.getElementById('drsBtn');
  function toggleDrs(state) {
    drsOpen = state === undefined ? !drsOpen : state;
    wingGoal = drsOpen ? 0.30 : 0;   // DRS «уплощает» крыло
    if (drsFlag) {
      drsFlag.classList.toggle('open', drsOpen);
      drsFlag.querySelector('span').textContent = drsOpen ? 'DRS ОТКРЫТ · минимум сопротивления' : 'DRS ЗАКРЫТ · максимум прижима';
    }
    if (drsBtn) drsBtn.textContent = drsOpen ? 'Закрыть DRS' : 'Нажать DRS';
  }
  if (drsBtn) drsBtn.onclick = () => toggleDrs();

  /* --- цвета кузова -------------------------------------------------------- */
  const COLORS = [
    ['#a6c03c', 'Python Green'],
    ['#c8ced2', 'Arctic Grey'],
    ['#bd120f', 'Guards Red'],
    ['#1c6ea6', 'Shark Blue'],
    ['#b7bbbe', 'GT Silver'],
    ['#17191b', 'Black']
  ];
  const swWrap = document.getElementById('swatches');
  COLORS.forEach((c, i) => {
    const b = document.createElement('button');
    b.className = 'sw' + (i === 0 ? ' on' : '');
    b.style.background = c[0];
    b.title = c[1];
    b.setAttribute('aria-label', 'Цвет: ' + c[1]);
    b.onclick = () => {
      setPaint(c[0]);
      swWrap.querySelectorAll('.sw').forEach((x) => x.classList.remove('on'));
      b.classList.add('on');
    };
    swWrap.appendChild(b);
  });

  /* --- кнопки вращения ------------------------------------------------------ */
  const rotBtn = document.getElementById('rotBtn');
  const spinBtn = document.getElementById('spinBtn');
  rotBtn.classList.add('active');
  spinBtn.classList.add('active');
  rotBtn.onclick = () => { rotOn = !rotOn; rotBtn.classList.toggle('active', rotOn); };
  spinBtn.onclick = () => { spinOn = !spinOn; spinBtn.classList.toggle('active', spinOn); };

  /* --- перетаскивание мышью / пальцем --------------------------------------- */
  let drag = null, manualAz = 0, manualEl = 0;
  const onDown = (x, y) => { drag = { x, y }; };
  const onMove = (x, y) => {
    if (!drag) return;
    manualAz += (x - drag.x) * 0.006;
    manualEl = Math.max(-0.35, Math.min(1.0, manualEl - (y - drag.y) * 0.004));
    drag = { x, y };
  };
  const onUp = () => { drag = null; };
  cv.addEventListener('pointerdown', (e) => onDown(e.clientX, e.clientY));
  window.addEventListener('pointermove', (e) => onMove(e.clientX, e.clientY));
  window.addEventListener('pointerup', onUp);
  cv.style.touchAction = 'none';

  /* --- выноски габаритов ----------------------------------------------------- */
  const dimSvg = document.getElementById('dimlayer');
  const SVGNS = 'http://www.w3.org/2000/svg';
  function w2s(p) {
    const vp = M4.apply(R.viewMatrix(), p);
    if (-vp[2] < 0.12) return null;
    return R.project(vp);
  }
  function drawDims() {
    if (cur.dims < 0.5) { dimSvg.innerHTML = ''; return; }
    const zo = -1.55;
    const items = [
      { a: [2.286, 0.02, zo], b: [-2.286, 0.02, zo], off: [0, 34], label: 'ДЛИНА 4572 мм' },
      { a: [1.228, 1.62, zo], b: [-1.229, 1.62, zo], off: [0, -14], label: 'КОЛЁСНАЯ БАЗА 2457 мм' },
      { a: [-2.95, 0.0, zo], b: [-2.95, 1.322, zo], off: [-16, 0], label: 'ВЫСОТА 1322 мм' }
    ];
    let out = '';
    for (const it of items) {
      const A = w2s(it.a), B = w2s(it.b);
      if (!A || !B) continue;
      const ax = A[0] + it.off[0], ay = A[1] + it.off[1];
      const bx = B[0] + it.off[0], by = B[1] + it.off[1];
      const nx = -(by - ay), ny = bx - ax;
      const nl = Math.hypot(nx, ny) || 1;
      const tx = (nx / nl) * 8, ty = (ny / nl) * 8;
      out += `<line x1="${ax}" y1="${ay}" x2="${bx}" y2="${by}"/>`;
      out += `<line class="tick" x1="${ax - tx}" y1="${ay - ty}" x2="${ax + tx}" y2="${ay + ty}"/>`;
      out += `<line class="tick" x1="${bx - tx}" y1="${by - ty}" x2="${bx + tx}" y2="${by + ty}"/>`;
      const mx = (ax + bx) / 2, my = (ay + by) / 2;
      const vertical = Math.abs(by - ay) > Math.abs(bx - ax);
      out += `<text x="${mx}" y="${my - (vertical ? 0 : 9)}" text-anchor="middle"` +
        (vertical ? ` transform="rotate(-90 ${mx} ${my})"` : '') + `>${it.label}</text>`;
    }
    dimSvg.innerHTML = out;
  }

  /* --- вспомогательное ------------------------------------------------------- */
  const lerp = (a, b, k) => a + (b - a) * k;
  function lerpAngle(a, b, k) {
    let d = ((b - a + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI;
    return a + d * k;
  }

  let baseShiftX = 0, baseShiftY = 0;
  function resize() {
    R.resize();
    dimSvg.setAttribute('viewBox', `0 0 ${R.W} ${R.H}`);
    dimSvg.setAttribute('width', R.W);
    dimSvg.setAttribute('height', R.H);
    baseShiftX = isSmall() ? 0 : Math.min(230, R.W * 0.19);
    baseShiftY = isSmall() ? -R.H * 0.27 : 0;
    const c = CAMS[slides[current].dataset.cam] || CAMS.hero;
    goal.shiftX = c.sx !== undefined ? c.sx : baseShiftX;
    goal.shiftY = c.sy !== undefined ? c.sy : baseShiftY;
    R.cam.fov = Math.min(R.W, R.H) * (isSmall() ? 0.92 : 1.02);
  }
  window.addEventListener('resize', resize);
  resize();
  applySlide(0);
  slides[0].classList.add('on');
  seen.add(slides[0]);
  runNumbers(slides[0]);

  /* --- главный цикл ----------------------------------------------------------- */
  let last = performance.now();
  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const t = now / 1000;

    if (rotOn) orbit += autoRot * dt;

    // сглаживание камеры
    const k = 1 - Math.pow(0.001, dt);
    cur.az = lerpAngle(cur.az, goal.az + orbit + manualAz, k);
    cur.el = lerp(cur.el, goal.el + manualEl, k);
    cur.dist = lerp(cur.dist, goal.dist, k);
    cur.tx = lerp(cur.tx, goal.tx, k);
    cur.ty = lerp(cur.ty, goal.ty, k);
    cur.tz = lerp(cur.tz, goal.tz, k);
    cur.xray = lerp(cur.xray, goal.xray, k);
    cur.hlWing = lerp(cur.hlWing, goal.hlWing, k);
    cur.hlWheel = lerp(cur.hlWheel, goal.hlWheel, k);
    cur.dims = lerp(cur.dims, goal.dims, k);
    cur.shiftX = lerp(cur.shiftX, goal.shiftX, k);
    cur.shiftY = lerp(cur.shiftY, goal.shiftY, k);

    R.cam.az = cur.az;
    R.cam.el = cur.el;
    R.cam.dist = cur.dist;
    R.cam.target = [cur.tx, cur.ty, cur.tz];
    R.cam.shiftX = cur.shiftX;
    R.cam.shiftY = cur.shiftY;

    // колёса
    spinSpeed = lerp(spinSpeed, spinOn ? goal.spin : 0, 1 - Math.pow(0.02, dt));
    spinAngle -= spinSpeed * dt;
    car.setSpin(spinAngle);

    // антикрыло / DRS
    wingAngle = lerp(wingAngle, wingGoal, 1 - Math.pow(0.004, dt));
    car.setWing(wingAngle);

    // «рентген» на слайде двигателя
    const x = cur.xray;
    car.body.opacity = 1 - 0.78 * x;
    car.aero.opacity = 1 - 0.62 * x;
    car.wing.opacity = 1 - 0.55 * x;
    car.engine.visible = x > 0.03;
    car.engine.opacity = Math.min(1, x * 1.6);
    car.engine.highlight = x * (0.18 + 0.12 * Math.sin(t * 2.0));

    // подсветка деталей (пульсация)
    const pulse = 0.55 + 0.45 * Math.sin(t * 2.4);
    car.wing.highlight = cur.hlWing * pulse * 0.7;
    for (const w of car.wheels) w.m.highlight = cur.hlWheel * pulse * 0.45;
    for (const c of car.calipers) c.m.highlight = cur.hlWheel * pulse * 0.8;

    updateGauge(t);

    R.render({ reflection: !isSmall() && cur.dims < 0.35 });
    drawDims();
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
