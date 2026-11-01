/**
 * riso-core.js — Riso 引擎共享合成核心（从 rumor-39s film.html 抽取的权威 shader）。
 * previs.html / still_spec.html 复用本文件；entry/still.html、entry/film.html 内联副本
 * 与 rumor-39s 原文一致（C01 fixture 校验基准）。
 */
const RISO = (() => {
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const easeOut = (x) => 1 - Math.pow(1 - clamp(x), 3);
  const easeInOut = (x) => { x = clamp(x); return x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2; };
  const lerp = (a, b, p) => a + (b - a) * p;
  const seg = (t, a, b) => clamp((t - a) / (b - a));

  const VS = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;

  // 权威 fragment shader：三版白墨 → 纸 + 半调网点（角度/周期可参数化）
  const FS = (inks, paper, angles, periods) => `#version 300 es
precision highp float;
uniform sampler2D uBlue, uOrange, uYellow;
uniform vec2 uRes, uOffB, uOffO, uOffY;
uniform vec3 uCam;
out vec4 outColor;

const vec3 PAPER  = vec3(${paper});
const vec3 INK_B  = vec3(${inks[0]});
const vec3 INK_O  = vec3(${inks[1]});
const vec3 INK_Y  = vec3(${inks[2]});

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float dotCoverage(float d, vec2 p, float deg, float period) {
  float a = radians(deg);
  float c = cos(a), s = sin(a);
  vec2 q = vec2(c * p.x + s * p.y, -s * p.x + c * p.y);
  vec2 f = fract(q / period) - 0.5;
  float r = length(f) * 2.0;
  float rad = sqrt(clamp(d, 0.0, 1.0)) * 0.74;
  float aa = 1.25 / period;
  return 1.0 - smoothstep(rad - aa, rad + aa, r);
}
float plateCov(float d, vec2 p, float deg, float period) {
  if (d <= 0.004) return 0.0;
  if (d >= 0.92) return 1.0;
  return dotCoverage(d, p, deg, period);
}
vec3 applyInk(vec3 col, vec3 ink, float cov) {
  vec3 k = ink / PAPER;
  return col * mix(vec3(1.0), k, cov);
}
void main() {
  vec2 p = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y);
  vec2 uvB = (p - uOffB) / uRes;
  vec2 uvO = (p - uOffO) / uRes;
  vec2 uvY = (p - uOffY) / uRes;
  float dB = texture(uBlue, uvB).a;
  float dO = texture(uOrange, uvO).a;
  float dY = texture(uYellow, uvY).a;

  vec2 q = (p - uCam.yz) / uCam.x;

  float fib = hash21(floor(q * vec2(1.0, 2.0)) + 17.0);
  float mot = hash21(floor(q / 90.0) + 3.0);
  vec3 paper = PAPER * (1.0 + (fib - 0.5) * 0.020 + (mot - 0.5) * 0.012);

  float dust = 0.0;
  dust += step(length(q - vec2(268, 946)), 2.4);
  dust += step(length(q - vec2(1332, 171)), 1.8);
  dust += step(length(q - vec2(612, 1030)), 1.4);

  vec3 col = paper;
  float covB = plateCov(dB, q, ${f1(angles[0])}, ${f1(periods[0])});
  float covO = plateCov(dO, q, ${f1(angles[1])}, ${f1(periods[1])});
  float covY = plateCov(dY, q, ${f1(angles[2])}, ${f1(periods[2])});

  float grain = 0.945 + 0.055 * hash21(floor(q * 1.3) + 9.0);
  covB *= grain; covO *= grain; covY *= grain;
  if (dB > 0.92 && hash21(floor(q * 2.2) + 31.0) < 0.010) covB = 0.22;
  if (dO > 0.92 && hash21(floor(q * 2.2) + 71.0) < 0.008) covO = 0.22;

  col = applyInk(col, INK_B, covB);
  col = applyInk(col, INK_O, covO);
  col = applyInk(col, INK_Y, covY);
  col *= 1.0 - dust * 0.35;
  outColor = vec4(col, 1.0);
}`;

  function makePlate(W, H) {
    const c = document.createElement('canvas');
    c.width = W; c.height = H;
    return c;
  }

  function hexToVec3(hex) {
    const h = hex.replace('#', '');
    const n = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
    const v = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16) / 255);
    return v.map((x) => Math.round(x * 1000) / 1000).join(', ');
  }

  // GLSL ES 3.0 不支持 int→float 隐式转换：一律格式化成浮点字面量
  const f1 = (x) => Number(x || 0).toFixed(1);

  /**
   * 合成三版到 WebGL 画布。
   * plates: [{canvas, off:[x,y]}] 1–3 版（缺省版传空 canvas，alpha=0）
   * opts: {canvas, W, H, paper:'#F4EEE2', inks:[hex×3], angles:[15,75,0], periods:[7,7,6.5], cam:{z,tx,ty}}
   */
  function composite(plates, opts) {
    const W = opts.W || 1920, H = opts.H || 1080;
    const paper = hexToVec3(opts.paper || '#F4EEE2');
    const inks = (opts.inks && opts.inks.length >= 3 ? opts.inks : ['#3D5588', '#FF665E', '#FFB511']).map(hexToVec3);
    const angles = opts.angles || [15, 75, 0];
    const periods = opts.periods || [7, 7, 6.5];
    const canvas = opts.canvas || document.getElementById('gl');
    const gl = canvas.getContext('webgl2', { antialias: false, preserveDrawingBuffer: true, premultipliedAlpha: false });
    function compile(type, src) {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error('shader: ' + gl.getShaderInfoLog(s));
      return s;
    }
    const prog = gl.createProgram();
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, VS));
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FS(inks, paper, angles, periods)));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error('link: ' + gl.getProgramInfoLog(prog));
    gl.useProgram(prog);
    const quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'aPos');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const U = (n) => gl.getUniformLocation(prog, n);
    const cam = opts.cam || { z: 1, tx: 0, ty: 0 };
    for (let i = 0; i < 3; i++) {
      const p = plates[i] || { canvas: makePlate(4, 4), off: [0, 0] };
      const t = gl.createTexture();
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, p.canvas);
      gl.uniform1i(U(['uBlue', 'uOrange', 'uYellow'][i]), i);
      gl.uniform2f(U(['uOffB', 'uOffO', 'uOffY'][i]), p.off[0], p.off[1]);
    }
    gl.uniform2f(U('uRes'), W, H);
    gl.uniform3f(U('uCam'), cam.z, cam.tx, cam.ty);
    gl.viewport(0, 0, W, H);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
    gl.finish();
    return canvas;
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  function ink(ctx, a) { ctx.fillStyle = `rgba(255,255,255,${a})`; }
  function text(ctx, str, x, y, size, weight, density = 1, font = '"Noto Sans SC"') {
    ctx.save();
    ctx.font = `${weight} ${size}px ${font}`;
    ctx.textBaseline = 'alphabetic';
    ctx.letterSpacing = '0.01em';
    ctx.fillStyle = `rgba(255,255,255,${density})`;
    ctx.fillText(str, x, y);
    ctx.restore();
  }
  function drawCross(ctx, x, y, density = 1) {
    ink(ctx, density);
    ctx.strokeStyle = `rgba(255,255,255,${density})`;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x - 26, y); ctx.lineTo(x + 26, y);
    ctx.moveTo(x, y - 26); ctx.lineTo(x, y + 26);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, 13, 0, Math.PI * 2);
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
  }

  return { clamp, easeOut, easeInOut, lerp, seg, makePlate, composite, roundRect, ink, text, drawCross, hexToVec3 };
})();
