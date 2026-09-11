const TOOL_CANDIDATES = [
  "read_file", "edit_file", "write_file", "glob_search", "grep_search", "list_dir",
  "bash", "spawn_agent", "task_create", "task_update", "task_list", "task_get",
  "skill", "ask_user_question", "subagent_result",
];
const DEFAULT_TOOLS = new Set([
  "read_file", "edit_file", "write_file", "glob_search", "grep_search", "list_dir",
  "bash", "spawn_agent", "task_create",
]);

const $ = (id) => document.getElementById(id);
const state = { catalog: null, current: null, loadedContent: "", sha256: "", composing: false };

/* ---------- feedback ---------- */
let toastTimer = null;
function toast(message, kind = "") {
  const el = $("toast");
  el.textContent = message;
  el.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = "toast"; }, 3200);
}

function setStatus(message, kind = "") {
  const el = $("editor-status");
  el.textContent = message;
  el.className = `statusbar__msg ${kind}`;
}

async function api(path, options) {
  const res = await fetch(path, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `${res.status} ${res.statusText}`);
  return body;
}

const fmt = (n) => (n ?? 0).toLocaleString("en-US");
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

/* ---------- library ---------- */
async function loadCatalog() {
  state.catalog = await api("/api/state");
  $("endpoint").textContent = state.catalog.promptRoot;
  $("endpoint").title = `content: ${state.catalog.promptRoot}\nworkbuddy: ${state.catalog.workbuddyRoot}`;
  $("foot-roots").textContent = `${state.catalog.promptRoot}  ·  ${state.catalog.workbuddyRoot}`;
  renderLibrary();
}

function renderLibrary() {
  const filter = $("filter").value.trim().toLowerCase();
  const match = (...fields) => !filter || fields.some((f) => f.toLowerCase().includes(filter));
  const root = $("library");
  root.replaceChildren();

  let shownGroups = 0;
  for (const group of state.catalog.groups) {
    const entries = group.entries.filter((e) => match(e.id, e.file, group.name));
    if (filter && entries.length === 0) continue;
    shownGroups += 1;
    const details = el("details", "group");
    details.open = Boolean(filter) || entries.length <= 6;
    const summary = el("summary");
    summary.append(el("span", null, group.name), el("span", "count", String(entries.length)));
    details.append(summary);
    const list = el("div", "entries");
    for (const entry of entries) list.append(entryButton(group.name, entry));
    details.append(list);
    root.append(details);
  }

  const wb = state.catalog.workbuddy;
  const sections = [
    ["WorkBuddy · main", wb.main],
    ["WorkBuddy · styles", wb.styles],
    ["WorkBuddy · contract", wb.contract],
    ...Object.entries(wb.modes).map(([mode, files]) => [`Mode · ${mode}`, files]),
  ];
  const label = el("div", "section-label", "WorkBuddy 资源");
  root.append(label);
  for (const [title, files] of sections) {
    const shown = files.filter((f) => match(f.path));
    if (filter && shown.length === 0) continue;
    shownGroups += 1;
    const details = el("details", "group");
    details.open = Boolean(filter) && shown.length > 0;
    const summary = el("summary");
    summary.append(el("span", null, title), el("span", "count", String(files.length)));
    details.append(summary);
    const list = el("div", "entries");
    for (const f of shown) {
      const btn = el("button", "entry");
      btn.type = "button";
      btn.append(el("span", null, f.path.split("/").pop()), el("span", "chars", fmt(f.chars)));
      btn.addEventListener("click", () => openWorkbuddy(f.path, btn));
      list.append(btn);
    }
    details.append(list);
    root.append(details);
  }

  if (shownGroups === 0) {
    const empty = el("div", "empty");
    empty.append(el("span", "empty__mark", "∅"), el("p", null, "没有匹配的提示词"), el("p", "empty__hint", `没有条目匹配 “${filter}”`));
    root.append(empty);
  }
}

function entryButton(group, entry) {
  const btn = el("button", "entry");
  btn.type = "button";
  btn.title = `${group}/${entry.file}`;
  btn.append(el("span", null, entry.id));
  if (entry.status === "reference-only") btn.append(el("span", "ref", "ref"));
  btn.append(el("span", "chars", fmt(entry.chars)));
  btn.addEventListener("click", () => openContent(group, entry.file, btn));
  return btn;
}

