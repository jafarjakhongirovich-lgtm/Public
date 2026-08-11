/* ===========================================================================
   Процедурная модель Porsche 911 GT3 RS (992).
   Пропорции построены по заводским габаритам:
   длина 4572 / ширина 1900 / высота 1322 / колёсная база 2457 мм.
   =========================================================================== */

/* активный цвет кузова — общий объект, мутируется при смене цвета */
const PAINT = [166, 192, 60];
const PAINT_DARK = [0, 0, 0];

const COL = {
  carbon: [30, 32, 35],
  carbonLite: [46, 49, 53],
  glass: [16, 20, 26],
  tire: [24, 25, 27],
  rim: [178, 182, 186],
  rimDark: [108, 112, 116],
  disc: [96, 99, 104],
  caliper: [186, 30, 26],
  lamp: [206, 222, 235],
  tail: [188, 26, 24],
  chrome: [112, 118, 124],
  black: [18, 19, 21]
};

function setPaint(hex) {
  const n = parseInt(hex.slice(1), 16);
  PAINT[0] = (n >> 16) & 255;
  PAINT[1] = (n >> 8) & 255;
  PAINT[2] = n & 255;
  PAINT_DARK[0] = PAINT[0] * 0.45;
  PAINT_DARK[1] = PAINT[1] * 0.45;
  PAINT_DARK[2] = PAINT[2] * 0.45;
}
setPaint('#a6c03c');

/* ---- примитивы ---------------------------------------------------------- */
function box(m, x0, x1, y0, y1, z0, z1, col, opt = {}) {
  // границы нормализуются, чтобы обход вершин всегда давал наружные нормали
  if (x0 > x1) { const t = x0; x0 = x1; x1 = t; }
  if (y0 > y1) { const t = y0; y0 = y1; y1 = t; }
  if (z0 > z1) { const t = z0; z0 = z1; z1 = t; }
  const a = m.v(x0, y0, z0), b = m.v(x1, y0, z0), c = m.v(x1, y1, z0), d = m.v(x0, y1, z0);
  const e = m.v(x0, y0, z1), f = m.v(x1, y0, z1), g = m.v(x1, y1, z1), h = m.v(x0, y1, z1);
  m.face([d, c, b, a], col, opt);   // -z
  m.face([e, f, g, h], col, opt);   // +z
  m.face([a, b, f, e], col, opt);   // -y
  m.face([h, g, c, d], col, opt);   // +y
  m.face([h, d, a, e], col, opt);   // -x
  m.face([c, g, f, b], col, opt);   // +x
}

function quad(m, p0, p1, p2, p3, col, opt = {}) {
  const a = m.v(p0[0], p0[1], p0[2]);
  const b = m.v(p1[0], p1[1], p1[2]);
  const c = m.v(p2[0], p2[1], p2[2]);
  const d = m.v(p3[0], p3[1], p3[2]);
  m.face([a, b, c, d], col, opt);
}

/* ---- сечения кузова -----------------------------------------------------
   Каждая станция: x, полуширина w, низ yb, линия плеча (крыло) ys,
   верх по центру yt, полуширина крыши rw. Всё в метрах.
   ya — высота нижней кромки у наружных точек: там, где она поднята,
   образуется вырез колёсной арки.                                        */
