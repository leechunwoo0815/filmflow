/**
 * scene-kit.js — 12 个参数化场景组件（封闭 DSL，不读项目文案）。
 * 组件只画白色 alpha 到 plate；最终油墨色由 riso-core 的 inks 决定。
 */
const SCENE_KIT = (() => {
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const seg = (t, a, b) => clamp((t - a) / (b - a));
  const alpha = (ctx, a) => { ctx.fillStyle = `rgba(255,255,255,${clamp(a)})`; };
  const FONT = '"Noto Sans SC", "PingFang SC", sans-serif';

  function roundRect(ctx, x, y, w, h, r = 0) {
    r = Math.min(r, Math.abs(w) / 2, Math.abs(h) / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  function text(ctx, str, x, y, size, weight = 500, a = 1) {
    ctx.save();
    ctx.font = `${weight} ${size}px ${FONT}`;
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = `rgba(255,255,255,${clamp(a)})`;
    ctx.fillText(String(str ?? ''), x, y);
    ctx.restore();
  }
  function rnd(i) {
    const v = Math.sin((i + 1) * 12.9898) * 43758.5453;
    return v - Math.floor(v);
  }

  const components = {
    'paper-card': {
      schema: { x: 'number', y: 'number', w: 'number', h: 'number', radius: 'number' },
      defaults: { x: 80, y: 100, w: 1760, h: 880, radius: 8, grain: 0.08 },
      render(ctx, p, t) {
        alpha(ctx, 0.035);
        roundRect(ctx, p.x, p.y, p.w, p.h, p.radius);
        ctx.fill();
        ctx.save();
        ctx.strokeStyle = 'rgba(255,255,255,0.30)';
        ctx.lineWidth = 2;
        roundRect(ctx, p.x + 14, p.y + 14, p.w - 28, p.h - 28, p.radius);
        ctx.stroke();
        ctx.restore();
        const n = Math.floor((p.w * p.h) / 90000);
        for (let i = 0; i < n; i++) {
          const x = p.x + rnd(i * 3) * p.w;
          const y = p.y + rnd(i * 3 + 1) * p.h;
          alpha(ctx, 0.05 + rnd(i * 3 + 2) * 0.08);
          ctx.fillRect(x, y, 1.6, 1.6);
        }
      },
      bbox: (p) => [p.x, p.y, p.w, p.h],
    },
    'headline': {
      schema: { text: 'string', x: 'number', y: 'number', size: 'number', weight: 'number' },
      defaults: { text: '标题', x: 160, y: 520, size: 132, weight: 900 },
      render(ctx, p, t, env) {
        const reveal = clamp((t - 0.15) / 0.6);
        ctx.save();
        ctx.beginPath();
        ctx.rect(p.x - 10, p.y - p.size * 1.1, (p.maxWidth || env.W) * reveal, p.size * 1.2);
        ctx.clip();
        text(ctx, p.text, p.x, p.y, p.size, p.weight, 1);
        ctx.restore();
      },
      bbox: (p) => [p.x, p.y - p.size, p.maxWidth || p.size * 4, p.size * 1.2],
    },
    'body-block': {
      schema: { lines: 'array', x: 'number', y: 'number', size: 'number' },
      defaults: { lines: ['正文'], x: 160, y: 620, size: 44, lineHeight: 1.5 },
      render(ctx, p, t) {
        const p0 = clamp((t - 0.3) / 0.6);
        (p.lines || []).forEach((line, i) => {
          const a = clamp(p0 * (p.lines.length) - i);
          if (a > 0) text(ctx, line, p.x, p.y + i * p.size * (p.lineHeight || 1.5), p.size, 500, a);
        });
      },
      bbox: (p) => [p.x, p.y - p.size, p.maxWidth || p.size * 8, p.size * (p.lines || []).length * 1.6],
    },
    'stamp': {
      schema: { text: 'string', x: 'number', y: 'number', size: 'number' },
      defaults: { text: '已核', x: 1500, y: 760, size: 72, rotate: -8 },
      render(ctx, p, t) {
        const s = clamp((t - 0.2) / 0.35);
        if (s <= 0) return;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotate || 0) * Math.PI / 180);
        ctx.scale(1 + (1 - s) * 0.35, 1 + (1 - s) * 0.35);
        ctx.strokeStyle = `rgba(255,255,255,${0.9 * s})`;
        ctx.lineWidth = 5;
        roundRect(ctx, -p.size * 1.6, -p.size * 0.75, p.size * 3.2, p.size * 1.5, 10);
        ctx.stroke();
        text(ctx, p.text, -p.size * 0.9, p.size * 0.25, p.size, 900, s);
        ctx.restore();
      },
      bbox: (p) => [p.x - p.size * 1.6, p.y - p.size, p.size * 3.2, p.size * 2],
    },
    'arrow-grow': {
      schema: { x1: 'number', y1: 'number', x2: 'number', y2: 'number', width: 'number' },
      defaults: { x1: 160, y1: 760, x2: 1200, y2: 760, width: 12, duration: 1.0 },
      render(ctx, p, t) {
        const k = clamp(t / Math.max(0.2, p.duration || 1.0)) * (p.progress ?? 1);
        const x2 = p.x1 + (p.x2 - p.x1) * k;
        const y2 = p.y1 + (p.y2 - p.y1) * k;
        alpha(ctx, 0.95);
        ctx.lineWidth = p.width || 12;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(p.x1, p.y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        if (k > 0.05) {
          const ang = Math.atan2(p.y2 - p.y1, p.x2 - p.x1);
          const h = Math.max(28, (p.width || 12) * 3);
          ctx.beginPath();
          ctx.moveTo(x2, y2);
          ctx.lineTo(x2 - h * Math.cos(ang - 0.5), y2 - h * Math.sin(ang - 0.5));
          ctx.lineTo(x2 - h * Math.cos(ang + 0.5), y2 - h * Math.sin(ang + 0.5));
          ctx.closePath();
          ctx.fill();
        }
      },
      bbox: (p) => [Math.min(p.x1, p.x2), Math.min(p.y1, p.y2), Math.abs(p.x2 - p.x1), Math.abs(p.y2 - p.y1)],
    },
    'hand-pointer': {
      schema: { x: 'number', y: 'number', scale: 'number', rotate: 'number' },
      defaults: { x: 1400, y: 700, scale: 1.0, rotate: -0.2 },
      render(ctx, p, t) {
        const s = p.scale || 1;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rotate || 0);
        ctx.scale(s, s);
        alpha(ctx, 0.95);
        ctx.lineCap = 'round';
        ctx.lineWidth = 38;
        ctx.beginPath();
        ctx.moveTo(180, 620);
        ctx.quadraticCurveTo(120, 300, 0, 12);
        ctx.stroke();
        roundRect(ctx, -56, -56, 112, 112, 40);
        ctx.fill();
        [[-42, 70, -0.1], [-14, 84, 0], [14, 88, 0], [42, 72, 0.1]].forEach(([fx, len, r]) => {
          ctx.save();
          ctx.translate(fx, -40);
          ctx.rotate(r);
          roundRect(ctx, -17, -len, 34, len, 17);
          ctx.fill();
          ctx.restore();
        });
        ctx.restore();
      },
      bbox: (p) => [p.x - 200 * (p.scale || 1), p.y - 200 * (p.scale || 1), 500 * (p.scale || 1), 900 * (p.scale || 1)],
    },
    'roller': {
      schema: { x: 'number', y: 'number', w: 'number', h: 'number', progress: 'number' },
      defaults: { x: 200, y: 820, w: 900, h: 42, progress: 0.6 },
      render(ctx, p, t) {
        const k = clamp((t / 1.2) * (p.progress ?? 0.6));
        const w = (p.w || 900) * k;
        alpha(ctx, 0.9);
        roundRect(ctx, p.x, p.y, w, p.h || 42, (p.h || 42) / 2);
        ctx.fill();
        ctx.save();
        ctx.strokeStyle = 'rgba(255,255,255,0.9)';
        ctx.lineWidth = 10;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(p.x + w, p.y + (p.h || 42) / 2);
        ctx.lineTo(p.x + w + 120, p.y - 60);
        ctx.stroke();
        ctx.restore();
      },
      bbox: (p) => [p.x, p.y - 80, p.w + 140, 180],
    },
    'halftone-field': {
      schema: { x: 'number', y: 'number', w: 'number', h: 'number', period: 'number', density: 'number' },
      defaults: { x: 120, y: 140, w: 1680, h: 800, period: 18, density: 0.35 },
      render(ctx, p, t) {
        const period = Math.max(6, p.period || 18);
        for (let y = p.y; y < p.y + p.h; y += period) {
          for (let x = p.x; x < p.x + p.w; x += period) {
            const i = Math.floor(x / period) * 31 + Math.floor(y / period) * 17;
            const d = (p.density || 0.35) * (0.5 + rnd(i) * 0.8);
            alpha(ctx, d * 0.35);
            ctx.beginPath();
            ctx.arc(x, y, period * 0.24, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      },
      bbox: (p) => [p.x, p.y, p.w, p.h],
    },
    'registration-cross': {
      schema: { x: 'number', y: 'number', size: 'number' },
      defaults: { x: 1768, y: 128, size: 1.0 },
      render(ctx, p, t) {
        const s = p.size || 1;
        ctx.save();
        ctx.strokeStyle = 'rgba(255,255,255,0.95)';
        ctx.lineWidth = 3 * s;
        ctx.beginPath();
        ctx.moveTo(p.x - 26 * s, p.y); ctx.lineTo(p.x + 26 * s, p.y);
        ctx.moveTo(p.x, p.y - 26 * s); ctx.lineTo(p.x, p.y + 26 * s);
        ctx.stroke();
        ctx.beginPath(); ctx.arc(p.x, p.y, 13 * s, 0, Math.PI * 2); ctx.stroke();
        alpha(ctx, 0.95);
        ctx.beginPath(); ctx.arc(p.x, p.y, 3.5 * s, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      },
      bbox: (p) => [p.x - 30, p.y - 30, 60, 60],
    },
    'evidence-card': {
      schema: { x: 'number', y: 'number', count: 'number', stagger: 'number' },
      defaults: { x: 300, y: 520, count: 5, stagger: 0.45, w: 320, h: 120 },
      render(ctx, p, t) {
        const count = Math.max(0, Math.min(12, p.count ?? 5));
        for (let i = 0; i < count; i++) {
          const k = clamp((t - i * (p.stagger || 0.45)) / 0.4);
          if (k <= 0) continue;
          const x = p.x + i * 26;
          const y = p.y + i * 18;
          ctx.save();
          ctx.globalAlpha = k;
          alpha(ctx, 0.09);
          roundRect(ctx, x, y, p.w || 320, p.h || 120, 6);
          ctx.fill();
          ctx.strokeStyle = 'rgba(255,255,255,0.55)';
          ctx.lineWidth = 2;
          roundRect(ctx, x, y, p.w || 320, p.h || 120, 6);
          ctx.stroke();
          for (let j = 0; j < 3; j++) {
            alpha(ctx, 0.45);
            ctx.fillRect(x + 24, y + 28 + j * 24, (p.w || 320) * (0.55 - j * 0.1), 6);
          }
          ctx.restore();
        }
      },
      bbox: (p) => [p.x, p.y, (p.w || 320) + (p.count || 5) * 26, (p.h || 120) + (p.count || 5) * 18],
    },
    'chart-bar': {
      schema: { x: 'number', y: 'number', w: 'number', h: 'number', values: 'array' },
      defaults: { x: 300, y: 500, w: 900, h: 320, values: [0.3, 0.6, 0.9], labels: [] },
      render(ctx, p, t) {
        const vals = p.values || [];
        const max = Math.max(1, ...vals.map((v) => Number(v) || 0));
        const bw = (p.w || 900) / Math.max(1, vals.length) * 0.55;
        const gap = (p.w || 900) / Math.max(1, vals.length);
        vals.forEach((v, i) => {
          const k = clamp((t - i * 0.12) / 0.5);
          const h = (Number(v) || 0) / max * (p.h || 320) * k;
          alpha(ctx, 0.9);
          ctx.fillRect(p.x + i * gap, p.y + (p.h || 320) - h, bw, h);
          text(ctx, String(v), p.x + i * gap, p.y + (p.h || 320) + 34, 24, 500, 0.9);
        });
      },
      bbox: (p) => [p.x, p.y, p.w, p.h + 50],
    },
    'count-up': {
      schema: { x: 'number', y: 'number', value: 'number', suffix: 'string' },
      defaults: { x: 500, y: 700, value: 100, suffix: '%', size: 160, duration: 1.2 },
      render(ctx, p, t) {
        const k = clamp(t / Math.max(0.2, p.duration || 1.2));
        text(ctx, Math.round((p.value || 0) * k) + (p.suffix || ''), p.x, p.y, p.size || 160, 900, 1);
      },
      bbox: (p) => [p.x, p.y - (p.size || 160), (p.size || 160) * 4, (p.size || 160) * 1.4],
    },
  };

  function merge(name, props) {
    const c = components[name];
    return c ? Object.assign({}, c.defaults, props || {}) : null;
  }

  return {
    components,
    names: Object.keys(components),
    defaults(name) { return merge(name); },
    render(name, ctx, props, t, env) {
      const c = components[name];
      if (!c) return false;
      c.render(ctx, merge(name, props), t, env || { W: 1920, H: 1080 });
      return true;
    },
    bbox(name, props) {
      const c = components[name];
      return c ? c.bbox(merge(name, props)) : null;
    },
  };
})();