function markActive(btn) {
  document.querySelectorAll(".entry.active").forEach((n) => n.classList.remove("active"));
  if (btn) btn.classList.add("active");
}

const isDirty = () => Boolean(state.current) && $("editor").value !== state.loadedContent;
function confirmDiscard() {
  return !isDirty() || window.confirm("当前修改尚未保存，确定要放弃吗？");
}

/* ---------- editor ---------- */
async function openContent(group, file, btn) {
  if (!confirmDiscard()) return;
  const data = await api(`/api/content?group=${encodeURIComponent(group)}&file=${encodeURIComponent(file)}`);
  state.current = { kind: "content", group, file };
  applyEditor(`${group}/${file}`, data);
  markActive(btn);
}

async function openWorkbuddy(path, btn) {
  if (!confirmDiscard()) return;
  const data = await api(`/api/workbuddy?path=${encodeURIComponent(path)}`);
  state.current = { kind: "workbuddy", path };
  applyEditor(`workbuddy/${path}`, data);
  markActive(btn);
}

function applyEditor(label, data) {
  state.loadedContent = data.content;
  state.sha256 = data.sha256;
  const editor = $("editor");
  editor.value = data.content;
  editor.disabled = false;
  $("save").disabled = false;
  $("reload").disabled = false;
  $("editor-empty").classList.add("hide");
  $("editor-meta").className = "meta";
  $("editor-meta").replaceChildren(
    el("b", null, label),
    el("span", "pill", `${fmt(data.chars)} 字符`),
    el("span", "pill", `sha ${data.sha256.slice(0, 10)}`),
  );
  setStatus("已加载。修改后点击保存写回磁盘（自动生成备份）。");
  updateDirty();
  updateStats();
  editor.focus();
}

function updateDirty() {
  const dirty = isDirty();
  $("dirty").classList.toggle("hide", !dirty);
  $("save").disabled = !state.current;
}

function updateStats() {
  const value = $("editor").value;
  if (!state.current) { $("editor-stats").textContent = ""; return; }
  const lines = value ? value.split("\n").length : 0;
  const words = (value.match(/\S+/g) || []).length;
  $("editor-stats").textContent = `${fmt(value.length)} 字符 · ${fmt(lines)} 行 · ${fmt(words)} 词`;
}

async function saveCurrent() {
  if (!state.current || state.composing) return;
  const content = $("editor").value;
  const isContent = state.current.kind === "content";
  const endpoint = isContent ? "/api/content" : "/api/workbuddy";
  const payload = isContent
    ? { group: state.current.group, file: state.current.file, content, expectedSha256: state.sha256 }
    : { path: state.current.path, content, expectedSha256: state.sha256 };
  try {
    const result = await api(endpoint, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
    state.loadedContent = content;
    state.sha256 = result.sha256;
    updateDirty();
    if (result.changed) {
      setStatus(`已保存 · ${fmt(result.chars)} 字符 · 备份：${result.backupPath}`, "ok");
      toast("已写回提示词文件", "ok");
    } else {
      setStatus("内容没有变化，未写入。");
    }
    runCompose();
  } catch (error) {
    if (String(error.message).includes("changed on disk")) {
      setStatus("冲突：文件已被其他进程修改，未写入。请点“还原”重新加载。", "err");
      toast("磁盘文件已变更，未覆盖", "err");
    } else {
      setStatus(error.message, "err");
      toast(error.message, "err");
    }
  }
}

function reloadCurrent() {
  if (!state.current) return;
  const btn = document.querySelector(".entry.active");
  if (state.current.kind === "content") openContent(state.current.group, state.current.file, btn);
  else openWorkbuddy(state.current.path, btn);
}

/* ---------- compose ---------- */
function buildToolChips() {
  const box = $("tool-chips");
  for (const name of TOOL_CANDIDATES) {
    const btn = el("button", "chip-toggle", name);
    btn.type = "button";
    btn.setAttribute("aria-pressed", String(DEFAULT_TOOLS.has(name)));
    btn.addEventListener("click", () => {
      btn.setAttribute("aria-pressed", btn.getAttribute("aria-pressed") === "true" ? "false" : "true");
      runCompose();
    });
    box.append(btn);
  }
}

function selectedTools() {
  const pressed = [...document.querySelectorAll("#tool-chips .chip-toggle")]
    .filter((b) => b.getAttribute("aria-pressed") === "true")
    .map((b) => b.textContent);
  const extra = $("c-tools-extra").value.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean);
  return [...new Set([...pressed, ...extra])];
}