const STATIONS = [
  { x:  2.286, w: 0.70, yb: 0.31, ys: 0.53, yt: 0.485, rw: 0.46 },
  { x:  2.21,  w: 0.845, yb: 0.20, ys: 0.575, yt: 0.505, rw: 0.55 },
  { x:  2.05,  w: 0.90, yb: 0.145, ys: 0.635, yt: 0.535, rw: 0.62, ya: 0.19 },
  { x:  1.80,  w: 0.93, yb: 0.13, ys: 0.70, yt: 0.58, rw: 0.66, ya: 0.34 },
  { x:  1.52,  w: 0.95, yb: 0.155, ys: 0.725, yt: 0.605, rw: 0.68, ya: 0.52 },
  { x:  1.23,  w: 0.95, yb: 0.17, ys: 0.74, yt: 0.645, rw: 0.69, ya: 0.55 },
  { x:  0.95,  w: 0.945, yb: 0.185, ys: 0.75, yt: 0.755, rw: 0.71, ya: 0.50 },
  { x:  0.80,  w: 0.94, yb: 0.19, ys: 0.757, yt: 0.86, rw: 0.70, ya: 0.30 },
  { x:  0.55,  w: 0.935, yb: 0.20, ys: 0.767, yt: 1.06, rw: 0.65, ya: 0.22 },
  { x:  0.25,  w: 0.935, yb: 0.20, ys: 0.777, yt: 1.25, rw: 0.60 },
  { x: -0.10,  w: 0.94, yb: 0.205, ys: 0.788, yt: 1.318, rw: 0.575 },
  { x: -0.45,  w: 0.945, yb: 0.205, ys: 0.80, yt: 1.322, rw: 0.575 },
  { x: -0.78,  w: 0.95, yb: 0.20, ys: 0.815, yt: 1.255, rw: 0.578, ya: 0.26 },
  { x: -1.00,  w: 0.95, yb: 0.198, ys: 0.83, yt: 1.19, rw: 0.59, ya: 0.46 },
  { x: -1.23,  w: 0.955, yb: 0.195, ys: 0.85, yt: 1.115, rw: 0.61, ya: 0.58 },
  { x: -1.50,  w: 0.95, yb: 0.19, ys: 0.875, yt: 1.02, rw: 0.68, ya: 0.55 },
  { x: -1.78,  w: 0.935, yb: 0.185, ys: 0.893, yt: 0.972, rw: 0.73, ya: 0.32 },
  { x: -2.05,  w: 0.89, yb: 0.19, ys: 0.888, yt: 0.945, rw: 0.72 },
  { x: -2.24,  w: 0.80, yb: 0.24, ys: 0.85, yt: 0.90, rw: 0.66 },
  { x: -2.286, w: 0.66, yb: 0.34, ys: 0.78, yt: 0.82, rw: 0.54 }
];

function sectionPts(s) {
  const { w, yb, ys, yt, rw } = s;
  const ya = s.ya === undefined ? yb : s.ya;      // кромка арки
  const yl = Math.max(ya, yb + (ys - yb) * 0.30); // низ боковины
  return [
    [w * 0.80, ya],
    [w * 0.985, yl],
    [w, ys],
    [w * 0.94, ys + (yt - ys) * 0.42],
    [rw * 1.02, yb + (yt - yb) * 0.99],
    [rw * 0.55, yt],
    [0, yt],
    [-rw * 0.55, yt],
    [-rw * 1.02, yb + (yt - yb) * 0.99],
    [-w * 0.94, ys + (yt - ys) * 0.42],
    [-w, ys],
    [-w * 0.985, yl],
    [-w * 0.80, ya],
    [0, yb]
  ];
}

/* какой материал у грани обшивки */
function skinMaterial(x, y, z, jHigh) {
  const az = Math.abs(z);
  // лобовое стекло
  if (x > 0.25 && x < 0.90 && y > 0.88 && az < 0.72) return 'glass';
  // боковые стёкла
  if (x > -1.05 && x < 0.40 && y > 0.92 && az > 0.42) return 'glass';
  // заднее стекло
  if (x > -1.40 && x < -0.90 && y > 0.98 && az < 0.70) return 'glass';
  // крыша — карбон (Weissach)
  if (x > -0.95 && x < 0.30 && y > 1.20 && az < 0.62) return 'roof';
  // днище
  if (y < 0.24 && jHigh === false) return 'under';
  return 'paint';
}

