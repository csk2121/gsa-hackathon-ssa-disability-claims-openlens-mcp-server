"""
Build the evaluation report from saved results.

    python -m eval.agent_eval.report

Writes:
  eval/results/agent/report.html   self-contained page: score chart across
                                   experiments, latency chart, tables
  docs/evaluation_results.md       generated from the engine benchmark and the
                                   agent experiments (do not edit by hand)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "eval" / "results" / "agent"
ENGINE_RESULTS = ROOT / "eval" / "results" / "eval_results.json"
REPORT_HTML = RESULTS_DIR / "report.html"
RESULTS_DOC = ROOT / "docs" / "evaluation_results.md"

EVALUATOR_ORDER = (
    "tool_selection", "rating_match", "report_fidelity", "grounded_numbers",
    "expectations", "correctness", "grounding",
)
EVALUATOR_LABELS = {
    "tool_selection": "Right tool",
    "rating_match": "Rating matches",
    "report_fidelity": "Report shown in full",
    "grounded_numbers": "No invented numbers",
    "expectations": "Case expectations",
    "correctness": "Correctness (LLM judge)",
    "grounding": "Grounding (LLM judge)",
}


def load_experiments() -> list[dict[str, Any]]:
    experiments = []
    for path in RESULTS_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "summary" in data and "cases" in data:
            experiments.append(data)
    return sorted(experiments, key=lambda e: e["started_at"])


def load_engine_results() -> list[dict[str, Any]]:
    if not ENGINE_RESULTS.is_file():
        return []
    data = json.loads(ENGINE_RESULTS.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


# ── HTML ──────────────────────────────────────────────────────────────────────

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OpenLens Agent Evaluation</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface-1: #fcfcfb; --text-primary: #0b0b0b; --text-secondary: #52514e;
  --text-muted: #898781; --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a;
  --good: #006300; --bad: #b3261e;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7;
    --text-muted: #898781; --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
    --good: #0ca30c; --bad: #f2867f;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface-1: #1a1a19; --text-primary: #f0efec; --text-secondary: #c3c2b7;
  --text-muted: #898781; --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
  --good: #0ca30c; --bad: #f2867f;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--text-primary);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1080px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 18px; margin: 36px 0 12px; }
.sub { color: var(--text-secondary); margin: 0 0 24px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
.tile, .card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.tile .label { color: var(--text-secondary); font-size: 13px; }
.tile .value { font-size: 30px; font-weight: 650; margin-top: 2px; }
.tile .note { color: var(--text-muted); font-size: 12px; }
.charts { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
@media (max-width: 760px) { .charts { grid-template-columns: 1fr; } }
.card h3 { font-size: 15px; margin: 0 0 8px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; }
.legend span::before { content: ""; display: inline-block; width: 14px; height: 2px; vertical-align: middle;
  margin-right: 6px; background: var(--key); }
.plot { position: relative; }
svg { display: block; width: 100%; height: auto; overflow: visible; }
.tip { position: absolute; pointer-events: none; background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; font-size: 13px; box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  white-space: nowrap; display: none; z-index: 2; }
.tip .t { color: var(--text-secondary); margin-bottom: 4px; }
.tip .row { display: flex; gap: 8px; align-items: center; }
.tip .row b { min-width: 40px; }
.tip .key { width: 12px; height: 2px; background: var(--key); }
.table-wrap { overflow-x: auto; background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--grid); vertical-align: top; }
th { color: var(--text-secondary); font-weight: 600; white-space: nowrap; }
td.num { font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
.pass { color: var(--good); font-weight: 600; }
.fail { color: var(--bad); font-weight: 600; }
.detail { color: var(--text-secondary); font-size: 13px; }
footer { color: var(--text-muted); font-size: 12px; margin-top: 32px; }
</style>
</head>
<body>
<main>
  <h1>OpenLens Agent Evaluation</h1>
  <p class="sub" id="sub"></p>
  <div class="tiles" id="tiles"></div>
  <h2>Experiments</h2>
  <div class="charts">
    <div class="card">
      <h3>Scores by experiment</h3>
      <div class="legend" id="score-legend"></div>
      <div class="plot" id="score-plot"></div>
    </div>
    <div class="card">
      <h3>Average latency per question (seconds)</h3>
      <div class="plot" id="latency-plot"></div>
    </div>
  </div>
  <h2>Evaluator scores</h2>
  <div class="table-wrap"><table id="eval-table"></table></div>
  <h2 id="cases-title">Cases in the latest experiment</h2>
  <div class="table-wrap"><table id="case-table"></table></div>
  <footer id="footer"></footer>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  const DATA = JSON.parse(document.getElementById("data").textContent);
  const exps = DATA.experiments;
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs, text) => {
    const n = tag === "svg" || DATA.svgTags.includes(tag) ? document.createElementNS(NS, tag) : document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const pct = v => v == null ? "–" : Math.round(v * 100) + "%";

  document.getElementById("sub").textContent = exps.length
    ? `Dataset ${exps[0].dataset} · ${exps.length} experiment${exps.length > 1 ? "s" : ""} · agent ${exps[exps.length - 1].agent_model} · judges ${exps[exps.length - 1].judge_model || "off"}`
    : "No experiments yet. Run: python -m eval.agent_eval.run --prompt v01";
  document.getElementById("footer").textContent = `Generated ${DATA.generated}. Cost covers the agent's own tokens, not the judges'. Claude Code runs use the Claude subscription; their cost is the API-equivalent figure Claude Code reports, not a bill.`;
  if (!exps.length) return;

  const last = exps[exps.length - 1], s = last.summary;
  const tiles = [
    ["Cases passed", pct(s.pass_rate), `${s.cases_passed} of ${s.cases} · ${last.name}`],
    ["Average latency", s.avg_latency_s + "s", last.backend === "claude-code" ? "per question, Claude Code's timing" : "per question, end to end"],
    ["Average tokens", (s.avg_tokens / 1000).toFixed(1) + "k", `${s.avg_tool_calls} tool calls per question`],
    [s.cost_is_billed === false ? "API-equivalent cost" : "Agent cost", "$" + s.agent_cost_usd.toFixed(2), s.cost_is_billed === false ? "whole run; not billed (Claude subscription)" : `whole run, ${last.agent_model}`],
  ];
  const tilesEl = document.getElementById("tiles");
  for (const [label, value, note] of tiles) {
    const t = el("div", {class: "tile"});
    t.append(el("div", {class: "label"}, label), el("div", {class: "value"}, value), el("div", {class: "note"}, note));
    tilesEl.append(t);
  }

  // Score chart: 3 series, one 0-1 axis.
  const SERIES = [
    {key: "pass_rate", label: "Cases passed (all checks)", color: "var(--series-1)", get: e => e.summary.pass_rate},
    {key: "correctness", label: "Correctness (LLM judge)", color: "var(--series-2)", get: e => (e.summary.evaluators.correctness || {}).score},
    {key: "grounding", label: "Grounding (LLM judge)", color: "var(--series-3)", get: e => (e.summary.evaluators.grounding || {}).score},
  ];
  const legend = document.getElementById("score-legend");
  for (const sr of SERIES) { const sp = el("span", {style: `--key:${sr.color}`}, sr.label); legend.append(sp); }

  function tooltip(plot) {
    const tip = el("div", {class: "tip"}); plot.append(tip);
    return {
      show(x, y, title, rows) {
        tip.replaceChildren(el("div", {class: "t"}, title));
        for (const [value, label, color] of rows) {
          const r = el("div", {class: "row"});
          if (color) r.append(el("span", {class: "key", style: `--key:${color}`}));
          r.append(el("b", {}, value), el("span", {}, label));
          tip.append(r);
        }
        tip.style.display = "block";
        const w = plot.clientWidth, tw = tip.offsetWidth;
        tip.style.left = Math.min(Math.max(x + 12, 0), w - tw) + "px";
        tip.style.top = Math.max(y - 10, 0) + "px";
      },
      hide() { tip.style.display = "none"; },
    };
  }

  function scoreChart() {
    const plot = document.getElementById("score-plot");
    plot.replaceChildren();
    const W = Math.max(plot.clientWidth, 280), H = 260, m = {l: 40, r: 16, t: 12, b: 34};
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const x = i => m.l + (exps.length === 1 ? iw / 2 : i * iw / (exps.length - 1));
    const y = v => m.t + ih - v * ih;
    const svg = el("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Scores by experiment, 0 to 100 percent"});
    for (const v of [0, 0.25, 0.5, 0.75, 1]) {
      svg.append(el("line", {x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), stroke: v === 0 ? "var(--axis)" : "var(--grid)", "stroke-width": 1}));
      svg.append(el("text", {x: m.l - 8, y: y(v) + 4, "text-anchor": "end", "font-size": 12, fill: "var(--text-muted)"}, pct(v)));
    }
    exps.forEach((e, i) => svg.append(el("text", {x: x(i), y: H - 12, "text-anchor": "middle", "font-size": 12, fill: "var(--text-muted)"}, e.name)));
    for (const sr of SERIES) {
      const pts = exps.map((e, i) => [x(i), sr.get(e)]).filter(p => p[1] != null);
      if (pts.length > 1) svg.append(el("polyline", {points: pts.map(p => `${p[0]},${y(p[1])}`).join(" "), fill: "none", stroke: sr.color, "stroke-width": 2, "stroke-linejoin": "round"}));
      for (const p of pts) svg.append(el("circle", {cx: p[0], cy: y(p[1]), r: 4.5, fill: sr.color, stroke: "var(--surface-1)", "stroke-width": 2}));
    }
    const cross = el("line", {y1: m.t, y2: m.t + ih, stroke: "var(--axis)", "stroke-width": 1, visibility: "hidden"});
    svg.append(cross);
    const hit = el("rect", {x: m.l, y: m.t, width: iw, height: ih, fill: "transparent", tabindex: 0});
    svg.append(hit);
    plot.append(svg);
    const tip = tooltip(plot);
    const at = clientX => {
      const r = svg.getBoundingClientRect(), px = (clientX - r.left) * W / r.width;
      let best = 0; exps.forEach((_, i) => { if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i; });
      return best;
    };
    const show = i => {
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
      const r = svg.getBoundingClientRect();
      tip.show(x(i) * r.width / W, 8, `${exps[i].name} (prompt ${exps[i].prompt_version})`,
        SERIES.map(sr => [pct(sr.get(exps[i])), sr.label, sr.color]));
    };
    hit.addEventListener("pointermove", ev => show(at(ev.clientX)));
    hit.addEventListener("focus", () => show(exps.length - 1));
    for (const evName of ["pointerleave", "blur"]) hit.addEventListener(evName, () => { tip.hide(); cross.setAttribute("visibility", "hidden"); });
  }

  function latencyChart() {
    const plot = document.getElementById("latency-plot");
    plot.replaceChildren();
    const W = Math.max(plot.clientWidth, 220), H = 260, m = {l: 36, r: 8, t: 12, b: 34};
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const max = Math.max(...exps.map(e => e.summary.avg_latency_s), 1);
    const step = max > 20 ? 10 : max > 8 ? 5 : 2, top = Math.ceil(max / step) * step;
    const y = v => m.t + ih - v / top * ih;
    const band = iw / exps.length, bw = Math.min(48, band * 0.6);
    const svg = el("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Average latency per question by experiment"});
    for (let v = 0; v <= top; v += step) {
      svg.append(el("line", {x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), stroke: v === 0 ? "var(--axis)" : "var(--grid)", "stroke-width": 1}));
      svg.append(el("text", {x: m.l - 8, y: y(v) + 4, "text-anchor": "end", "font-size": 12, fill: "var(--text-muted)"}, v + "s"));
    }
    plot.append(svg);
    const tip = tooltip(plot);
    exps.forEach((e, i) => {
      const cx = m.l + band * i + band / 2, v = e.summary.avg_latency_s, h = Math.max(y(0) - y(v), 1);
      const r = Math.min(4, bw / 2, h);
      const x0 = cx - bw / 2, y0 = y(v);
      svg.append(el("path", {d: `M${x0},${y(0)} V${y0 + r} Q${x0},${y0} ${x0 + r},${y0} H${x0 + bw - r} Q${x0 + bw},${y0} ${x0 + bw},${y0 + r} V${y(0)} Z`, fill: "var(--series-1)"}));
      svg.append(el("text", {x: cx, y: H - 12, "text-anchor": "middle", "font-size": 12, fill: "var(--text-muted)"}, e.name));
      const hit = el("rect", {x: m.l + band * i, y: m.t, width: band, height: ih, fill: "transparent", tabindex: 0});
      const show = () => { const rr = svg.getBoundingClientRect(); tip.show(cx * rr.width / W, 8, e.name,
        [[v + "s", "average latency"], [(e.summary.avg_tokens / 1000).toFixed(1) + "k", "average tokens"]]); };
      hit.addEventListener("pointermove", show); hit.addEventListener("focus", show);
      hit.addEventListener("pointerleave", () => tip.hide()); hit.addEventListener("blur", () => tip.hide());
      svg.append(hit);
    });
  }

  // Evaluator table: rows = evaluators, columns = experiments.
  const et = document.getElementById("eval-table");
  const head = el("tr"); head.append(el("th", {}, "Evaluator"));
  for (const e of exps) head.append(el("th", {class: "num"}, `${e.prompt_version} · ${e.name}`));
  et.append(head);
  const rowFor = (label, cells) => { const tr = el("tr"); tr.append(el("td", {}, label)); for (const c of cells) tr.append(el("td", {class: "num"}, c)); et.append(tr); };
  for (const key of DATA.evaluatorOrder) {
    if (!exps.some(e => e.summary.evaluators[key])) continue;
    rowFor(DATA.evaluatorLabels[key], exps.map(e => { const st = e.summary.evaluators[key]; return st ? `${pct(st.score)} (${st.passed}/${st.applicable})` : "–"; }));
  }
  rowFor("Cases passed (all checks)", exps.map(e => `${pct(e.summary.pass_rate)} (${e.summary.cases_passed}/${e.summary.cases})`));
  rowFor("Average latency", exps.map(e => e.summary.avg_latency_s + "s"));
  rowFor("Average tokens", exps.map(e => e.summary.avg_tokens.toLocaleString()));
  rowFor("Agent cost (* API-equivalent, not billed)", exps.map(e => "$" + e.summary.agent_cost_usd.toFixed(2) + (e.summary.cost_is_billed === false ? "*" : "")));

  // Case table for the latest experiment.
  document.getElementById("cases-title").textContent = `Cases in the latest experiment (${last.name})`;
  const ct = document.getElementById("case-table");
  const ch = el("tr"); for (const h of ["Case", "Result", "Tools called", "Latency", "Failed checks"]) ch.append(el("th", {}, h));
  ct.append(ch);
  for (const c of last.cases) {
    const tr = el("tr");
    const name = el("td"); name.append(el("div", {}, c.id), el("div", {class: "detail"}, c.capability));
    const failed = [...c.checks, ...c.judges].filter(r => r.passed === false);
    const fails = el("td", {class: "detail"});
    if (!failed.length) fails.textContent = "–";
    for (const r of failed) fails.append(el("div", {}, `${DATA.evaluatorLabels[r.name] || r.name}: ${r.detail}`));
    tr.append(name, el("td", {class: c.passed ? "pass" : "fail"}, c.passed ? "Pass" : "Fail"),
      el("td", {class: "detail"}, (c.run.tools_called || []).join(", ") || "none"),
      el("td", {class: "num"}, c.run.latency_s + "s"), fails);
    ct.append(tr);
  }

  const draw = () => { scoreChart(); latencyChart(); };
  draw();
  let t; window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(draw, 120); });
})();
</script>
</body>
</html>
"""