async function runCompose() {
  if (!state.catalog || state.composing) return;
  state.composing = true;
  $("compose-spinner").classList.remove("hide");
  $("run-compose").disabled = true;
  try {
    const result = await api("/api/compose", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        role: $("c-role").value.trim() || "coder",
        permissionMode: $("c-permission").value,
        interactionMode: $("c-interaction").value,
        memoryEnabled: $("c-memory").checked,
        tools: selectedTools(),
      }),
    });
    if (!result.ok) throw new Error(result.error);
    renderMetrics(result.metrics);
    renderCompose(result);
  } catch (error) {
    $("compose-out").replaceChildren(makeBlock("编排失败", "", error.message, { open: true }));
    toast(error.message, "err");
  } finally {
    state.composing = false;
    $("compose-spinner").classList.add("hide");
    $("run-compose").disabled = false;
  }
}

function metric(k, value, unit) {
  const box = el("div", "metric");
  box.append(el("div", "k", k), el("div", "v", value), el("div", "u", unit));
  return box;
}

function renderMetrics(m) {
  const total = m.totalChars || 1;
  const box = $("metrics");
  box.replaceChildren(
    metric("System prompt", fmt(m.systemPromptChars), `字符 ≈ ${fmt(m.systemPromptTokens)} tok`),
    metric("Dynamic reminder", fmt(m.dynamicContextChars), `字符 ≈ ${fmt(m.dynamicContextTokens)} tok`),
    metric("合计 / 轮", fmt(m.totalChars), `≈ ${fmt(m.totalTokens)} tokens`),
  );
  const split = el("div", "split");
  const sys = el("div", "split__sys"); sys.style.width = `${(m.systemPromptChars / total) * 100}%`;
  const dyn = el("div", "split__dyn"); dyn.style.width = `${(m.dynamicContextChars / total) * 100}%`;
  split.append(sys, dyn);
  const legend = el("div", "split-legend");
  legend.append(
    el("span", null, `▮ 静态 system ${Math.round((m.systemPromptChars / total) * 100)}%`),
    el("span", null, `▮ 动态 reminder ${Math.round((m.dynamicContextChars / total) * 100)}%`),
  );
  box.append(split, legend);
}

function makeBlock(title, tag, body, { open = false, copyable = true } = {}) {
  const block = el("div", "block");
  block.dataset.open = String(open);
  const bar = el("div", "block__bar");
  const head = el("button", "block__head");
  head.type = "button";
  head.setAttribute("aria-expanded", String(open));
  const titleWrap = el("span", "block__title");
  titleWrap.append(el("span", null, title));
  if (tag) titleWrap.append(el("span", "block__tag", tag));
  head.append(titleWrap);
  bar.append(head);
  if (copyable) {
    const tools = el("span", "block__tools");
    const copy = el("button", "copy", "复制");
    copy.type = "button";
    copy.addEventListener("click", () => navigator.clipboard.writeText(body).then(() => toast("已复制到剪贴板", "ok"), () => toast("复制失败", "err")));
    tools.append(copy);
    bar.append(tools);
  }
  const pre = el("pre", "block__body", body);
  pre.hidden = !open;
  head.addEventListener("click", () => {
    const next = block.dataset.open !== "true";
    block.dataset.open = String(next);
    head.setAttribute("aria-expanded", String(next));
    pre.hidden = !next;
    syncExpandLabel();
  });
  block.append(bar, pre);
  return block;
}