/* ---- кузов -------------------------------------------------------------- */
function buildBody() {
  const m = new Mesh('body');
  const rows = STATIONS.map((s) => sectionPts(s));
  const idx = [];
  for (let i = 0; i < STATIONS.length; i++) {
    const row = [];
    for (const p of rows[i]) row.push(m.v(STATIONS[i].x, p[1], p[0]));
    idx.push(row);
  }
  const N = rows[0].length;
  for (let i = 0; i < STATIONS.length - 1; i++) {
    for (let j = 0; j < N; j++) {
      const j2 = (j + 1) % N;
      const a = idx[i][j], b = idx[i][j2], c = idx[i + 1][j2], d = idx[i + 1][j];
      const pa = m.verts[a], pb = m.verts[b], pc = m.verts[c], pd = m.verts[d];
      const x = (pa[0] + pc[0]) / 2;
      const y = (pa[1] + pb[1] + pc[1] + pd[1]) / 4;
      const z = (pa[2] + pb[2] + pc[2] + pd[2]) / 4;
      // j = 12 и 13 — плоскости днища и внутренние поверхности арок
      const mat = (j >= 12) ? 'under' : skinMaterial(x, y, z, y > 0.30);
      if (mat === 'glass') {
        m.face([a, b, c, d], COL.glass, { glass: true, gloss: 90, spec: 0.9 });
      } else if (mat === 'roof') {
        m.face([a, b, c, d], COL.carbon, { gloss: 60, spec: 0.5, paint: true });
      } else if (mat === 'under') {
        m.face([a, b, c, d], COL.black, { gloss: 8, spec: 0.05 });
      } else {
        m.face([a, b, c, d], PAINT, { gloss: 34, spec: 0.62, paint: true });
      }
    }
  }
  // заглушки передка и кормы
  const capF = idx[0], capR = idx[idx.length - 1];
  for (let j = 1; j < N - 1; j++) {
    m.face([capF[0], capF[j + 1], capF[j]], PAINT, { gloss: 30, spec: 0.5, paint: true });
  }
  for (let j = 1; j < N - 1; j++) {
    m.face([capR[0], capR[j], capR[j + 1]], COL.carbonLite, { gloss: 24, spec: 0.4 });
  }
  return m;
}

