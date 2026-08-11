/* ===========================================================================
   Мини 3D-движок на Canvas 2D.
   Плоское затенение + сортировка граней методом художника.
   Никаких внешних библиотек.
   =========================================================================== */

const V3 = {
  sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
  add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]],
  cross: (a, b) => [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0]
  ],
  dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
  scale: (a, s) => [a[0] * s, a[1] * s, a[2] * s],
  len: (a) => Math.hypot(a[0], a[1], a[2]),
  norm: (a) => {
    const l = Math.hypot(a[0], a[1], a[2]) || 1;
    return [a[0] / l, a[1] / l, a[2] / l];
  }
};

/* --- матрицы 4x4, построчно --------------------------------------------- */
const M4 = {
  id: () => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
  mul(a, b) {
    const o = new Array(16);
    for (let r = 0; r < 4; r++) {
      for (let c = 0; c < 4; c++) {
        o[r * 4 + c] =
          a[r * 4] * b[c] +
          a[r * 4 + 1] * b[4 + c] +
          a[r * 4 + 2] * b[8 + c] +
          a[r * 4 + 3] * b[12 + c];
      }
    }
    return o;
  },
  trans(x, y, z) {
    return [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z, 0, 0, 0, 1];
  },
  rotX(a) {
    const c = Math.cos(a), s = Math.sin(a);
    return [1, 0, 0, 0, 0, c, -s, 0, 0, s, c, 0, 0, 0, 0, 1];
  },
  rotY(a) {
    const c = Math.cos(a), s = Math.sin(a);
    return [c, 0, s, 0, 0, 1, 0, 0, -s, 0, c, 0, 0, 0, 0, 1];
  },
  rotZ(a) {
    const c = Math.cos(a), s = Math.sin(a);
    return [c, -s, 0, 0, s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  },
  apply(m, p) {
    return [
      m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3],
      m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7],
      m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11]
    ];
  },
  applyDir(m, p) {
    return [
      m[0] * p[0] + m[1] * p[1] + m[2] * p[2],
      m[4] * p[0] + m[5] * p[1] + m[6] * p[2],
      m[8] * p[0] + m[9] * p[1] + m[10] * p[2]
    ];
  }
};

/* --- Меш ----------------------------------------------------------------- */
class Mesh {
  constructor(name) {
    this.name = name;
    this.verts = [];
    this.faces = [];
    this.matrix = M4.id();
    this.visible = true;
    this.opacity = 1;
    this.highlight = 0; // 0..1 — подсветка детали
    this._world = [];
  }
  v(x, y, z) {
    this.verts.push([x, y, z]);
    return this.verts.length - 1;
  }
  face(idx, col, opt = {}) {
    this.faces.push({
      v: idx,
      col,
      gloss: opt.gloss === undefined ? 26 : opt.gloss,
      spec: opt.spec === undefined ? 0.55 : opt.spec,
      glass: !!opt.glass,
      emissive: opt.emissive || 0,
      paint: !!opt.paint,
      dbl: !!opt.dbl, // двусторонняя грань (не отсекать)
      tag: opt.tag || ''
    });
  }
  /* зеркальная копия по Z (левая сторона) */
  mirrorZ() {
    const n = this.verts.length;
    for (let i = 0; i < n; i++) {
      const p = this.verts[i];
      this.verts.push([p[0], p[1], -p[2]]);
    }
    const fn = this.faces.length;
    for (let i = 0; i < fn; i++) {
      const f = this.faces[i];
      const nv = f.v.map((k) => k + n).reverse();
      this.faces.push(Object.assign({}, f, { v: nv }));
    }
    return this;
  }
}