function renderCompose(r) {
  const m = r.metrics;
  const out = $("compose-out");
  out.replaceChildren();

  const entryBlock = el("div", "block");
  entryBlock.dataset.open = "false";
  const bar = el("div", "block__bar");
  const head = el("button", "block__head");
  head.type = "button";
  head.setAttribute("aria-expanded", "false");
  const tw = el("span", "block__title");
  tw.append(el("span", null, "运行时原子片段"), el("span", "block__tag", `${r.runtimeEntries.length} 条 · ${fmt(m.runtimeEntriesChars)} 字符`));
  head.append(tw);
  bar.append(head);
  const rows = el("div", "block__rows");
  rows.hidden = true;
  r.runtimeEntries.forEach((entry, i) => {
    const row = el("div", "entry-row");
    const preview = el("span", "preview", entry.split("\n").find((l) => l.trim()) || "(空)");
    row.append(el("span", "idx", `#${i + 1}`), preview, el("span", "chars", fmt(entry.length)));
    row.title = entry;
    rows.append(row);
  });
  head.addEventListener("click", () => {
    const next = entryBlock.dataset.open !== "true";
    entryBlock.dataset.open = String(next);
    head.setAttribute("aria-expanded", String(next));
    rows.hidden = !next;
    syncExpandLabel();
  });
  entryBlock.append(bar, rows);
  out.append(entryBlock);

  out.append(makeBlock("静态基座 · workbuddy base", `${fmt(m.workbuddyBaseChars)} 字符`, r.staticSections.workbuddyBase));
  out.append(makeBlock("角色行", `${fmt(r.staticSections.roleLine.length)} 字符`, r.staticSections.roleLine));
  out.append(makeBlock("完整 System Prompt（真实函数输出）", `${fmt(m.systemPromptChars)} 字符`, r.systemPrompt, { open: true }));
  out.append(makeBlock("动态上下文 · <system-reminder>", `${fmt(m.dynamicContextChars)} 字符`, r.dynamicContext));
  if (r.dynamicEntries.length) out.append(makeBlock("动态补充片段", `${r.dynamicEntries.length} 条`, r.dynamicEntries.join("\n\n---\n\n")));
  syncExpandLabel();
}

function setBlockOpen(block, open) {
  block.dataset.open = String(open);
  const head = block.querySelector(".block__head");
  if (head) head.setAttribute("aria-expanded", String(open));
  block.querySelectorAll(".block__body, .block__rows").forEach((node) => { node.hidden = !open; });
}

function syncExpandLabel() {
  const blocks = [...document.querySelectorAll("#compose-out .block")];
  const allOpen = blocks.length > 0 && blocks.every((b) => b.dataset.open === "true");
  $("expand-all").textContent = allOpen ? "收起全部" : "展开全部";
}

let composeTimer = null;
const scheduleCompose = () => { clearTimeout(composeTimer); composeTimer = setTimeout(runCompose, 220); };

/* ---------- wire-up ---------- */
$("filter").addEventListener("input", renderLibrary);
$("refresh").addEventListener("click", () => loadCatalog().then(() => { toast("目录已刷新", "ok"); runCompose(); }).catch((e) => toast(e.message, "err")));
$("run-compose").addEventListener("click", runCompose);
$("save").addEventListener("click", saveCurrent);
$("reload").addEventListener("click", reloadCurrent);
$("expand-all").addEventListener("click", (e) => {
  const blocks = [...document.querySelectorAll("#compose-out .block")];
  const target = !blocks.every((b) => b.dataset.open === "true");
  blocks.forEach((b) => setBlockOpen(b, target));
  e.currentTarget.textContent = target ? "收起全部" : "展开全部";
});
$("editor").addEventListener("input", () => { updateDirty(); updateStats(); });
for (const id of ["c-role", "c-tools-extra"]) $(id).addEventListener("input", scheduleCompose);
for (const id of ["c-permission", "c-interaction", "c-memory"]) $(id).addEventListener("change", runCompose);

document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName ?? "");
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveCurrent(); return; }
  if (e.key === "/" && !typing) { e.preventDefault(); $("filter").focus(); return; }
  if (e.key === "Escape") {
    if (document.activeElement === $("filter") && $("filter").value) { $("filter").value = ""; renderLibrary(); }
    else document.activeElement?.blur();
  }
});
window.addEventListener("beforeunload", (e) => { if (isDirty()) { e.preventDefault(); e.returnValue = ""; } });

/* ---------- init ---------- */
buildToolChips();
loadCatalog()
  .then(runCompose)
  .catch((error) => { $("endpoint").textContent = "连接失败"; toast(error.message, "err"); });