/* ---- аэродинамика и обвес ----------------------------------------------- */
function buildAeroKit() {
  const m = new Mesh('aero');
  // передний сплиттер
  quad(m, [2.35, 0.115, 0.78], [2.35, 0.115, -0.78], [1.95, 0.135, -0.95], [1.95, 0.135, 0.95],
    COL.carbon, { gloss: 40, spec: 0.35, dbl: true });
  quad(m, [2.35, 0.115, 0.78], [2.30, 0.30, 0.71], [2.30, 0.30, -0.71], [2.35, 0.115, -0.78],
    COL.carbonLite, { gloss: 40, spec: 0.35, dbl: true });
  // дайв-планы по краям сплиттера
  quad(m, [2.30, 0.30, 0.90], [2.06, 0.40, 0.965], [2.02, 0.40, 0.94], [2.26, 0.30, 0.875],
    COL.carbon, { gloss: 40, spec: 0.4, dbl: true });
  quad(m, [2.30, 0.30, -0.90], [2.26, 0.30, -0.875], [2.02, 0.40, -0.94], [2.06, 0.40, -0.965],
    COL.carbon, { gloss: 40, spec: 0.4, dbl: true });
  // пороги
  box(m, 1.05, -1.15, 0.115, 0.235, 0.90, 1.00, COL.carbon, { gloss: 30, spec: 0.3 });
  box(m, 1.05, -1.15, 0.115, 0.235, -1.00, -0.90, COL.carbon, { gloss: 30, spec: 0.3 });
  // диффузор
  quad(m, [-2.10, 0.20, 0.86], [-2.10, 0.20, -0.86], [-2.34, 0.44, -0.78], [-2.34, 0.44, 0.78],
    COL.carbon, { gloss: 34, spec: 0.35, dbl: true });
  for (let i = -2; i <= 2; i++) {
    const z = i * 0.30;
    box(m, -2.32, -2.08, 0.21, 0.44, z - 0.022, z + 0.022, COL.carbonLite, { gloss: 30, spec: 0.3 });
  }
  // боковые воздухозаборники (за дверьми)
  quad(m, [-1.05, 0.62, 0.955], [-1.45, 0.66, 0.94], [-1.45, 0.86, 0.94], [-1.08, 0.80, 0.955],
    COL.black, { gloss: 12, spec: 0.1 });
  quad(m, [-1.05, 0.62, -0.955], [-1.08, 0.80, -0.955], [-1.45, 0.86, -0.94], [-1.45, 0.66, -0.94],
    COL.black, { gloss: 12, spec: 0.1 });
  // прорези над передними крыльями (выпуск воздуха из колёсных арок)
  for (let s = -1; s <= 1; s += 2) {
    for (let i = 0; i < 3; i++) {
      const x = 1.62 - i * 0.13;
      quad(m,
        [x, 0.745, s * 0.52], [x - 0.085, 0.745, s * 0.52],
        [x - 0.085, 0.735, s * 0.80], [x, 0.735, s * 0.80],
        COL.black, { gloss: 10, spec: 0.08, dbl: true });
    }
  }
  // NACA-каналы на капоте
  for (let s = -1; s <= 1; s += 2) {
    quad(m, [1.95, 0.545, s * 0.20], [1.55, 0.615, s * 0.16],
      [1.55, 0.615, s * 0.34], [1.95, 0.545, s * 0.40],
      COL.black, { gloss: 14, spec: 0.12, dbl: true });
  }
  // жалюзи моторного отсека — узкие щели по линии крышки
  const deckY = (x) => 1.032 + (x + 1.44) * 0.17;
  for (let i = 0; i < 6; i++) {
    const x = -1.46 - i * 0.078;
    const y0 = deckY(x), y1 = deckY(x - 0.034);
    const zw = 0.60 - i * 0.012;
    quad(m, [x, y0 + 0.004, zw], [x - 0.034, y1 + 0.004, zw],
      [x - 0.034, y1 + 0.004, -zw], [x, y0 + 0.004, -zw],
      COL.black, { gloss: 16, spec: 0.15, dbl: true });
    quad(m, [x - 0.034, y1 + 0.004, zw], [x - 0.034, y1 + 0.028, zw],
      [x - 0.034, y1 + 0.028, -zw], [x - 0.034, y1 + 0.004, -zw],
      COL.carbonLite, { gloss: 30, spec: 0.3, dbl: true });
  }
  // выхлоп по центру
  box(m, -2.36, -2.20, 0.30, 0.42, -0.16, -0.04, COL.chrome, { gloss: 70, spec: 0.8 });
  box(m, -2.36, -2.20, 0.30, 0.42, 0.04, 0.16, COL.chrome, { gloss: 70, spec: 0.8 });
  // зеркала на «крыле-ножке»
  for (let s = -1; s <= 1; s += 2) {
    box(m, 0.78, 0.66, 0.79, 0.825, s * 0.905, s * 0.985, COL.carbon, { gloss: 40, spec: 0.4 });
    box(m, 0.76, 0.60, 0.82, 0.935, s * 0.965, s * 1.055, PAINT, { gloss: 40, spec: 0.6, paint: true });
  }
  // фары
  for (let s = -1; s <= 1; s += 2) {
    quad(m, [2.085, 0.555, s * 0.56], [2.025, 0.63, s * 0.64],
      [2.045, 0.63, s * 0.79], [2.105, 0.565, s * 0.745],
      COL.lamp, { gloss: 90, spec: 0.9, emissive: 0.12, dbl: true });
  }
  // задняя световая полоса
  quad(m, [-2.255, 0.66, 0.62], [-2.255, 0.66, -0.62], [-2.245, 0.735, -0.62], [-2.245, 0.735, 0.62],
    COL.tail, { gloss: 60, spec: 0.7, emissive: 0.6, dbl: true });
  // надпись-планка PORSCHE
  quad(m, [-2.28, 0.80, 0.40], [-2.28, 0.80, -0.40], [-2.275, 0.845, -0.40], [-2.275, 0.845, 0.40],
    COL.chrome, { gloss: 80, spec: 0.9, dbl: true });
  return m;
}

