"use strict";
const $ = (sel) => document.querySelector(sel);
const el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  for (const k of kids) n.append(k);
  return n;
};

// ── Tabs ──────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    $("#tab-" + t.dataset.tab).classList.add("active");
  };
});

// ── SSE-over-fetch: POST a job, stream {type,...} events ──────────────
async function streamPost(url, body, onEvent) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let msg = resp.statusText;
    try { msg = (await resp.json()).error || msg; } catch (e) {}
    onEvent({ type: "error", message: msg });
    return;
  }
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i); buf = buf.slice(i + 2);
      const line = block.split("\n").find((l) => l.startsWith("data: "));
      if (line) { try { onEvent(JSON.parse(line.slice(6))); } catch (e) {} }
    }
  }
}

function logTo(node, msg) { node.textContent += msg + "\n"; node.scrollTop = node.scrollHeight; }
function setBar(node, pct) { node.style.width = Math.max(0, Math.min(100, pct)) + "%"; }
function fitDot(fit) { return el("span", { className: "dot " + (fit || "unknown") }); }

// ── Models tab ────────────────────────────────────────────────────────
let ONLINE = [];

async function loadModels() {
  const data = await (await fetch("/api/models")).json();

  const hw = data.hardware;
  $("#hardware").textContent =
    `GPU: ${hw.gpu_name || "Ingen"} (${hw.vram_mb} MB VRAM, CUDA: ${hw.has_cuda ? "ja" : "nej"})  ·  ` +
    `RAM: ${hw.ram_mb} MB  ·  ${hw.cpu_cores} kärnor  ·  Ledig disk: ${hw.free_disk_mb} MB`;

  // Whisper
  const wl = $("#whisper-list"); wl.textContent = "";
  const modelSel = $("#model"); modelSel.textContent = "";
  let installedCount = 0;
  for (const m of data.whisper) {
    wl.append(modelRow({
      fit: m.fit, label: m.label + (m.recommended ? " ⭐" : ""),
      meta: `${m.download_mb} MB — ${m.reason}`,
      installed: m.installed, disabled: m.fit === "red",
      onDownload: () => download("/api/download/whisper", { id: m.id }),
    }));
    if (m.installed) { modelSel.append(el("option", { value: m.id, textContent: m.label })); installedCount++; }
  }
  if (!installedCount) modelSel.append(el("option", { value: "", textContent: "(inga modeller installerade — se Modeller-fliken)" }));

  // LLM (curated, with hardware fit)
  const ll = $("#llm-list"); ll.textContent = "";
  const ppSel = $("#pp-model"); ppSel.textContent = "";
  if (!data.ollama_running) {
    ll.append(el("div", { className: "muted", textContent: "Ollama körs inte — starta Ollama för LLM-modeller." }));
  }
  for (const m of data.llm) {
    ll.append(modelRow({
      fit: m.fit, label: m.label + (m.recommended ? " ⭐" : ""),
      meta: `${m.download_mb} MB — ${m.reason}`,
      installed: m.installed, disabled: m.fit === "red" || !data.ollama_running,
      onDownload: () => download("/api/download/llm", { name: m.name }),
    }));
    if (m.installed) ppSel.append(el("option", { value: m.name, textContent: m.label }));
  }

  // Online extras
  ONLINE = data.llm_online_extra || [];
  renderOnline("");
}

function renderOnline(filter) {
  const box = $("#online-list"); box.textContent = "";
  const items = ONLINE.filter((n) => n.toLowerCase().includes(filter.toLowerCase()));
  box.append(el("div", { className: "muted", textContent: `${items.length} av ${ONLINE.length} modeller` }));
  for (const name of items.slice(0, 200)) {
    box.append(modelRow({
      fit: "unknown", label: name, meta: "ladda ner via Ollama",
      installed: false, disabled: false,
      onDownload: () => download("/api/download/llm", { name }),
    }));
  }
}
$("#online-search").oninput = (e) => renderOnline(e.target.value);

function modelRow({ fit, label, meta, installed, disabled, onDownload }) {
  const btn = el("button", { textContent: installed ? "Installerad" : "Ladda ner", disabled: installed || disabled });
  btn.onclick = onDownload;
  return el("div", { className: "model-row" },
    fitDot(fit),
    el("span", { className: "label" }, el("span", { textContent: label + "  " }), el("span", { className: "meta", textContent: meta })),
    btn);
}

function download(url, body) {
  const bar = $("#download-bar"), log = $("#download-log");
  setBar(bar, 0); log.textContent = "";
  streamPost(url, body, (ev) => {
    if (ev.type === "progress") { setBar(bar, ev.pct); if (ev.msg) logTo(log, ev.msg); }
    else if (ev.type === "log") logTo(log, ev.msg);
    else if (ev.type === "error") logTo(log, "FEL: " + ev.message);
    else if (ev.type === "done") { setBar(bar, 100); logTo(log, "Klar."); loadModels(); }
  });
}

// ── Transcribe tab ────────────────────────────────────────────────────
$("#start").onclick = () => {
  const source = $("#source").value.trim();
  const model_id = $("#model").value;
  const language = $("#language").value;
  const formats = [...document.querySelectorAll(".fmt:checked")].map((c) => c.value);
  if (!source) { alert("Ange en filsökväg eller URL."); return; }
  if (!model_id) { alert("Ingen modell installerad — gå till Modeller-fliken."); return; }
  if (!formats.length) { alert("Välj minst ett format."); return; }

  const bar = $("#transcribe-bar"), log = $("#transcribe-log"), res = $("#transcribe-results");
  setBar(bar, 0); log.textContent = ""; res.textContent = "";
  $("#start").disabled = true;
  streamPost("/api/transcribe", { source, model_id, language, formats }, (ev) => {
    if (ev.type === "progress") setBar(bar, ev.pct);
    else if (ev.type === "log") logTo(log, ev.msg);
    else if (ev.type === "error") { logTo(log, "FEL: " + ev.message); $("#start").disabled = false; }
    else if (ev.type === "done") {
      setBar(bar, 100); $("#start").disabled = false;
      for (const f of (ev.result.files || [])) res.append(el("a", { textContent: f, href: "#" }));
    }
  });
};

// ── Post-process ──────────────────────────────────────────────────────
$("#pp-run").onclick = () => {
  const out = $("#pp-output");
  const transcript = $("#transcribe-log").textContent;  // placeholder source; real wiring later
  const model = $("#pp-model").value;
  if (!model) { alert("Ingen LLM-modell installerad."); return; }
  out.textContent = "";
  streamPost("/api/postprocess", { operation: $("#pp-op").value, transcript, model }, (ev) => {
    if (ev.type === "token") { out.textContent += ev.text; out.scrollTop = out.scrollHeight; }
    else if (ev.type === "error") logTo(out, "\nFEL: " + ev.message);
  });
};

loadModels();