def build_html(experiments: list[dict[str, Any]]) -> str:
    slim = [
        {
            "name": e["name"], "dataset": e["dataset"], "prompt_version": e["prompt_version"],
            "agent_model": e["agent_model"], "judge_model": e["judge_model"],
            "backend": e.get("backend", "api"),
            "summary": e["summary"],
            "cases": [
                {
                    "id": c["id"], "capability": c["capability"], "passed": c["passed"],
                    "run": {"latency_s": c["run"]["latency_s"], "tools_called": c["run"]["tools_called"]},
                    "checks": c["checks"], "judges": c["judges"],
                }
                for c in e["cases"]
            ],
        }
        for e in experiments
    ]
    data = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "experiments": slim,
        "evaluatorOrder": list(EVALUATOR_ORDER),
        "evaluatorLabels": EVALUATOR_LABELS,
        "svgTags": ["line", "text", "polyline", "circle", "rect", "path", "g"],
    }
    # Keep "</script>" inside the JSON from closing the data block.
    payload = json.dumps(data).replace("</", "<\\/")
    return _PAGE.replace("__DATA__", payload)


# ── Markdown results doc ──────────────────────────────────────────────────────


def _pct(v: float | None) -> str:
    return "–" if v is None else f"{v:.0%}"


def _engine_result(r: dict[str, Any]) -> str:
    if not r["passed"]:
        return f"Fail: {r['details']}"
    return "Pass" if r.get("rating_exact") else "Pass (rating one level off)"