/* ---- заднее антикрыло «лебединая шея» ----------------------------------- */
function buildWing() {
  const m = new Mesh('wing');
  m.pivot = [-1.96, 1.44, 0];
  const span = 0.90;
  // профиль (хорда 0.46), точки от передней кромки к задней
  const prof = [
    [0.00, 0.000, 0.000],
    [0.08, 0.036, -0.028],
    [0.20, 0.046, -0.052],
    [0.34, 0.030, -0.072],
    [0.46, 0.004, -0.088]
  ];
  const top = [], bot = [];
  for (const p of prof) {
    top.push([-p[0], p[1], 0]);
    bot.push([-p[0], p[2], 0]);
  }
  const mk = (z) => {
    const t = top.map((p) => m.v(p[0], p[1], z));
    const b = bot.map((p) => m.v(p[0], p[1], z));
    return { t, b };
  };
  const L = mk(span), R = mk(-span);
  for (let i = 0; i < prof.length - 1; i++) {
    m.face([R.t[i], R.t[i + 1], L.t[i + 1], L.t[i]], COL.carbonLite, { gloss: 55, spec: 0.5 });
    m.face([L.b[i], L.b[i + 1], R.b[i + 1], R.b[i]], COL.carbon, { gloss: 45, spec: 0.4 });
  }
  // торцы профиля
  for (const s of [L, R]) {
    for (let i = 0; i < prof.length - 1; i++) {
      m.face([s.t[i], s.b[i], s.b[i + 1], s.t[i + 1]], COL.carbon, { gloss: 40, spec: 0.35, dbl: true });
    }
  }
  // передняя и задняя кромки
  m.face([L.t[0], L.b[0], R.b[0], R.t[0]], COL.carbonLite, { gloss: 60, spec: 0.6, dbl: true });
  const last = prof.length - 1;
  m.face([R.t[last], R.b[last], L.b[last], L.t[last]], COL.carbon, { gloss: 40, spec: 0.4, dbl: true });
  // гурни-флэп
  box(m, -0.50, -0.46, 0.00, 0.055, -span, span, COL.carbon, { gloss: 45, spec: 0.4 });
  // боковые пластины
  for (const s of [1, -1]) {
    const z = s * span;
    quad(m, [0.10, -0.20, z], [-0.56, -0.20, z], [-0.56, 0.14, z], [0.10, 0.10, z],
      COL.carbon, { gloss: 45, spec: 0.45, dbl: true });
    quad(m, [0.10, -0.20, z * 1.03], [0.10, 0.10, z * 1.03], [-0.56, 0.14, z * 1.03], [-0.56, -0.20, z * 1.03],
      COL.carbonLite, { gloss: 45, spec: 0.45, dbl: true });
  }
  // «лебединая шея» — стойки крепятся сверху к крылу
  for (const s of [1, -1]) {
    const z = s * 0.46;
    box(m, -0.30, -0.16, 0.02, 0.10, z - 0.035, z + 0.035, COL.carbonLite, { gloss: 50, spec: 0.5 });
    quad(m, [-0.16, 0.06, z - 0.035], [0.16, -0.20, z - 0.035], [0.24, -0.50, z - 0.035], [0.10, -0.50, z - 0.035],
      COL.carbon, { gloss: 45, spec: 0.45, dbl: true });
    quad(m, [-0.16, 0.06, z + 0.035], [0.10, -0.50, z + 0.035], [0.24, -0.50, z + 0.035], [0.16, -0.20, z + 0.035],
      COL.carbon, { gloss: 45, spec: 0.45, dbl: true });
    quad(m, [-0.16, 0.06, z - 0.035], [0.10, -0.50, z - 0.035], [0.10, -0.50, z + 0.035], [-0.16, 0.06, z + 0.035],
      COL.carbonLite, { gloss: 50, spec: 0.5, dbl: true });
    quad(m, [-0.30, 0.02, z - 0.035], [0.24, -0.50, z - 0.035], [0.24, -0.50, z + 0.035], [-0.30, 0.02, z + 0.035],
      COL.carbon, { gloss: 45, spec: 0.45, dbl: true });
  }
  return m;
}

