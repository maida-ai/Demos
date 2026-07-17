const el = (id) => document.getElementById(id);
const worker = el("worker");
const adversary = el("adversary");
const attemptsEl = el("attempts");
const landedEl = el("landed");
const runBtn = el("run");
const resetBtn = el("reset");
const gateToggle = el("gate");
const banner = el("round-banner");
const flash = el("flash");
const scenarioSel = el("scenario");
const modelSel = el("model");
const blurb = el("scenario-blurb");

let source = null;
let scenarioBlurbs = {};
let isLive = false;

function esc(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function scrollPane(pane) {
  pane.scrollTop = pane.scrollHeight;
}

function addMsg(pane, cls, who, html) {
  const div = document.createElement("div");
  div.className = `msg ${cls}`;
  div.innerHTML = `<div class="who">${who}</div>${html}`;
  pane.appendChild(div);
  scrollPane(pane);
  return div;
}

function bumpStat(node, value) {
  node.textContent = value;
  node.classList.remove("bump");
  void node.offsetWidth;
  node.classList.add("bump");
}

function setBanner(round) {
  const attack = round.n > 0;
  banner.className = `round-banner ${attack ? "attack" : ""}`;
  const label = attack ? `Round ${round.n}` : "Warmup";
  banner.innerHTML = `<b>${label}: ${esc(round.title)}</b> &nbsp; <span class="obj">${esc(round.objective)}</span>`;
}

function renderVerdict(v) {
  const div = document.createElement("div");
  div.className = "verdict";
  div.innerHTML = `
    <div class="v-head"><span>&#10008; ${esc(v.headline)}</span><span class="reason">${esc(v.reason_code)}</span></div>
    <div class="v-body">
      ${esc(v.detail)}
      <div class="path"><span class="lbl">baseline:</span> <span class="base">${esc(v.baseline_path)}</span></div>
      <div class="path"><span class="lbl">current:</span> <span class="cur">${esc(v.current)}</span></div>
    </div>
    <div class="foot">${esc(v.footer)}</div>`;
  worker.appendChild(div);
  scrollPane(worker);
}

function fireOwned() {
  flash.classList.remove("fire");
  void flash.offsetWidth;
  flash.classList.add("fire");
  document.body.classList.add("owned");
  const b = document.createElement("div");
  b.className = "owned-banner";
  b.textContent = "WORKER OWNED";
  document.body.appendChild(b);
  setTimeout(() => {
    document.body.classList.remove("owned");
    b.remove();
  }, 1800);
}

function handle(ev) {
  switch (ev.type) {
    case "meta":
      el("mode").textContent = ev.live ? "LIVE" : "CANNED";
      break;
    case "round":
      setBanner(ev);
      break;
    case "adversary_msg": {
      let who = "injection payload";
      let cls = "adversary";
      if (ev.refused) {
        who = "adversary model \u2014 refused to author";
        cls = "adversary refused";
      } else if (ev.note) {
        who = `injection payload \u2014 ${ev.note}`;
      }
      addMsg(adversary, cls, who, esc(ev.text));
      break;
    }
    case "worker_msg":
      addMsg(worker, "worker", "deskbot", esc(ev.text));
      break;
    case "tool_call": {
      const cls = ev.blocked ? "tool blocked" : ev.danger ? "tool danger" : "tool";
      const args = Object.keys(ev.args || {}).length ? ` <code>${esc(JSON.stringify(ev.args))}</code>` : "";
      let badge = "";
      if (ev.blocked) badge = `<span class="badge blocked">BLOCKED</span>`;
      else if (ev.danger) badge = `<span class="badge landed">DANGEROUS</span>`;
      addMsg(worker, cls, "tool call", `${badge}<code>${esc(ev.tool)}</code>${args}`);
      break;
    }
    case "tool_result":
      addMsg(worker, "result", `${esc(ev.tool)} &rarr;`, `<code>${esc(ev.result)}</code>`);
      break;
    case "gate_verdict":
      renderVerdict(ev);
      break;
    case "score":
      bumpStat(attemptsEl, ev.attempts);
      bumpStat(landedEl, ev.landed);
      break;
    case "attack_result": {
      const map = {
        landed: ["\u2718 Attack landed \u2014 worker complied", "res-landed"],
        blocked: ["\u2714 Blocked by the Maida gate", "res-blocked"],
        resisted: ["\u2714 Worker resisted the injection", "res-resisted"],
      };
      const [txt, cls] = map[ev.outcome] || ["", "system-line"];
      const line = document.createElement("div");
      line.className = `system-line ${cls}`;
      line.textContent = txt;
      worker.appendChild(line);
      scrollPane(worker);
      break;
    }
    case "owned":
      fireOwned();
      break;
    case "safe": {
      const line = document.createElement("div");
      line.className = "system-line safe";
      line.textContent = "\u2714 All attacks bounced. Behavior held to baseline.";
      worker.appendChild(line);
      scrollPane(worker);
      break;
    }
    case "error":
      addMsg(worker, "adversary", "error", esc(ev.detail));
      break;
    case "done":
      finish();
      break;
  }
}

function finish() {
  runBtn.disabled = false;
  gateToggle.disabled = false;
  scenarioSel.disabled = false;
  modelSel.disabled = !isLive;
  runBtn.textContent = "Run arena";
  if (source) { source.close(); source = null; }
}

function updateBlurb() {
  blurb.textContent = scenarioBlurbs[scenarioSel.value] || "";
}

function reset() {
  if (source) { source.close(); source = null; }
  worker.innerHTML = "";
  adversary.innerHTML = "";
  attemptsEl.textContent = "0";
  landedEl.textContent = "0";
  banner.classList.add("hidden");
  document.body.classList.remove("owned");
  finish();
}

function run() {
  reset();
  banner.classList.remove("hidden");
  banner.className = "round-banner";
  banner.textContent = "Starting...";
  runBtn.disabled = true;
  gateToggle.disabled = true;
  scenarioSel.disabled = true;
  modelSel.disabled = true;
  runBtn.textContent = "Running...";
  const gate = gateToggle.checked ? "on" : "off";
  const params = new URLSearchParams({
    gate,
    scenario: scenarioSel.value,
    model: modelSel.value,
  });
  source = new EventSource(`/run?${params.toString()}`);
  source.onmessage = (e) => handle(JSON.parse(e.data));
  source.onerror = () => finish();
}

runBtn.addEventListener("click", run);
resetBtn.addEventListener("click", reset);
scenarioSel.addEventListener("change", updateBlurb);

fetch("/api/config")
  .then((r) => r.json())
  .then((cfg) => {
    isLive = cfg.live;
    el("mode").textContent = cfg.live ? "LIVE" : "CANNED";
    scenarioSel.innerHTML = "";
    cfg.scenarios.forEach((s) => {
      scenarioBlurbs[s.id] = s.blurb;
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.name;
      scenarioSel.appendChild(opt);
    });
    modelSel.innerHTML = "";
    cfg.models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      if (m === cfg.default_model) opt.selected = true;
      modelSel.appendChild(opt);
    });
    if (!cfg.live) {
      modelSel.disabled = true;
      modelSel.title = "No OpenAI key detected - running canned mode";
    }
    updateBlurb();
  })
  .catch(() => {});
