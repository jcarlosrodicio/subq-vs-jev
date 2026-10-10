(async function () {
  const data = await fetch("data/results.json").then((r) => r.json());
  const LENS = data.meta.lengths;
  const SHARED = LENS.filter((l) => l <= 30000);
  const COLOR = { subq: "var(--subq)", jev: "var(--jev)", jev_chunked: "var(--jev)" };
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const seen = new Set(); // components that already played their entrance animation

  let lang = (() => {
    const q = new URLSearchParams(location.search).get("lang");
    if (q && I18N[q]) return q;
    try { const s = localStorage.getItem("lang"); if (s && I18N[s]) return s; } catch (e) {}
    return "en";
  })();
  const T = () => I18N[lang];

  // ---------- helpers ----------
  const nf = (d) => new Intl.NumberFormat(lang, { minimumFractionDigits: d, maximumFractionDigits: d });
  const pct = (x, d = 1) => nf(d).format(x * 100);
  const P = (x, d = 1) => pct(x, d) + (lang === "es" ? "\u00a0%" : "%");
  const num = (x, d) => nf(d).format(x);
  const K = (l) => `${l / 1000}K`;
  const fill = (s, vars) => s.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? vars[k] : `{${k}}`));
  const $ = (s) => document.querySelector(s);
  function h(tag, attrs = {}, parent, text) {
    const svgTags = ["svg", "g", "path", "line", "rect", "circle", "text", "clipPath", "defs", "polyline", "title"];
    const el = svgTags.includes(tag) ? document.createElementNS("http://www.w3.org/2000/svg", tag) : document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) el.setAttribute(k, v);
    if (text !== undefined) el.textContent = text;
    if (parent) parent.appendChild(el);
    return el;
  }
  function onView(el, key, cb, threshold = 0.3) {
    if (seen.has(key) || reduced) { seen.add(key); cb(true); return; }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { io.disconnect(); seen.add(key); cb(false); }
    }, { threshold });
    io.observe(el);
  }
  function tween(ms, step, done) {
    const t0 = performance.now();
    (function frame(now) {
      const t = Math.min(1, (now - t0) / ms);
      step(1 - Math.pow(1 - t, 3));
      if (t < 1) requestAnimationFrame(frame); else if (done) done();
    })(t0);
  }
  const row = (series, length) => data.by_length.find((r) => r.series === series && r.length === length);
  const lat = (series, length) => data.latency.find((r) => r.series === series && r.length === length);
  const longSeries = (l) => (l > 30000 ? "jev_chunked" : "jev");
  const autoAt = (s, l) => data.automation.by_length.find((x) => x.series === s && x.length === l).coverage;

  // ---------- numbers used in the copy ----------
  function vars() {
    const cal = data.calibration;
    const bin75 = cal.long.subq.bins.find((b) => b.lo === 0.7);
    const rb = data.robustness;
    const short = Math.min(...["subq", "jev"].flatMap((s) => LENS.filter((l) => l <= 16000).map((l) => row(s, l).acc)));
    return {
      answers: num(data.meta.answers_graded, 0),
      logs: data.meta.logs_per_length,
      cellq: data.meta.logs_per_length * 2,
      short: pct(short),
      subq360: pct(row("subq", 360000).acc),
      jev360: pct(row("jev_chunked", 360000).acc),
      subqece: num(cal.shared.subq.ece, 3),
      jevece: num(cal.shared.jev.ece, 3),
      subqecelong: num(cal.long.subq.ece, 3),
      jevcece: num(cal.long.jev_chunked.ece, 3),
      subq75: pct(bin75.acc, 0),
      jevsame: pct(rb.jev.repeat_same_answer_rate),
      jevshuffle: Math.round(rb.jev.option_shuffle_flip_rate * rb.jev.option_shuffle_n),
      n: rb.jev.option_shuffle_n,
      date: new Date(data.meta.first_call).toLocaleDateString(lang, { day: "numeric", month: "long", year: "numeric" }),
      versions: Object.values(data.meta.model_versions).flat().join(", "),
      subqshort: pct(data.head_to_head.subq.overall.acc),
      jevshort: pct(data.head_to_head.jev.overall.acc),
      s30: pct(row("subq", 30000).acc),
      s64: pct(row("subq", 64000).acc),
      s360: pct(row("subq", 360000).acc),
      subq8: num(lat("subq", 8000).p50, 2),
      subq128: num(lat("subq", 128000).p50, 2),
      jev8: num(lat("jev", 8000).p50, 2),
      jevc360: pct(row("jev_chunked", 360000).acc),
      jeva1: pct(data.head_to_head.jev.families.A1.acc),
      subqa1: pct(data.head_to_head.subq.families.A1.acc),
      autos30: pct(autoAt("subq", 30000), 0),
      autos360: pct(autoAt("subq", 360000), 0),
      autojmin: pct(Math.min(...LENS.filter((l) => l > 30000).map((l) => autoAt("jev_chunked", l))), 0),
      autojmax: pct(Math.max(...LENS.filter((l) => l > 30000).map((l) => autoAt("jev_chunked", l))), 0),
      jevident: pct(rb.jev.repeat_identical_rate, 0),
    };
  }

  // ---------- language ----------
  function applyText() {
    const v = vars();
    document.documentElement.lang = lang;
    document.title = T().doc_title;
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = fill(T()[el.dataset.i18n], v); });
    $("#lang").textContent = T().lang_other;
  }
  $("#lang").addEventListener("click", () => {
    lang = lang === "es" ? "en" : "es";
    try { localStorage.setItem("lang", lang); } catch (e) {}
    renderAll();
  });

  // ---------- hero: typed log line, question, two needles ----------
  function renderHero() {
    const hero = data.hero;
    const pre = $("#hero-log");
    const qEl = $("#hero-q");
    const meters = $("#hero-meters");
    meters.innerHTML = "";
    const needles = {};
    for (const s of ["subq", "jev"]) {
      const m = h("div", { class: "meter" }, meters);
      h("span", { class: `c-${s}` }, m, s === "subq" ? "SubQ" : "Jev");
      const track = h("div", { class: "track" }, m);
      for (const x of [0, 0.25, 0.5, 0.75, 1]) h("i", { class: "tick" + (x === 0.5 ? " half" : ""), style: `left:${x * 100}%` }, track);
      const needle = h("i", { class: "needle", style: `background:${COLOR[s]}` }, track);
      const val = h("span", { class: "val" }, m, "0.00");
      needles[s] = { needle, val, p: hero.answers[s] };
    }
    const show = (instant) => {
      for (const n of Object.values(needles)) {
        n.needle.style.left = `calc(${n.p * 100}% - 1px)`;
        if (instant) n.val.textContent = n.p.toFixed(2);
        else tween(1400, (t) => { n.val.textContent = (n.p * t).toFixed(2); });
      }
    };
    const fullLog = hero.lines.map((l) => l.replace(/^2026-/, "")).join("\n");
    const mark = (text) => text.split("\n").map((l) => (l.includes("RETURNED") ? `<span class="hl">${l}</span>` : l)).join("\n");
    if (seen.has("hero") || reduced) {
      seen.add("hero");
      pre.innerHTML = mark(fullLog);
      qEl.textContent = hero.question;
      show(true);
      return;
    }
    seen.add("hero");
    let i = 0;
    const typeLog = () => {
      i = Math.min(fullLog.length, i + 3);
      pre.innerHTML = fullLog.slice(0, i) + '<span class="caret">&nbsp;</span>';
      if (i < fullLog.length) setTimeout(typeLog, 12);
      else { pre.innerHTML = mark(fullLog); typeQ(0); }
    };
    const typeQ = (j) => {
      qEl.textContent = hero.question.slice(0, j);
      if (j < hero.question.length) setTimeout(() => typeQ(j + 1), 28);
      else setTimeout(() => show(false), 250);
    };
    setTimeout(typeLog, 300);
  }

  // ---------- receipt ----------
  function renderReceipt() {
    const ol = $("#receipt-lines");
    ol.innerHTML = "";
    const rb = data.robustness;
    const l8s = lat("subq", 8000).p50, l8j = lat("jev", 8000).p50;
    const lines = [
      [T().r_short, data.head_to_head.subq.overall.acc, data.head_to_head.jev.overall.acc, (x) => P(x)],
      [T().r_long, row("subq", 360000).acc, row("jev_chunked", 360000).acc, (x) => P(x), T().r_chunked],
      [T().r_calib, data.calibration.shared.subq.ece, data.calibration.shared.jev.ece, (x) => num(x, 3)],
      [T().r_repeat, rb.subq.repeat_identical_rate, rb.jev.repeat_identical_rate, (x) => P(x, 0)],
      [T().r_latency, l8s, l8j, (x) => num(x, 2) + " s"],
    ];
    const els = lines.map(([name, a, b, f, note]) => {
      const li = h("li", {}, ol);
      h("span", { class: "name" }, li, name);
      const va = h("span", { class: "v c-subq" }, li);
      const vb = h("span", { class: "v c-jev" }, li);
      return { li, va, vb, a, b, f, note };
    });
    const set = (e, t) => {
      e.va.textContent = e.f(e.a * t);
      e.vb.textContent = e.f(e.b * t);
      if (e.note) h("small", {}, e.vb, e.note);
    };
    onView(ol, "receipt", (instant) => {
      els.forEach((e, k) => {
        if (instant) { e.li.classList.add("in"); set(e, 1); return; }
        setTimeout(() => {
          e.li.classList.add("in");
          tween(800, (t) => set(e, t));
        }, Math.max(0, 2600 - performance.now()) + k * 180);
      });
    }, 0.1);
  }

  // ---------- tape: log sizes to scale ----------
  function renderTape() {
    const box = $("#tape-rows");
    box.innerHTML = "";
    const max = LENS[LENS.length - 1];
    const rows = LENS.map((l) => {
      const r = h("div", { class: "tape-row" }, box);
      h("span", { class: "len" }, r, K(l));
      const wrap = h("div", { class: "strip-wrap" }, r);
      const strip = h("div", { class: "strip" }, wrap);
      h("div", { class: "window", style: `width:${(Math.min(l, 32768) / max) * 100}%` }, wrap);
      for (let c = 29000; c < l; c += 29000) h("div", { class: "cut", style: `left:${(c / max) * 100}%` }, wrap);
      return { strip, l };
    });
    onView(box, "tape", (instant) => {
      $("#tape").classList.add("in");
      rows.forEach(({ strip, l }, k) => {
        const go = () => (strip.style.width = `${(l / max) * 100}%`);
        if (instant) { strip.style.transition = "none"; go(); } else setTimeout(go, k * 90);
      });
    });
  }

  // ---------- accuracy by length chart ----------
  let selected = 360000;
  function renderAccChart() {
    const fig = $("#acc-chart");
    fig.innerHTML = "";
    const W = Math.max(300, fig.clientWidth);
    const H = W < 600 ? 300 : 380;
    const m = { l: 40, r: W < 600 ? 42 : 56, t: 22, b: 34 };
    const lx = (l) => m.l + ((Math.log(l) - Math.log(LENS[0])) / (Math.log(LENS.at(-1)) - Math.log(LENS[0]))) * (W - m.l - m.r);
    const y = (a) => m.t + (1 - (a - 0.4) / 0.6) * (H - m.t - m.b);
    const svg = h("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": T().s1_title }, fig);

    const xw = lx(32768);
    h("rect", { class: "band", x: m.l, y: m.t, width: xw - m.l, height: H - m.t - m.b }, svg);
    h("text", { class: "lbl", x: m.l + 6, y: H - m.b - 8, style: "fill:var(--jev)" }, svg, T().s1_window + " · 32.7K");
    h("text", { class: "lbl", x: xw - 7, y: H - m.b - 8, "font-size": 14, style: "fill:var(--jev)" }, svg, "✂");

    const ax = h("g", { class: "axis" }, svg);
    for (const a of [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]) {
      h("line", { class: "gridline", x1: m.l, x2: W - m.r, y1: y(a), y2: y(a) }, ax);
      h("text", { x: m.l - 8, y: y(a) + 4, "text-anchor": "end" }, ax, P(a, 0));
    }
    const ticks = W < 520 ? [2000, 8000, 30000, 128000, 360000] : LENS;
    ticks.forEach((l) => h("text", { x: lx(l), y: H - m.b + 18, "text-anchor": "middle" }, ax, K(l)));

    const selRect = h("rect", { class: "col-sel", y: m.t, height: H - m.t - m.b, width: 0 }, svg);
    const clipId = "accclip";
    const clip = h("rect", { x: 0, y: 0, width: 0, height: H }, h("clipPath", { id: clipId }, h("defs", {}, svg)));
    const plot = h("g", { "clip-path": `url(#${clipId})` }, svg);

    const pts = (s, lens) => lens.map((l) => row(s, l)).filter(Boolean);
    const lines = [
      ["subq", pts("subq", LENS), ""],
      ["jev", pts("jev", SHARED), ""],
      ["jev_chunked", [row("jev", 30000), ...pts("jev_chunked", LENS)], "6 5"],
    ];
    for (const [s, ps, dash] of lines) {
      for (const p of ps) {
        if (p.series === s) h("line", { class: "ci", x1: lx(p.length), x2: lx(p.length), y1: y(p.ci[0]), y2: y(p.ci[1]), stroke: COLOR[s] }, plot);
      }
      h("path", { class: "series", d: "M" + ps.map((p) => `${lx(p.length)},${y(p.acc)}`).join("L"), stroke: COLOR[s], "stroke-dasharray": dash || null }, plot);
      for (const p of ps) {
        if (p.series !== s) continue;
        h("circle", { cx: lx(p.length), cy: y(p.acc), r: 4.5, fill: s === "jev_chunked" ? "var(--paper)" : COLOR[s], stroke: COLOR[s], "stroke-width": 2 }, plot);
      }
    }
    const end = (s, dy) => {
      const p = row(s, 360000);
      h("text", { class: "lbl", x: lx(360000) + 9, y: y(p.acc) + 4 + dy, style: `fill:${COLOR[s]};font-weight:600` }, plot, P(p.acc));
    };
    end("subq", 0);
    end("jev_chunked", 0);

    // clickable columns
    LENS.forEach((l, k) => {
      const x0 = k === 0 ? m.l : (lx(LENS[k - 1]) + lx(l)) / 2;
      const x1 = k === LENS.length - 1 ? W - m.r + 30 : (lx(l) + lx(LENS[k + 1])) / 2;
      const hit = h("rect", { class: "col-hit", x: x0, y: m.t, width: x1 - x0, height: H - m.t - m.b }, svg);
      hit.addEventListener("click", () => { selected = l; renderReadout(); place(); });
    });
    const place = () => {
      const k = LENS.indexOf(selected);
      const x0 = k === 0 ? m.l : (lx(LENS[k - 1]) + lx(selected)) / 2;
      const x1 = k === LENS.length - 1 ? W - m.r : (lx(selected) + lx(LENS[k + 1])) / 2;
      selRect.setAttribute("x", x0);
      selRect.setAttribute("width", x1 - x0);
    };
    place();
    renderAccChart.place = place;

    onView(fig, "acc", (instant) => {
      if (instant) { clip.setAttribute("width", W); return; }
      tween(1800, (t) => clip.setAttribute("width", W * t));
    });

    const leg = $("#acc-legend");
    leg.innerHTML = "";
    const sw = (stroke, dash, label, ci) => {
      const s = h("span", {}, leg);
      const g = h("svg", { viewBox: "0 0 22 10" }, s);
      if (ci) h("line", { x1: 11, x2: 11, y1: 0, y2: 10, stroke: "var(--ink-3)", "stroke-width": 1.5 }, g);
      else h("line", { x1: 0, x2: 22, y1: 5, y2: 5, stroke, "stroke-width": 2.5, "stroke-dasharray": dash || null }, g);
      s.append(label);
    };
    sw(COLOR.subq, "", T().leg_subq);
    sw(COLOR.jev, "", T().leg_jev);
    sw(COLOR.jev, "4 3", T().leg_jevc);
    sw("", "", T().leg_ci, true);
  }

  // ---------- readout under the chart ----------
  function renderReadout() {
    const sizes = $("#sizes");
    sizes.innerHTML = "";
    LENS.forEach((l) => {
      const b = h("button", { type: "button", "aria-pressed": String(l === selected) }, sizes, K(l));
      b.addEventListener("click", () => { selected = l; renderReadout(); renderAccChart.place && renderAccChart.place(); });
    });
    const body = $("#readout-body");
    body.innerHTML = "";
    const grid = h("div", { class: "readout-grid" }, body);
    const js = longSeries(selected);
    h("div", { class: "h" }, grid, fill(T().readout, { len: K(selected) }));
    h("div", { class: "h c-subq" }, grid, "SubQ");
    h("div", { class: "h c-jev" }, grid, js === "jev" ? "Jev" : T().leg_jevc);
    const fams = ["L1", "L2", "X1", "X2", "A1", "A2"];
    const rs = row("subq", selected), rj = row(js, selected);
    const cell = (s, block) => {
      const d = h("div", { class: "bar-cell" }, grid);
      const b = h("i", { class: "b", style: `width:0;background:${COLOR[s]}` }, d);
      h("span", {}, d, P(block.acc, 0));
      requestAnimationFrame(() => requestAnimationFrame(() => (b.style.width = `${block.acc * 70}px`)));
    };
    for (const f of fams) {
      h("div", {}, grid, T()["fam_" + f]);
      cell("subq", rs.families[f]);
      cell(js, rj.families[f]);
    }
    h("div", { style: "font-weight:600" }, grid, "Total");
    cell("subq", rs);
    cell(js, rj);
  }

  // ---------- heat grids ----------
  function renderGrids() {
    const box = $("#grids");
    box.innerHTML = "";
    const fams = ["L1", "L2", "X1", "X2", "A1", "A2"];
    for (const model of ["subq", "jev"]) {
      const wrap = h("div", {}, box);
      const title = h("p", { class: "grid-title" }, wrap);
      h("span", { class: `c-${model}` }, title, model === "subq" ? "SubQ Snap" : "Jev");
      if (model === "jev") h("span", { class: "muted small", style: "font-weight:400" }, title, `≥64K: ${T().r_chunked}`);
      const g = h("div", { class: "heat" }, wrap);
      h("div", {}, g);
      LENS.forEach((l) => h("div", { class: "colh" }, g, K(l)));
      fams.forEach((f, ri) => {
        h("div", { class: "rowh" }, g, T()["fam_" + f]);
        LENS.forEach((l, ci) => {
          const s = model === "jev" ? longSeries(l) : "subq";
          const r = row(s, l);
          const a = r.families[f].acc;
          const p = Math.max(0, Math.min(100, ((a - 0.3) / 0.7) * 100));
          const c = h("div", {
            class: "cell" + (s === "jev_chunked" ? " chunked" : ""),
            style: `background-color:color-mix(in srgb, ${COLOR[s]} ${p}%, var(--sheet));color:${p > 55 ? "var(--sheet)" : "var(--ink)"};transition-delay:${ci * 70 + ri * 25}ms`,
            title: `${T()["fam_" + f]} · ${K(l)} · ${P(a)}`,
          }, g, pct(a, 0));
        });
      });
    }
    onView(box, "grids", () => $("#s2").classList.add("in"), 0.2);

    const dep = $("#depth");
    const dv = (s) => [0.1, 0.5, 0.9].map((d) => pct(data.depth.find((x) => x.series === s && x.depth === d).acc)).join(" · ");
    dep.innerHTML = "";
    dep.append(T().s2_depth + " ");
    const parts = [["SubQ", "subq"], ["Jev", "jev"], [T().leg_jevc, "jev_chunked"]];
    parts.forEach(([name, s], k) => {
      h("span", { class: `c-${s === "subq" ? "subq" : "jev"}` }, dep, name + " ");
      h("b", {}, dep, dv(s));
      dep.append(k < parts.length - 1 ? "; " : ".");
    });
  }

  // ---------- calibration ----------
  let calScope = "shared";
  function renderCalib() {
    const scope = $("#cal-scope");
    scope.innerHTML = "";
    for (const [k, label] of [["shared", T().cal_short], ["long", T().cal_long]]) {
      const b = h("button", { type: "button", "aria-pressed": String(k === calScope) }, scope, label);
      b.addEventListener("click", () => { calScope = k; renderCalib(); });
    }
    const box = $("#calib");
    box.innerHTML = "";
    const set = data.calibration[calScope];
    const animate = [];
    for (const [s, c] of Object.entries(set)) {
      const wrap = h("div", {}, box);
      const t = h("h4", {}, wrap);
      h("b", { class: `c-${s === "subq" ? "subq" : "jev"}` }, t, s === "subq" ? "SubQ Snap" : s === "jev" ? "Jev" : T().leg_jevc);
      h("span", {}, t, `${T().calib_err} ${num(c.ece, 3)}`);
      const W = Math.max(260, wrap.clientWidth || 400);
      const H = Math.min(W, 340);
      const m = { l: 40, r: 18, t: 22, b: 34 };
      const x = (v) => m.l + v * (W - m.l - m.r);
      const y = (v) => m.t + (1 - v) * (H - m.t - m.b);
      const svg = h("svg", { viewBox: `0 0 ${W} ${H}` }, wrap);
      const ax = h("g", { class: "axis" }, svg);
      for (const v of [0, 0.25, 0.5, 0.75, 1]) {
        h("line", { class: "gridline", x1: x(0), x2: x(1), y1: y(v), y2: y(v) }, ax);
        h("text", { x: m.l - 6, y: y(v) + 4, "text-anchor": "end" }, ax, P(v, 0));
        h("text", { x: x(v), y: H - m.b + 16, "text-anchor": "middle" }, ax, P(v, 0));
      }
      h("text", { class: "lbl", x: x(0.5), y: H - 2, "text-anchor": "middle" }, svg, T().axis_conf);
      h("text", { class: "lbl", x: 12, y: y(0.5), transform: `rotate(-90 12 ${y(0.5)})`, "text-anchor": "middle" }, svg, T().axis_right);
      h("line", { x1: x(0), y1: y(0), x2: x(1), y2: y(1), stroke: "var(--ink-3)", "stroke-dasharray": "4 4" }, svg);
      const col = COLOR[s];
      for (const b of c.bins) {
        const r = 3 + Math.sqrt(b.n / c.n) * 15;
        const g = h("g", { class: "pt" }, svg);
        h("line", { x1: x(b.conf), x2: x(b.conf), y1: y(b.conf), y2: y(b.acc), stroke: col, "stroke-width": 1.5, opacity: 0.5 }, g);
        h("circle", { cx: x(b.conf), cy: y(b.acc), r, fill: col, "fill-opacity": b.n < 5 ? 0.25 : 0.75, stroke: col },
          g).appendChild(h("title", {}, null, `${P(b.conf, 0)} → ${P(b.acc, 0)} (n=${b.n})`));
        animate.push({ g, dy: -y(b.acc) + m.t - 20 });
      }
    }
    onView(box, "calib", (instant) => {
      animate.forEach(({ g, dy }, k) => {
        if (instant) return;
        g.style.transition = "none";
        g.style.transform = `translateY(${dy}px)`;
        g.style.opacity = 0;
        requestAnimationFrame(() => requestAnimationFrame(() => {
          g.style.transition = "";
          g.style.transitionDelay = `${k * 60}ms`;
          g.style.transform = "translateY(0)";
          g.style.opacity = 1;
        }));
      });
    });
  }

  // ---------- automation at <=5% error ----------
  function renderAuto() {
    const box = $("#auto");
    box.innerHTML = "";
    const grid = h("div", { class: "readout-grid auto-grid" }, box);
    h("div", { class: "h" }, grid, "");
    h("div", { class: "h c-subq" }, grid, "SubQ");
    h("div", { class: "h c-jev" }, grid, "Jev");
    const bars = [];
    for (const l of LENS) {
      h("div", { class: "mono" }, grid, K(l) + (l > 30000 ? ` · Jev ${T().r_chunked}` : ""));
      for (const s of ["subq", longSeries(l)]) {
        const r = data.automation.by_length.find((x) => x.series === s && x.length === l);
        const d = h("div", { class: "bar-cell" }, grid);
        const b = h("i", { class: "b", style: `width:0;background:${COLOR[s]}` }, d);
        h("span", {}, d, P(r.coverage, 0));
        h("span", { class: "na" }, d, r.error === null ? T().auto_none : `${T().auto_err} ${P(r.error, 1)}`);
        bars.push([b, r.coverage]);
      }
    }
    onView(box, "auto", (instant) => bars.forEach(([b, c], k) => {
      if (instant) { b.style.transition = "none"; b.style.width = `${c * 60}px`; }
      else setTimeout(() => (b.style.width = `${c * 60}px`), k * 40);
    }));
  }

  // ---------- robustness ----------
  const loops = [];
  function renderRobust() {
    loops.forEach(clearInterval);
    loops.length = 0;
    const box = $("#robust");
    box.innerHTML = "";
    const rb = data.robustness;
    const of = (rate, n) => `${Math.round(rate * n)} ${T().rb_of} ${n}`;
    const rows = [
      ["shuffle", (s) => [of(rb[s].option_shuffle_flip_rate, rb[s].option_shuffle_n), T().rb_shuffle_m, ""]],
      ["rephrase", (s) => [of(rb[s].paraphrase_flip_rate, rb[s].paraphrase_n), T().rb_rephrase_m, `${T().rb_spread} ±${num(rb[s].paraphrase_mean_spread, 3)}`]],
      ["negate", (s) => [of(rb[s].negation_contradiction_rate, rb[s].negation_n), T().rb_negate_m, `${T().rb_gap}: ${num(rb[s].negation_mean_gap, 3)}`]],
      ["repeat", (s) => [P(rb[s].repeat_identical_rate, 0), T().rb_repeat_m, `${T().rb_same} ${P(rb[s].repeat_same_answer_rate)}`]],
    ];
    for (const [key, res] of rows) {
      const r = h("div", { class: "rb" }, box);
      const left = h("div", { class: "left" }, r);
      h("div", { class: "what" }, left, T()["rb_" + key]);
      const demo = h("div", { class: "demo" }, left);
      for (const s of ["subq", "jev"]) {
        const [big, sub, sub2] = res(s);
        const c = h("div", { class: "res" }, r);
        h("div", { class: `who c-${s}` }, c, s === "subq" ? "SubQ" : "Jev");
        h("div", { class: "big" }, c, big);
        h("div", { class: "sub" }, c, sub);
        if (sub2) h("div", { class: "sub" }, c, sub2);
      }
      demos[key](demo);
    }
  }
  const demos = {
    shuffle(el) {
      h("div", { style: "margin-bottom:4px" }, el, T().rb_q_shuffle);
      const opts = h("div", { class: "opts" }, el);
      const names = ["Bilbao", "Gdansk", "Leeds", "Lyon", "Porto"];
      const items = names.map((n) => h("span", { class: "opt" }, opts, n));
      if (reduced) return;
      loops.push(setInterval(() => {
        const first = items.map((i) => i.getBoundingClientRect().left);
        const order = items.slice().sort(() => Math.random() - 0.5);
        order.forEach((i) => opts.appendChild(i));
        items.forEach((i, k) => {
          const dx = first[k] - i.getBoundingClientRect().left;
          i.style.transition = "none";
          i.style.transform = `translateX(${dx}px)`;
          requestAnimationFrame(() => requestAnimationFrame(() => { i.style.transition = ""; i.style.transform = ""; }));
        });
      }, 1800));
    },
    rephrase(el) { cycle(el, T().rb_q_rephrase); },
    negate(el) { cycle(el, T().rb_q_negate, true); },
    repeat(el) {
      const line = h("div", {}, el, "POST /v1/systemone");
      const n = h("span", { style: "margin-left:8px" }, line, "×1");
      let k = 1;
      if (!reduced) loops.push(setInterval(() => { k = (k % 3) + 1; n.textContent = "×" + k; }, 900));
    },
  };
  function cycle(el, texts, markNot) {
    const t = h("div", {}, el);
    let k = 0;
    const show = () => {
      const s = texts[k % texts.length];
      t.innerHTML = markNot ? s.replace("NOT", '<b class="c-subq">NOT</b>') : s;
      k++;
    };
    show();
    if (!reduced) loops.push(setInterval(show, 2000));
  }

  // ---------- race ----------
  let raceLen = 8000;
  let raceFrame = 0;
  function renderRace(autoplay) {
    const sizes = $("#race-sizes");
    sizes.innerHTML = "";
    for (const l of [8000, 30000, 128000, 360000]) {
      const b = h("button", { type: "button", "aria-pressed": String(l === raceLen) }, sizes, K(l));
      b.addEventListener("click", () => { raceLen = l; renderRace(true); });
    }
    const box = $("#race");
    box.innerHTML = "";
    const js = longSeries(raceLen);
    const lanes = ["subq", js].map((s) => {
      const L = lat(s, raceLen);
      const lane = h("div", { class: "lane" }, box);
      h("span", { class: `c-${s === "subq" ? "subq" : "jev"}` }, lane, s === "subq" ? "SubQ" : "Jev");
      const tr = h("div", { class: "track2" }, lane);
      const chunks = s === "jev_chunked" ? Math.ceil(raceLen / 29000) : 1;
      for (let c = 1; c < chunks; c++) h("i", { class: "seg", style: `left:${(c / chunks) * 100}%` }, tr);
      const trail = h("i", { class: "trail", style: `background:${COLOR[s]}` }, tr);
      const runner = h("i", { class: "runner", style: `background:${COLOR[s]}` }, tr);
      const time = h("span", { class: "time" }, lane, "0.00 s");
      if (chunks > 1) h("span", { class: "meta" }, lane, fill(T().s5_chunks, { n: chunks }));
      return { tr, runner, trail, time, dur: L.p50 };
    });
    const draw = (elapsed) => {
      for (const ln of lanes) {
        const t = Math.min(1, elapsed / ln.dur);
        const w = ln.tr.clientWidth - 14;
        ln.runner.style.transform = `translateX(${t * w}px)`;
        ln.trail.style.width = `${t * w}px`;
        ln.time.textContent = num(Math.min(elapsed, ln.dur), 2) + " s";
      }
    };
    cancelAnimationFrame(raceFrame);
    const run = () => {
      const t0 = performance.now();
      const maxDur = Math.max(...lanes.map((l) => l.dur));
      const frame = (now) => {
        const e = (now - t0) / 1000;
        draw(e);
        if (e < maxDur) raceFrame = requestAnimationFrame(frame);
      };
      raceFrame = requestAnimationFrame(frame);
    };
    if (autoplay && !reduced) run();
    else onView(box, "race", (instant) => (instant ? draw(99) : run()), 0.6);

    const cost = $("#cost");
    cost.innerHTML = "";
    const head = h("div", { class: "row h" }, cost);
    h("span", {}, head, T().s5_cost);
    h("span", { class: "c-subq" }, head, "SubQ");
    h("span", { class: "c-jev" }, head, "Jev");
    for (const l of [8000, 30000, 128000, 360000]) {
      const r = h("div", { class: "row" }, cost);
      h("span", {}, r, K(l) + (l > 30000 ? ` (Jev ${T().r_chunked})` : ""));
      h("span", {}, r, "$" + num(lat("subq", l).usd_per_1k_decisions, 3));
      h("span", {}, r, "$" + num(lat(longSeries(l), l).usd_per_1k_decisions, 3));
    }
  }

  // ---------- takeaways ----------
  function renderTakeaways() {
    const box = $("#takeaways");
    box.innerHTML = "";
    const v = vars();
    for (const s of ["subq", "jev"]) {
      const col = h("div", {}, box);
      h("h3", { class: `c-${s}` }, col, s === "subq" ? "SubQ Snap" : "Jev");
      for (const [kind, mark] of [["good", "+"], ["watch", "−"]]) {
        h("p", { class: "tk-h" }, col, T()["tk_" + kind]);
        const ul = h("ul", { class: "tk" }, col);
        for (const item of T()[`tk_${s}_${kind}`]) {
          const li = h("li", {}, ul);
          h("span", { class: "tk-mark", "aria-hidden": "true" }, li, mark);
          h("span", {}, li, fill(item, v));
        }
      }
    }
  }

  // ---------- render ----------
  function renderAll() {
    applyText();
    renderHero();
    renderReceipt();
    renderTape();
    renderAccChart();
    renderReadout();
    renderGrids();
    renderCalib();
    renderAuto();
    renderRobust();
    renderRace(false);
    renderTakeaways();
  }
  renderAll();

  let rt;
  let lastW = innerWidth;
  addEventListener("resize", () => {
    if (innerWidth === lastW) return;
    lastW = innerWidth;
    clearTimeout(rt);
    rt = setTimeout(() => { renderAccChart(); renderCalib(); }, 150);
  });
})();