/* ---- колесо ------------------------------------------------------------- */
function buildWheel(R, halfW, outSign, spokes) {
  const m = new Mesh('wheel');
  const N = 16;
  const Rr = R * 0.735;           // посадочный диаметр (кромка диска)
  const zo = outSign * halfW;     // внешняя сторона
  const zi = -outSign * halfW;    // внутренняя
  const ringO = [], ringI = [], rimO = [], rimI = [];
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    const cx = Math.cos(a), cy = Math.sin(a);
    ringO.push(m.v(cx * R, cy * R, zo * 0.92));
    ringI.push(m.v(cx * R, cy * R, zi * 0.92));
    rimO.push(m.v(cx * Rr, cy * Rr, zo));
    rimI.push(m.v(cx * Rr, cy * Rr, zi));
  }
  for (let i = 0; i < N; i++) {
    const j = (i + 1) % N;
    // протектор
    m.face([ringO[i], ringO[j], ringI[j], ringI[i]], COL.tire, { gloss: 6, spec: 0.06, dbl: true });
    // боковины
    m.face([rimO[i], rimO[j], ringO[j], ringO[i]], [30, 31, 34], { gloss: 10, spec: 0.1, dbl: true });
    m.face([ringI[i], ringI[j], rimI[j], rimI[i]], [22, 23, 25], { gloss: 8, spec: 0.08, dbl: true });
  }
  // тормозной диск
  const zd = outSign * halfW * 0.30;
  const dR = R * 0.66, hub = R * 0.16;
  const dOut = [], dIn = [];
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    dOut.push(m.v(Math.cos(a) * dR, Math.sin(a) * dR, zd));
    dIn.push(m.v(Math.cos(a) * hub, Math.sin(a) * hub, zd));
  }
  for (let i = 0; i < N; i++) {
    const j = (i + 1) % N;
    m.face([dIn[i], dIn[j], dOut[j], dOut[i]], COL.disc, { gloss: 22, spec: 0.25, dbl: true });
  }
  // обод (кольцо диска)
  const zf = outSign * halfW * 0.86;
  const oOut = [], oIn = [];
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    oOut.push(m.v(Math.cos(a) * Rr * 0.995, Math.sin(a) * Rr * 0.995, zf));
    oIn.push(m.v(Math.cos(a) * Rr * 0.88, Math.sin(a) * Rr * 0.88, zf));
  }
  for (let i = 0; i < N; i++) {
    const j = (i + 1) % N;
    m.face([oIn[i], oIn[j], oOut[j], oOut[i]], COL.rim, { gloss: 46, spec: 0.55, dbl: true });
  }
  // спицы
  for (let s = 0; s < spokes; s++) {
    const a = (s / spokes) * Math.PI * 2;
    const wA = Math.PI / spokes * 0.42;
    const r0 = R * 0.17, r1 = Rr * 0.90;
    const p = (r, off) => [Math.cos(a + off) * r, Math.sin(a + off) * r, zf];
    quad(m, p(r0, -wA * 1.5), p(r1, -wA), p(r1, wA), p(r0, wA * 1.5),
      COL.rim, { gloss: 40, spec: 0.5, dbl: true });
    quad(m, p(r0, -wA * 1.5), p(r0, wA * 1.5), p(r1, wA), p(r1, -wA),
      COL.rimDark, { gloss: 30, spec: 0.35, dbl: true });
  }
  // центральная гайка
  const cN = 8, cR = R * 0.16;
  const capIdx = [];
  for (let i = 0; i < cN; i++) {
    const a = (i / cN) * Math.PI * 2;
    capIdx.push(m.v(Math.cos(a) * cR, Math.sin(a) * cR, zf * 1.06));
  }
  for (let i = 1; i < cN - 1; i++) {
    m.face([capIdx[0], capIdx[i], capIdx[i + 1]], [196, 168, 60], { gloss: 60, spec: 0.7, dbl: true });
  }
  return m;
}

/* суппорт не вращается — отдельным мешем */
function buildCaliper(R, halfW, outSign) {
  const m = new Mesh('caliper');
  m.noReflect = true;
  const zc = outSign * halfW * 0.30;
  const r = R * 0.60;
  quad(m, [-0.05, r * 0.98, zc + outSign * 0.05], [0.16, r * 0.86, zc + outSign * 0.05],
    [0.16, r * 0.62, zc + outSign * 0.05], [-0.05, r * 0.70, zc + outSign * 0.05],
    COL.caliper, { gloss: 40, spec: 0.5, dbl: true });
  quad(m, [-0.05, r * 0.98, zc - outSign * 0.02], [-0.05, r * 0.70, zc - outSign * 0.02],
    [0.16, r * 0.62, zc - outSign * 0.02], [0.16, r * 0.86, zc - outSign * 0.02],
    COL.caliper, { gloss: 40, spec: 0.5, dbl: true });
  quad(m, [-0.05, r * 0.98, zc - outSign * 0.02], [0.16, r * 0.86, zc - outSign * 0.02],
    [0.16, r * 0.86, zc + outSign * 0.05], [-0.05, r * 0.98, zc + outSign * 0.05],
    [150, 24, 20], { gloss: 40, spec: 0.5, dbl: true });
  return m;
}