def build_doc(experiments: list[dict[str, Any]], engine: list[dict[str, Any]]) -> str:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [
        "# Evaluation Results — SSA Disability Claims OpenLens",
        "",
        f"_Generated by `python -m eval.agent_eval.report` on {today} from the saved results. "
        "Do not edit by hand._",
        "",
        "OpenLens is evaluated at two levels:",
        "",
        "1. **Engine benchmark** (`python eval/engine_benchmark.py`): the Answer Coverage engine "
        "on its own, against expected ratings. Free and deterministic.",
        "2. **Agent evaluation** (`python -m eval.agent_eval.run`): a Claude agent answers the "
        "`openlens-eval-0` test set through the real MCP server over stdio, scored by code checks "
        "and LLM judges. The interactive report is `eval/results/agent/report.html`.",
        "",
        "## Engine benchmark",
        "",
    ]
    if engine:
        exact = sum(1 for r in engine if r.get("rating_exact"))
        passed = sum(1 for r in engine if r.get("passed"))
        lines += [
            f"{passed} of {len(engine)} cases pass; {exact} of {len(engine)} match the expected rating exactly.",
            "",
            "| Question | Expected | Actual | Score | Result |",
            "|----------|----------|--------|-------|--------|",
        ]
        for r in engine:
            lines.append(
                f"| {r['question']} | {r['expected_rating']} | {r['actual_rating']} | "
                f"{r['actual_score']} | {_engine_result(r)} |"
            )
    else:
        lines.append("_Not run yet. Run `python eval/engine_benchmark.py`._")

    lines += ["", "## Agent evaluation", ""]
    if not experiments:
        lines.append("_No experiments yet. Run `python -m eval.agent_eval.run --prompt v01`._")
        return "\n".join(lines) + "\n"

    header = "| Evaluator | " + " | ".join(f"{e['prompt_version']} ({e['name']})" for e in experiments) + " |"
    lines += [
        f"Test set `{experiments[0]['dataset']}`: {experiments[-1]['summary']['cases']} questions. "
        f"Agent `{experiments[-1]['agent_model']}`, judges `{experiments[-1]['judge_model']}`, "
        f"backend `{experiments[-1].get('backend', 'api')}`"
        + (" (headless Claude Code on a Claude subscription; latency is Claude Code's own timing "
           "per question, excluding process and server start-up)." if experiments[-1].get("backend") == "claude-code" else ".")
        ,
        "",
        header,
        "|" + "---|" * (len(experiments) + 1),
    ]
    for key in EVALUATOR_ORDER:
        if not any(key in e["summary"]["evaluators"] for e in experiments):
            continue
        cells = []
        for e in experiments:
            st = e["summary"]["evaluators"].get(key)
            cells.append(f"{_pct(st['score'])} ({st['passed']}/{st['applicable']})" if st else "–")
        lines.append(f"| {EVALUATOR_LABELS[key]} | " + " | ".join(cells) + " |")
    rows = [
        ("**Cases passed (all checks)**", lambda s: f"**{_pct(s['pass_rate'])}** ({s['cases_passed']}/{s['cases']})"),
        ("Average latency per question", lambda s: f"{s['avg_latency_s']}s"),
        ("Average tokens per question", lambda s: f"{s['avg_tokens']:,}"),
        ("Agent cost for the run (* API-equivalent, not billed)",
         lambda s: f"${s['agent_cost_usd']:.2f}" + ("*" if s.get("cost_is_billed") is False else "")),
    ]
    for label, fmt in rows:
        lines.append(f"| {label} | " + " | ".join(fmt(e["summary"]) for e in experiments) + " |")

    last = experiments[-1]
    failures = [c for c in last["cases"] if not c["passed"]]
    lines += ["", f"### Failures in the latest experiment ({last['name']})", ""]
    if not failures:
        lines.append("None: every case passed every applicable check.")
    for c in failures:
        reasons = "; ".join(
            f"{EVALUATOR_LABELS.get(r['name'], r['name'])}: {r['detail']}"
            for r in c["checks"] + c["judges"] if r["passed"] is False
        )
        lines.append(f"- **{c['id']}**: {reasons}")
    return "\n".join(lines) + "\n"


def build_report() -> None:
    experiments = load_experiments()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_HTML.write_text(build_html(experiments), encoding="utf-8")
    RESULTS_DOC.write_text(build_doc(experiments, load_engine_results()), encoding="utf-8")
    print(f"Report: {REPORT_HTML.relative_to(ROOT)} | Doc: {RESULTS_DOC.relative_to(ROOT)}")


if __name__ == "__main__":
    build_report()
