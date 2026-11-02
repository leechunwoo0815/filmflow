/**
 * scene-render.js — Scene DSL 共享渲染器（still_spec / film_spec 共用）。
 * 只读 program JSON；无 Date.now / 无未播种随机。
 */
const SCENE_RENDER = (() => {
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const seg = (t, a, b) => clamp((t - a) / (b - a));
  const FONT = '"Noto Sans SC", "PingFang SC", sans-serif';

  function cameraAt(camera, t) {
    const kfs = (camera || {}).keyframes;
    if (!kfs || !kfs.length) return { z: 1, tx: 0, ty: 0 };
    let a = kfs[0], b = kfs[kfs.length - 1];
    for (let i = 0; i < kfs.length - 1; i++) {
      if (t >= kfs[i].t && t <= kfs[i + 1].t) { a = kfs[i]; b = kfs[i + 1]; break; }
    }
    const span = b.t - a.t;
    const p = span > 0 ? clamp((t - a.t) / span) : 0;
    const z = a.zoom + (b.zoom - a.zoom) * p;
    const x = (a.x || 0) + ((b.x || 0) - (a.x || 0)) * p;
    const y = (a.y || 0) + ((b.y || 0) - (a.y || 0)) * p;
    const anchor = (camera || {}).anchor || [960, 540];
    return { z, tx: anchor[0] * (1 - z) + x, ty: anchor[1] * (1 - z) + y };
  }

  function wrapText(ctx, text, maxWidth, font, weight, size, letterSpacing) {
    ctx.save();
    ctx.font = `${weight || 500} ${size}px ${font || FONT}`;
    ctx.letterSpacing = `${letterSpacing || 0}px`;
    const out = [];
    for (const para of String(text ?? '').split('\n')) {
      let line = '';
      for (const ch of para) {
        const test = line + ch;
        if (line && ctx.measureText(test).width > maxWidth) { out.push(line); line = ch; }
        else line = test;
      }
      out.push(line);
    }
    ctx.restore();
    return out;
  }

  function alphaAt(layer, t, duration) {
    let a = 1;
    const inAnim = layer.in || {};
    if (inAnim.type === 'fade' && inAnim.duration) {
      a *= seg(t, inAnim.at || 0, (inAnim.at || 0) + inAnim.duration);
    }
    const outAnim = layer.out || {};
    if (outAnim.type === 'fade' && outAnim.duration) {
      a *= 1 - seg(t, outAnim.at ?? duration - outAnim.duration, (outAnim.at ?? duration - outAnim.duration) + outAnim.duration);
    }
    return clamp(a);
  }

  function drawText(ctx, layer, t, duration, W, H) {
    const style = layer.style || {};
    const box = layer.box || [80, 200, W - 160, H - 400];
    const size = style.size || 96;
    const weight = style.weight || 900;
    const font = style.font || FONT;
    const maxWidth = style.maxWidth || box[2];
    const lines = wrapText(ctx, layer.content, maxWidth, font, weight, size, style.letterSpacing);
    const lh = size * (style.lineHeight || 1.35);
    const a = alphaAt(layer, t, duration);
    if (a <= 0) return;
    ctx.save();
    ctx.font = `${weight} ${size}px ${font}`;
    ctx.letterSpacing = `${style.letterSpacing || 0}px`;
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = `rgba(255,255,255,${a})`;
    const reveal = layer.reveal;
    if (reveal) {
      const p = seg(t, reveal.at || 0, (reveal.at || 0) + (reveal.duration || 0.6));
      ctx.beginPath();
      ctx.rect(box[0] - 12, box[1] - size * 1.1, maxWidth + 24, (lines.length * lh + size) * p);
      ctx.clip();
    }
    lines.forEach((line, i) => {
      const width = ctx.measureText(line).width;
      const x = style.align === 'center' ? box[0] + (box[2] - width) / 2
        : style.align === 'right' ? box[0] + box[2] - width : box[0];
      ctx.fillText(line, x, box[1] + i * lh);
    });
    ctx.restore();
  }

  function drawShape(ctx, layer) {
    const box = layer.box || [0, 0, 0, 0];
    const a = clamp(layer.alpha ?? 0.9);
    ctx.save();
    ctx.fillStyle = `rgba(255,255,255,${a})`;
    if (layer.shape === 'circle') {
      ctx.beginPath();
      ctx.arc(box[0], box[1], Math.abs(box[2]) / 2, 0, Math.PI * 2);
      ctx.fill();
    } else if (layer.shape === 'line') {
      ctx.strokeStyle = `rgba(255,255,255,${a})`;
      ctx.lineWidth = layer.width || 10;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(box[0], box[1]);
      ctx.lineTo(box[0] + box[2], box[1] + box[3]);
      ctx.stroke();
    } else {
      ctx.fillRect(box[0], box[1], box[2], box[3]);
    }
    ctx.restore();
  }

  function drawLayer(ctx, layer, t, duration, W, H) {
    if (layer.type === 'text') drawText(ctx, layer, t, duration, W, H);
    else if (layer.type === 'shape') drawShape(ctx, layer);
    else if (layer.type === 'component') {
      const ok = SCENE_KIT.render(layer.component, ctx, layer.props || {}, t, { W, H });
      if (!ok) {
        ctx.save();
        ctx.strokeStyle = 'rgba(255,255,255,0.9)';
        ctx.lineWidth = 8;
        ctx.beginPath(); ctx.moveTo(W / 2 - 40, H / 2 - 40); ctx.lineTo(W / 2 + 40, H / 2 + 40);
        ctx.moveTo(W / 2 + 40, H / 2 - 40); ctx.lineTo(W / 2 - 40, H / 2 + 40); ctx.stroke();
        ctx.restore();
      }
    } else if (layer.type === 'group') {
      (layer.children || []).slice().sort((a, b) => (a.z || 0) - (b.z || 0))
        .forEach((child) => drawLayer(ctx, child, t, duration, W, H));
    } else if (layer.type === 'image') {
      const box = layer.box || [100, 100, 400, 300];
      ctx.save();
      ctx.strokeStyle = 'rgba(255,255,255,0.7)';
      ctx.lineWidth = 6;
      ctx.strokeRect(box[0], box[1], box[2], box[3]);
      ctx.beginPath(); ctx.moveTo(box[0], box[1]); ctx.lineTo(box[0] + box[2], box[1] + box[3]);
      ctx.moveTo(box[0] + box[2], box[1]); ctx.lineTo(box[0], box[1] + box[3]); ctx.stroke();
      ctx.restore();
    }
  }

  function renderProgram(program, t, opts) {
    const W = (opts && opts.W) || (program.canvas && program.canvas.w) || 1920;
    const H = (opts && opts.H) || (program.canvas && program.canvas.h) || 1080;
    const scale = (opts && opts.scale) || 1;
    const plates = [RISO.makePlate(W, H), RISO.makePlate(W, H), RISO.makePlate(W, H)];
    const cam = cameraAt(program.camera, t);
    plates.forEach((canvas) => {
      const ctx = canvas.getContext('2d');
      ctx.setTransform(cam.z * scale, 0, 0, cam.z * scale, cam.tx * scale, cam.ty * scale);
    });
    const duration = program.duration || 1;
    (program.layers || []).slice().sort((a, b) => (a.z || 0) - (b.z || 0)).forEach((layer) => {
      const key = layer.plate || 'blue';
      const ctx = plates[['blue', 'orange', 'yellow'].indexOf(key)] ? plates[['blue', 'orange', 'yellow'].indexOf(key)].getContext('2d') : plates[0].getContext('2d');
      drawLayer(ctx, layer, t, duration, W, H);
    });
    return { plates: plates.map((canvas) => ({ canvas, off: [0, 0] })), cam, W, H };
  }

  const compositors = new Map();
  function getCompositor(program, slot, W, H, scale) {
    const c = program.canvas || {};
    const key = JSON.stringify([slot, W, H, scale, c.paper, c.inks, c.angles, c.periods]);
    if (!compositors.has(key)) {
      const canvas = document.createElement('canvas');
      canvas.width = W; canvas.height = H;
      compositors.set(key, RISO.createCompositor({
        canvas, W, H, paper: c.paper, inks: c.inks,
        angles: c.angles, periods: c.periods, screenScale: scale || 1,
      }));
    }
    return compositors.get(key);
  }

  function drawInto(program, t, slot, W, H, scale) {
    const r = renderProgram(program, t, { W, H, scale });
    const comp = getCompositor(program, slot, W, H, scale);
    comp.draw(r.plates, { z: 1, tx: 0, ty: 0 });
    return comp.canvas;
  }

  function drawTransition(out, prev, cur, type, p, W, H) {
    const ctx = out.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    ctx.globalAlpha = 1;
    ctx.drawImage(prev, 0, 0);
    if (!type || type === 'cut') {
      ctx.drawImage(cur, 0, 0);
      return;
    }
    if (type === 'dissolve' || type === 'ink-bleed' && p > 0.5) {
      ctx.globalAlpha = type === 'dissolve' ? p : 1;
      if (type === 'ink-bleed') {
        ctx.save();
        const pts = [];
        for (let i = 0; i < 48; i++) {
          const ang = (i / 48) * Math.PI * 2;
          const noise = 0.72 + 0.28 * Math.abs(Math.sin(i * 12.9898));
          pts.push([W / 2 + Math.cos(ang) * W * 0.75 * p * noise,
                    H / 2 + Math.sin(ang) * H * 0.75 * p * noise]);
        }
        ctx.beginPath();
        pts.forEach((pt, i) => i ? ctx.lineTo(pt[0], pt[1]) : ctx.moveTo(pt[0], pt[1]));
        ctx.closePath(); ctx.clip();
      }
      ctx.drawImage(cur, 0, 0);
      ctx.restore();
      ctx.globalAlpha = 1;
      return;
    }
    if (type === 'match-shape') {
      ctx.save();
      ctx.beginPath();
      ctx.arc(W / 2, H / 2, Math.max(W, H) * 0.55 * p, 0, Math.PI * 2);
      ctx.clip();
      ctx.drawImage(cur, 0, 0);
      ctx.restore();
      return;
    }
    if (type === 'push') {
      ctx.clearRect(0, 0, W, H);
      ctx.drawImage(prev, -W * p, 0);
      ctx.drawImage(cur, W * (1 - p), 0);
      return;
    }
    if (type === 'glitch') {
      ctx.drawImage(cur, 0, 0);
      const rows = 18;
      for (let i = 0; i < rows; i++) {
        if ((i * 7) % 3 === 0) {
          const sy = Math.floor(H * i / rows), sh = H / rows;
          const dx = Math.sin(i * 12.9898) * 40 * (1 - p);
          ctx.drawImage(prev, 0, sy, W, sh, dx, sy, W, sh);
        }
      }
      return;
    }
    // wipe / paper-slide / 未知：从左向右擦除（paper-slide 边缘轻微倾斜）
    ctx.save();
    ctx.beginPath();
    if (type === 'paper-slide') {
      ctx.moveTo(0, 0); ctx.lineTo(W * p, 0); ctx.lineTo(W * p - 40, H); ctx.lineTo(0, H);
    } else {
      ctx.rect(0, 0, W * p, H);
    }
    ctx.closePath();
    ctx.clip();
    ctx.drawImage(cur, 0, 0);
    ctx.restore();
  }

  function renderFrameAt(programs, transitions, t, opts) {
    const W = (opts && opts.W) || 1920;
    const H = (opts && opts.H) || 1080;
    const scale = (opts && opts.scale) || 1;
    const cur = (programs || []).find((p) => t >= p.start && t < p.end) || programs[programs.length - 1];
    if (!cur) return null;
    const out = document.createElement('canvas');
    out.width = W; out.height = H;
    const curCanvas = drawInto(cur.program, Math.max(0, t - cur.start), 0, W, H, scale);
    const tr = (transitions || []).find((x) => x.to === cur.id && t >= x.at &&
      t < x.at + (x.duration || 0.5));
    if (!tr) {
      out.getContext('2d').drawImage(curCanvas, 0, 0);
      return out;
    }
    const prev = (programs || []).find((p) => p.id === tr.from);
    if (!prev) {
      out.getContext('2d').drawImage(curCanvas, 0, 0);
      return out;
    }
    const prevCanvas = drawInto(prev.program, Math.max(0, t - prev.start), 1, W, H, scale);
    drawTransition(out, prevCanvas, curCanvas, tr.type, seg(t, tr.at, tr.at + (tr.duration || 0.5)), W, H);
    return out;
  }

  return { renderProgram, renderFrameAt, cameraAt, wrapText };
})();