/* ---- оппозитный 6-цилиндровый двигатель (для «разрезного» слайда) -------- */
function buildEngine() {
  const m = new Mesh('engine');
  const cx = -1.62, cy = 0.52, len = 0.62;
  // картер
  box(m, cx - 0.34, cx + 0.34, cy - 0.18, cy + 0.20, -0.26, 0.26,
    [78, 82, 88], { gloss: 30, spec: 0.35 });
  // блоки цилиндров слева и справа (по 3)
  for (const s of [1, -1]) {
    for (let i = 0; i < 3; i++) {
      const x = cx - 0.24 + i * 0.24;
      box(m, x - 0.09, x + 0.09, cy - 0.10, cy + 0.10, s * 0.26, s * 0.60,
        [104, 108, 114], { gloss: 34, spec: 0.4 });
      box(m, x - 0.11, x + 0.11, cy - 0.13, cy + 0.13, s * 0.60, s * 0.70,
        [138, 142, 148], { gloss: 44, spec: 0.5 });
    }
    // распредвалы / крышка ГБЦ
    box(m, cx - 0.38, cx + 0.38, cy + 0.13, cy + 0.20, s * 0.30, s * 0.66,
      [166, 170, 176], { gloss: 50, spec: 0.55 });
  }
  // впуск с индивидуальными дросселями
  box(m, cx - 0.40, cx + 0.40, cy + 0.24, cy + 0.34, -0.20, 0.20,
    [58, 62, 68], { gloss: 30, spec: 0.35 });
  for (const s of [1, -1]) {
    for (let i = 0; i < 3; i++) {
      const x = cx - 0.24 + i * 0.24;
      box(m, x - 0.05, x + 0.05, cy + 0.20, cy + 0.28, s * 0.20, s * 0.34,
        [40, 44, 50], { gloss: 26, spec: 0.3 });
    }
  }
  // выпускные коллекторы
  for (const s of [1, -1]) {
    for (let i = 0; i < 3; i++) {
      const x = cx - 0.24 + i * 0.24;
      box(m, x - 0.035, x + 0.035, cy - 0.30, cy - 0.08, s * 0.44, s * 0.51,
        [126, 96, 74], { gloss: 24, spec: 0.3 });
    }
    box(m, cx - 0.34, cx + 0.34, cy - 0.36, cy - 0.28, s * 0.34, s * 0.52,
      [112, 84, 64], { gloss: 22, spec: 0.28 });
  }
  m.visible = false;
  return m;
}

/* ---- сборка ------------------------------------------------------------- */
function buildCar() {
  const FRONT_AXLE = 1.228, REAR_AXLE = -1.229;
  const Rf = 0.3505, Rr = 0.3671;     // 275/35 ZR20 и 335/30 ZR21
  const hwF = 0.1375, hwR = 0.1675;
  const zF = 0.812, zR = 0.828;

  const body = buildBody();
  const aero = buildAeroKit();
  const wing = buildWing();
  const engine = buildEngine();

  const wheels = [
    { m: buildWheel(Rf, hwF, 1, 10), x: FRONT_AXLE, z: zF, R: Rf },
    { m: buildWheel(Rf, hwF, -1, 10), x: FRONT_AXLE, z: -zF, R: Rf },
    { m: buildWheel(Rr, hwR, 1, 10), x: REAR_AXLE, z: zR, R: Rr },
    { m: buildWheel(Rr, hwR, -1, 10), x: REAR_AXLE, z: -zR, R: Rr }
  ];
  const calipers = [
    { m: buildCaliper(Rf, hwF, 1), x: FRONT_AXLE, z: zF, R: Rf },
    { m: buildCaliper(Rf, hwF, -1), x: FRONT_AXLE, z: -zF, R: Rf },
    { m: buildCaliper(Rr, hwR, 1), x: REAR_AXLE, z: zR, R: Rr },
    { m: buildCaliper(Rr, hwR, -1), x: REAR_AXLE, z: -zR, R: Rr }
  ];

  for (const w of wheels) w.m.matrix = M4.trans(w.x, w.R, w.z);
  for (const c of calipers) c.m.matrix = M4.trans(c.x, c.R, c.z);
  wing.matrix = M4.trans(wing.pivot[0], wing.pivot[1], wing.pivot[2]);

  return {
    body, aero, wing, engine, wheels, calipers,
    meshes: [body, aero, wing, engine, ...wheels.map((w) => w.m), ...calipers.map((c) => c.m)],
    setSpin(rad) {
      for (const w of this.wheels) {
        w.m.matrix = M4.mul(M4.trans(w.x, w.R, w.z), M4.rotZ(rad));
      }
    },
    setWing(angleRad) {
      const p = this.wing.pivot;
      this.wing.matrix = M4.mul(M4.trans(p[0], p[1], p[2]), M4.rotZ(angleRad));
    }
  };
}