/* --- Сцена и рендер ------------------------------------------------------ */
class Renderer {
  constructor(canvas) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.meshes = [];
    this.dpr = 1;
    this.light = V3.norm([0.42, 0.82, 0.38]);
    this.fill = V3.norm([-0.55, 0.35, -0.75]);   // заполняющий свет с теневой стороны
    this.sky = [96, 122, 150];
    this.ground = [16, 18, 21];
    this.cam = {
      az: -0.9, el: 0.16, dist: 12,
      target: [0, 0.6, 0],
      fov: 640,
      shiftX: 0, shiftY: 0
    };
    this._buf = [];
  }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    const w = this.cv.clientWidth, h = this.cv.clientHeight;
    this.dpr = dpr;
    this.cv.width = Math.max(1, Math.round(w * dpr));
    this.cv.height = Math.max(1, Math.round(h * dpr));
    this.W = w; this.H = h;
  }

  camPos() {
    const c = this.cam;
    return [
      c.target[0] + c.dist * Math.cos(c.el) * Math.cos(c.az),
      c.target[1] + c.dist * Math.sin(c.el),
      c.target[2] + c.dist * Math.cos(c.el) * Math.sin(c.az)
    ];
  }

  /* матрица вида (мир -> камера) */
  viewMatrix() {
    const eye = this.camPos();
    const f = V3.norm(V3.sub(this.cam.target, eye));
    const up0 = [0, 1, 0];
    const s = V3.norm(V3.cross(f, up0));
    const u = V3.cross(s, f);
    return [
      s[0], s[1], s[2], -V3.dot(s, eye),
      u[0], u[1], u[2], -V3.dot(u, eye),
      -f[0], -f[1], -f[2], V3.dot(f, eye),
      0, 0, 0, 1
    ];
  }

  project(p) {
    // p — точка в пространстве камеры, взгляд вдоль -z
    const z = -p[2];
    const k = this.cam.fov / Math.max(z, 0.05);
    return [
      this.W / 2 + p[0] * k + this.cam.shiftX,
      this.H / 2 - p[1] * k + this.cam.shiftY,
      z
    ];
  }

  shade(col, n, wp, f, eye) {
    let r = col[0], g = col[1], b = col[2];
    const nd = Math.max(0, V3.dot(n, this.light));
    const nf = Math.max(0, V3.dot(n, this.fill));
    const hemi = 0.5 + 0.5 * n[1];
    const amb = 0.19 + 0.15 * hemi;
    let inten = amb + 0.58 * nd + 0.26 * nf;

    // отражение неба/земли для «краски»
    if (f.paint || f.glass) {
      const t = Math.max(0, Math.min(1, 0.5 + 0.5 * n[1]));
      const env = f.glass ? 0.55 : 0.22;
      r = r * (1 - env) + (this.ground[0] * (1 - t) + this.sky[0] * t) * env;
      g = g * (1 - env) + (this.ground[1] * (1 - t) + this.sky[1] * t) * env;
      b = b * (1 - env) + (this.ground[2] * (1 - t) + this.sky[2] * t) * env;
    }

    r *= inten; g *= inten; b *= inten;

    // блик
    const view = V3.norm(V3.sub(eye, wp));
    const h = V3.norm(V3.add(view, this.light));
    const sp = Math.pow(Math.max(0, V3.dot(n, h)), f.gloss) * f.spec * 255;
    r += sp; g += sp; b += sp;

    // контровой свет по кромке
    const rim = Math.pow(1 - Math.max(0, V3.dot(n, view)), 3.5) * 24;
    r += rim * 0.7; g += rim * 0.85; b += rim;

    if (f.emissive) {
      r += col[0] * f.emissive; g += col[1] * f.emissive; b += col[2] * f.emissive;
    }
    return [r, g, b];
  }

  render(opts = {}) {
    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.W, this.H);

    const view = this.viewMatrix();
    const eye = this.camPos();
    const buf = this._buf;
    buf.length = 0;

    if (opts.shadow !== false) this.drawShadow(2.35, 1.02, 0.008);

    const collect = (flip) => {
      for (const m of this.meshes) {
        if (!m.visible) continue;
        if (flip && m.noReflect) continue;
        const mm = m.matrix;
        const wp = m._world;
        for (let i = 0; i < m.verts.length; i++) {
          const p = m.verts[i];
          let o = wp[i];
          if (!o) o = wp[i] = [0, 0, 0];
          o[0] = mm[0] * p[0] + mm[1] * p[1] + mm[2] * p[2] + mm[3];
          o[1] = mm[4] * p[0] + mm[5] * p[1] + mm[6] * p[2] + mm[7];
          o[2] = mm[8] * p[0] + mm[9] * p[1] + mm[10] * p[2] + mm[11];
          if (flip) o[1] = -o[1];
        }
        for (const f of m.faces) {
          const idx = f.v;
          const a = wp[idx[0]], b = wp[idx[1]], c = wp[idx[2]];
          let n = V3.norm(V3.cross(V3.sub(b, a), V3.sub(c, a)));
          if (flip) n = [n[0], n[1], n[2]];
          const cx = (a[0] + b[0] + c[0]) / 3;
          const cy = (a[1] + b[1] + c[1]) / 3;
          const cz = (a[2] + b[2] + c[2]) / 3;
          const cen = [cx, cy, cz];
          const toEye = V3.sub(eye, cen);
          const facing = V3.dot(n, toEye);
          if (!f.dbl && !f.glass && facing < 0) continue;
          if (facing < 0) n = V3.scale(n, -1);
          if (flip && cy > 0.02) continue;

          // проекция
          const pts = [];
          let depth = 0, behind = false;
          const halfW = this.W / 2 + this.cam.shiftX;
          const halfH = this.H / 2 + this.cam.shiftY;
          for (let i = 0; i < idx.length; i++) {
            const p = wp[idx[i]];
            const vx = view[0] * p[0] + view[1] * p[1] + view[2] * p[2] + view[3];
            const vy = view[4] * p[0] + view[5] * p[1] + view[6] * p[2] + view[7];
            const vz = -(view[8] * p[0] + view[9] * p[1] + view[10] * p[2] + view[11]);
            if (vz < 0.08) { behind = true; break; }
            const kk = this.cam.fov / vz;
            pts.push([halfW + vx * kk, halfH - vy * kk]);
            depth += vz;
          }
          if (behind) continue;
          depth /= idx.length;

          let sh = this.shade(f.col, n, cen, f, eye);
          if (m.highlight > 0) {
            const k = m.highlight;
            sh = [
              sh[0] * (1 - k) + Math.min(255, sh[0] * 1.3 + 96) * k,
              sh[1] * (1 - k) + Math.min(255, sh[1] * 1.3 + 104) * k,
              sh[2] * (1 - k) + Math.min(255, sh[2] * 1.3 + 82) * k
            ];
          }
          buf.push({
            pts, depth,
            col: sh,
            alpha: (f.glass ? 0.82 : 1) * m.opacity * (flip ? 0.10 : 1),
            flip
          });
        }
      }
    };

    if (opts.reflection !== false) collect(true);
    collect(false);

    buf.sort((p, q) => q.depth - p.depth);

    ctx.lineJoin = 'round';
    for (const f of buf) {
      const c = f.col;
      const r = c[0] < 0 ? 0 : c[0] > 255 ? 255 : c[0] | 0;
      const g = c[1] < 0 ? 0 : c[1] > 255 ? 255 : c[1] | 0;
      const b = c[2] < 0 ? 0 : c[2] > 255 ? 255 : c[2] | 0;
      const style = `rgb(${r},${g},${b})`;
      ctx.globalAlpha = f.alpha;
      ctx.fillStyle = style;
      ctx.strokeStyle = style;
      ctx.lineWidth = 0.7;
      ctx.beginPath();
      ctx.moveTo(f.pts[0][0], f.pts[0][1]);
      for (let i = 1; i < f.pts.length; i++) ctx.lineTo(f.pts[i][0], f.pts[i][1]);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  /* мягкая контактная тень под машиной */
  drawShadow(len, wid, y) {
    const ctx = this.ctx;
    const view = this.viewMatrix();
    const pts = [];
    const N = 28;
    for (let i = 0; i < N; i++) {
      const a = (i / N) * Math.PI * 2;
      const p = [Math.cos(a) * len, y, Math.sin(a) * wid];
      const vp = M4.apply(view, p);
      if (-vp[2] < 0.08) return;
      pts.push(this.project(vp));
    }
    let cx = 0, cy = 0;
    for (const p of pts) { cx += p[0]; cy += p[1]; }
    cx /= pts.length; cy /= pts.length;
    let rad = 0;
    for (const p of pts) rad = Math.max(rad, Math.hypot(p[0] - cx, p[1] - cy));
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad);
    g.addColorStop(0, 'rgba(0,0,0,0.55)');
    g.addColorStop(0.55, 'rgba(0,0,0,0.28)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.save();
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }
}
