from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

SESSIONS = {
    "2419": "sess-93c868002c66",
    "2907": "sess-42d40a6ca00e",
    "3066": "sess-76719b07fdab",
    "3435": "sess-e4e716ee7a0e",
}


# 将 ISO 时间转换成适合轨迹展示的短时间。
def _short_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%H:%M:%S")
    except ValueError:
        return value


# 将任意事件字段转换成可序列化且稳定的文本。
def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


# 从单个事件文件中读取并严格过滤目标 run 的事件。
def _load_events(event_file: Path, run_id: str) -> tuple[list[dict[str, Any]], int]:
    selected: list[dict[str, Any]] = []
    foreign = 0
    for line in event_file.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_run_id = event.get("run_id")
        if event_run_id == run_id:
            selected.append(event)
        elif event_run_id:
            foreign += 1
    return selected, foreign


# 将一个 run 的事件重建成按 LLM 步骤组织的操作轨迹。
def _build_task_trace(task: str, session_dir: Path) -> dict[str, Any]:
    event_files = sorted((session_dir / "runs").glob("*/events.jsonl"))
    if not event_files:
        raise FileNotFoundError(f"No events.jsonl under {session_dir}")
    event_file = event_files[0]
    run_id = event_file.parent.name
    events, foreign_count = _load_events(event_file, run_id)

    steps: list[dict[str, Any]] = []
    step_by_number: dict[int, dict[str, Any]] = {}
    tool_by_id: dict[str, dict[str, Any]] = {}
    current_step: dict[str, Any] | None = None
    run_events: list[dict[str, Any]] = []

    for event in events:
        event_type = str(event.get("type", ""))
        if event_type == "step.started":
            number = int(event.get("step", len(steps) + 1))
            current_step = {
                "number": number,
                "ts": event.get("ts", ""),
                "time": _short_time(event.get("ts")),
                "usage": None,
                "thinking": "",
                "tools": [],
                "events": [],
            }
            steps.append(current_step)
            step_by_number[number] = current_step
            continue

        explicit_step = event.get("step")
        if explicit_step is not None:
            current_step = step_by_number.get(int(explicit_step), current_step)

        if event_type == "llm.usage" and current_step is not None:
            current_step["usage"] = {
                "input": int(event.get("input_tokens", 0) or 0),
                "output": int(event.get("output_tokens", 0) or 0),
                "cache_read": int(event.get("cache_read_input_tokens", 0) or 0),
                "cache_create": int(event.get("cache_creation_input_tokens", 0) or 0),
                "context_pct": float(event.get("context_pct", 0) or 0),
                "model": event.get("model", ""),
            }
        elif event_type == "llm.thinking" and current_step is not None:
            current_step["thinking"] = _as_text(event.get("thinking"))
        elif event_type == "tool.call_started" and current_step is not None:
            tool = {
                "id": event.get("tool_use_id", ""),
                "name": event.get("tool_name", "unknown"),
                "ts": event.get("ts", ""),
                "time": _short_time(event.get("ts")),
                "params": _as_text(event.get("params")),
                "status": "running",
                "elapsed_ms": None,
                "output": "",
                "error": "",
            }
            current_step["tools"].append(tool)
            tool_by_id[str(tool["id"])] = tool
        elif event_type in {"tool.call_finished", "tool.call_failed"}:
            tool = tool_by_id.get(str(event.get("tool_use_id", "")))
            if tool is not None:
                if event_type.endswith("failed"):
                    tool["status"] = "failed"
                elif tool["status"] != "failed":
                    tool["status"] = "finished"
                tool["elapsed_ms"] = event.get("elapsed_ms")
                tool["output"] = _as_text(event.get("output"))
                tool["error"] = _as_text(
                    event.get("error") or event.get("message") or event.get("error_type")
                )
        elif event_type in {
            "test.result",
            "stuck.loop",
            "change.applied",
            "run.finished",
            "session.closed",
        }:
            item = {
                "type": event_type,
                "time": _short_time(event.get("ts")),
                "status": event.get("status", ""),
                "detail": _as_text(
                    event.get("summary")
                    or event.get("reason")
                    or event.get("message")
                    or event.get("paths")
                    or event
                ),
            }
            if current_step is not None and event_type not in {"session.closed"}:
                current_step["events"].append(item)
            else:
                run_events.append(item)

    usages = [step["usage"] for step in steps if step["usage"]]
    tools = [tool for step in steps for tool in step["tools"]]
    tool_counts = Counter(str(tool["name"]) for tool in tools)
    first_ts = events[0].get("ts") if events else None
    last_ts = events[-1].get("ts") if events else None
    duration_minutes = 0.0
    if first_ts and last_ts:
        duration_minutes = (
            datetime.fromisoformat(last_ts) - datetime.fromisoformat(first_ts)
        ).total_seconds() / 60

    return {
        "task": task,
        "session_id": session_dir.name,
        "run_id": run_id,
        "event_file": str(event_file),
        "foreign_events_excluded": foreign_count,
        "started": _short_time(first_ts),
        "ended": _short_time(last_ts),
        "duration_minutes": round(duration_minutes, 2),
        "step_count": len(steps),
        "tool_count": len(tools),
        "tool_failure_count": sum(tool["status"] == "failed" for tool in tools),
        "input_tokens": sum(usage["input"] for usage in usages),
        "output_tokens": sum(usage["output"] for usage in usages),
        "cache_read_tokens": sum(usage["cache_read"] for usage in usages),
        "tool_counts": dict(tool_counts.most_common()),
        "steps": steps,
        "run_events": run_events,
    }


# 返回自包含操作轨迹报告的 HTML 模板。
def _html_document(trace_data: list[dict[str, Any]]) -> str:
    payload = json.dumps(trace_data, ensure_ascii=False).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SWE-bench 四任务历史操作 Trace</title>
  <style>
    :root {{ --bg:#f1f2ef; --surface:#fbfcf9; --ink:#18211f; --muted:#68716e; --line:#d6dad5; --green:#176b55; --red:#a94335; --amber:#a96517; --blue:#315f84; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:"Noto Sans SC","Microsoft YaHei UI",sans-serif; font-size:14px; line-height:1.55; }}
    button,input,select {{ font:inherit; }}
    code,.mono,pre {{ font-family:"Cascadia Code",Consolas,monospace; }}
    .shell {{ width:min(1480px,calc(100% - 28px)); margin:auto; padding:26px 0 60px; }}
    header {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:28px; align-items:end; padding:22px 0; border-bottom:2px solid var(--ink); }}
    .eyebrow {{ margin:0 0 7px; color:var(--green); font:700 11px/1 "Cascadia Code",Consolas,monospace; }}
    h1 {{ margin:0 0 8px; font:600 clamp(32px,4vw,54px)/1.08 Georgia,"Noto Serif SC",serif; letter-spacing:0; }}
    header p {{ max-width:850px; margin:0; color:var(--muted); font-size:16px; }}
    .back {{ align-self:start; color:var(--green); text-decoration:none; border-bottom:1px solid currentColor; }}
    .summary {{ display:grid; grid-template-columns:repeat(4,1fr); gap:1px; margin:20px 0; border:1px solid var(--line); background:var(--line); }}
    .summary-item {{ padding:16px; background:var(--surface); }}
    .summary-item span {{ display:block; color:var(--muted); font-size:11px; }}
    .summary-item strong {{ display:block; margin:5px 0; font:600 25px/1 Georgia,serif; }}
    .toolbar {{ position:sticky; top:0; z-index:5; display:grid; grid-template-columns:150px 170px 150px minmax(220px,1fr) auto; gap:8px; padding:12px 0; background:rgb(241 242 239 / 95%); backdrop-filter:blur(12px); }}
    .control {{ min-width:0; height:40px; padding:0 11px; border:1px solid var(--line); background:var(--surface); color:var(--ink); border-radius:0; }}
    .button {{ border:0; padding:0 15px; background:var(--ink); color:white; cursor:pointer; }}
    .task-head {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:20px; align-items:center; margin-top:28px; padding:16px 0 12px; border-bottom:1px solid var(--ink); }}
    .task-head h2 {{ margin:0; font:600 28px/1.15 Georgia,"Noto Serif SC",serif; }}
    .task-meta {{ color:var(--muted); font-size:12px; text-align:right; }}
    .task-stats {{ display:flex; flex-wrap:wrap; gap:1px; margin:0 0 14px; background:var(--line); border:1px solid var(--line); }}
    .task-stat {{ flex:1 1 130px; padding:10px 12px; background:var(--surface); }}
    .task-stat span {{ display:block; color:var(--muted); font-size:10px; }}
    .task-stat strong {{ font-variant-numeric:tabular-nums; }}
    .trace-list {{ display:grid; gap:6px; }}
    .step-row {{ border-left:3px solid var(--line); background:var(--surface); }}
    .step-row.has-failure {{ border-left-color:var(--red); }}
    .step-row.has-change {{ border-left-color:var(--green); }}
    .step-summary {{ display:grid; grid-template-columns:74px 74px minmax(0,1fr) 110px 110px; gap:12px; align-items:center; min-height:52px; padding:8px 13px; cursor:pointer; list-style:none; }}
    .step-summary::-webkit-details-marker {{ display:none; }}
    .step-no {{ font-weight:700; }}
    .time {{ color:var(--muted); font-size:12px; }}
    .action-line {{ min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .tool-chip {{ display:inline-block; margin:2px 4px 2px 0; padding:2px 6px; background:#e5e9e5; color:#36413e; font:700 10px/1.4 "Cascadia Code",Consolas,monospace; }}
    .tool-chip.failed {{ background:#f1d9d4; color:var(--red); }}
    .tokens {{ color:var(--muted); font-size:11px; text-align:right; font-variant-numeric:tabular-nums; }}
    .cache {{ color:var(--green); }}
    .detail {{ padding:0 14px 14px 173px; border-top:1px solid var(--line); }}
    .detail-section {{ padding-top:13px; }}
    .detail-title {{ margin-bottom:6px; color:var(--muted); font:700 10px/1 "Cascadia Code",Consolas,monospace; text-transform:uppercase; }}
    .tool-detail {{ margin-top:9px; padding:12px; border:1px solid var(--line); background:#f5f6f3; }}
    .tool-detail.failed {{ border-color:#dfb2aa; }}
    .tool-title {{ display:flex; justify-content:space-between; gap:12px; font-weight:700; }}
    pre {{ max-height:420px; overflow:auto; margin:9px 0 0; padding:11px; background:#202725; color:#e7ede9; font-size:11px; line-height:1.55; white-space:pre-wrap; overflow-wrap:anywhere; }}
    .event {{ margin-top:8px; padding:10px 12px; border-left:3px solid var(--blue); background:#e5edf2; }}
    .event.change-applied {{ border-left-color:var(--green); background:#dfece7; }}
    .event.test-result {{ border-left-color:var(--amber); background:#f1e7d5; }}
    .event.stuck-loop,.event.run-finished {{ border-left-color:var(--red); background:#f2dfdb; }}
    .empty {{ padding:50px; color:var(--muted); text-align:center; }}
    mark {{ background:#f4d58f; color:inherit; }}
    footer {{ margin-top:34px; padding-top:18px; border-top:2px solid var(--ink); color:var(--muted); font-size:11px; }}
    @media(max-width:850px) {{ header{{grid-template-columns:1fr}} .summary{{grid-template-columns:1fr 1fr}} .toolbar{{position:static;grid-template-columns:1fr 1fr}} .toolbar input{{grid-column:1/-1}} .step-summary{{grid-template-columns:58px 60px minmax(0,1fr)}} .tokens{{display:none}} .detail{{padding-left:14px}} }}
    @media(max-width:520px) {{ .shell{{width:calc(100% - 16px)}} .summary{{grid-template-columns:1fr}} .toolbar{{grid-template-columns:1fr}} .toolbar input{{grid-column:auto}} .task-head{{grid-template-columns:1fr}} .task-meta{{text-align:left}} }}
    @media print {{ .toolbar,.back{{display:none}} body{{background:white;font-size:10px}} .shell{{width:100%;padding:0}} details{{break-inside:avoid}} pre{{max-height:none}} }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div><p class="eyebrow">FORENSIC TRACE / RUN_ID FILTERED</p><h1>四任务历史操作 Trace</h1><p>按精确 run_id 重建 2419、2907、3066、3435 的 LLM 步骤、工具参数与输出、测试事件、源码修改和结束状态。跨任务串入事件已排除。</p></div>
      <a class="back" href="swebench-agent-token-cache-analysis.html">返回诊断主报告</a>
    </header>
    <div id="summary" class="summary"></div>
    <div class="toolbar" aria-label="轨迹筛选">
      <select id="taskFilter" class="control" aria-label="选择任务"><option value="all">全部任务</option></select>
      <select id="toolFilter" class="control" aria-label="选择工具"><option value="all">全部工具</option></select>
      <select id="statusFilter" class="control" aria-label="选择状态"><option value="all">全部状态</option><option value="failed">含失败</option><option value="changed">含源码修改</option><option value="test">含测试</option><option value="no-tool">无工具步骤</option></select>
      <input id="search" class="control" type="search" placeholder="搜索思考、命令、路径、输出…" aria-label="搜索轨迹">
      <button id="expandAll" class="button" type="button">展开当前</button>
    </div>
    <main id="report"></main>
    <footer>数据来自本地 events.jsonl；未纳入 llm.token、permission.granted、model_selected 等高频传输事件。生成时间：2026-08-07。</footer>
  </div>
  <script id="traceData" type="application/json">{payload}</script>
  <script>
    const tasks = JSON.parse(document.getElementById('traceData').textContent);
    const fmt = new Intl.NumberFormat('zh-CN');
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    const slug = (value) => String(value).replaceAll('.', '-');
    const taskFilter = document.getElementById('taskFilter');
    const toolFilter = document.getElementById('toolFilter');
    const statusFilter = document.getElementById('statusFilter');
    const search = document.getElementById('search');
    const report = document.getElementById('report');
    const summary = document.getElementById('summary');
    const allTools = [...new Set(tasks.flatMap(task => Object.keys(task.tool_counts)))].sort();
    tasks.forEach(task => taskFilter.insertAdjacentHTML('beforeend', `<option value="${{task.task}}">${{task.task}}</option>`));
    allTools.forEach(tool => toolFilter.insertAdjacentHTML('beforeend', `<option value="${{esc(tool)}}">${{esc(tool)}}</option>`));

    const totals = {{
      steps: tasks.reduce((n,t)=>n+t.step_count,0),
      tools: tasks.reduce((n,t)=>n+t.tool_count,0),
      input: tasks.reduce((n,t)=>n+t.input_tokens,0),
      foreign: tasks.reduce((n,t)=>n+t.foreign_events_excluded,0),
    }};
    summary.innerHTML = `
      <div class="summary-item"><span>Agent 循环步骤</span><strong>${{fmt.format(totals.steps)}}</strong><small>含 2 个已开始但未产生 usage 的尾部步骤</small></div>
      <div class="summary-item"><span>工具调用</span><strong>${{fmt.format(totals.tools)}}</strong><small>含参数与结果</small></div>
      <div class="summary-item"><span>未缓存输入</span><strong>${{(totals.input/1e6).toFixed(2)}}M</strong><small>按 run_id 去重</small></div>
      <div class="summary-item"><span>排除串线事件</span><strong>${{fmt.format(totals.foreign)}}</strong><small>未进入本轨迹</small></div>`;

    function eventClass(type) {{ return slug(type); }}
    function stepText(step) {{
      return [step.thinking, ...step.tools.flatMap(t => [t.name,t.params,t.output,t.error]), ...step.events.flatMap(e => [e.type,e.detail])].join('\\n').toLowerCase();
    }}
    function matches(step) {{
      const tool = toolFilter.value;
      const state = statusFilter.value;
      const q = search.value.trim().toLowerCase();
      if (tool !== 'all' && !step.tools.some(t => t.name === tool)) return false;
      if (state === 'failed' && !step.tools.some(t => t.status === 'failed')) return false;
      if (state === 'changed' && !step.events.some(e => e.type === 'change.applied')) return false;
      if (state === 'test' && !step.events.some(e => e.type === 'test.result')) return false;
      if (state === 'no-tool' && step.tools.length) return false;
      return !q || stepText(step).includes(q);
    }}
    function renderTool(tool) {{
      const body = [tool.params && `<div class="detail-title">Parameters</div><pre>${{esc(tool.params)}}</pre>`, tool.output && `<div class="detail-title">Output</div><pre>${{esc(tool.output)}}</pre>`, tool.error && `<div class="detail-title">Error</div><pre>${{esc(tool.error)}}</pre>`].filter(Boolean).join('');
      return `<div class="tool-detail ${{tool.status === 'failed' ? 'failed' : ''}}"><div class="tool-title"><span>${{esc(tool.name)}}</span><span class="time">${{esc(tool.status)}} · ${{tool.elapsed_ms ?? '—'}} ms</span></div>${{body || '<div class="time">无附加输出</div>'}}</div>`;
    }}
    function renderStep(step) {{
      const usage = step.usage || {{input:0,output:0,cache_read:0,context_pct:0}};
      const failed = step.tools.some(t => t.status === 'failed');
      const changed = step.events.some(e => e.type === 'change.applied');
      const chips = step.tools.length ? step.tools.map(t => `<span class="tool-chip ${{t.status === 'failed'?'failed':''}}">${{esc(t.name)}}</span>`).join('') : '<span class="time">无工具，模型继续思考或收尾</span>';
      const thinking = step.thinking ? `<div class="detail-section"><div class="detail-title">Model thinking</div><pre>${{esc(step.thinking)}}</pre></div>` : '';
      const tools = step.tools.map(renderTool).join('');
      const events = step.events.map(e => `<div class="event ${{eventClass(e.type)}}"><strong>${{esc(e.type)}}</strong> <span class="time">${{esc(e.time)}} ${{esc(e.status)}}</span><pre>${{esc(e.detail)}}</pre></div>`).join('');
      return `<details class="step-row ${{failed?'has-failure':''}} ${{changed?'has-change':''}}"><summary class="step-summary"><span class="step-no">#${{step.number}}</span><span class="time">${{esc(step.time)}}</span><span class="action-line">${{chips}}</span><span class="tokens">in ${{fmt.format(usage.input)}}</span><span class="tokens cache">cache ${{fmt.format(usage.cache_read)}}</span></summary><div class="detail">${{thinking}}${{tools}}${{events}}</div></details>`;
    }}
    function render() {{
      const chosenTask = taskFilter.value;
      const blocks = tasks.filter(t => chosenTask === 'all' || t.task === chosenTask).map(task => {{
        const steps = task.steps.filter(matches);
        if (!steps.length) return '';
        const hit = task.input_tokens ? (100*task.cache_read_tokens/task.input_tokens).toFixed(2) : '0.00';
        return `<section data-task="${{task.task}}"><div class="task-head"><h2>sqlfluff__sqlfluff-${{task.task}}</h2><div class="task-meta mono">${{esc(task.session_id)}}<br>${{esc(task.run_id)}}</div></div><div class="task-stats"><div class="task-stat"><span>时间</span><strong>${{task.started}}–${{task.ended}}</strong></div><div class="task-stat"><span>持续</span><strong>${{task.duration_minutes}} min</strong></div><div class="task-stat"><span>步骤 / 当前显示</span><strong>${{task.step_count}} / ${{steps.length}}</strong></div><div class="task-stat"><span>工具 / 失败</span><strong>${{task.tool_count}} / ${{task.tool_failure_count}}</strong></div><div class="task-stat"><span>缓存读取率</span><strong>${{hit}}%</strong></div><div class="task-stat"><span>排除串线</span><strong>${{task.foreign_events_excluded}}</strong></div></div><div class="trace-list">${{steps.map(renderStep).join('')}}</div></section>`;
      }}).join('');
      report.innerHTML = blocks || '<div class="empty">没有符合当前筛选条件的操作。</div>';
    }}
    [taskFilter,toolFilter,statusFilter].forEach(el => el.addEventListener('change',render));
    search.addEventListener('input',render);
    document.getElementById('expandAll').addEventListener('click',event => {{
      const rows = [...document.querySelectorAll('.step-row')];
      const shouldOpen = rows.some(row => !row.open);
      rows.forEach(row => row.open = shouldOpen);
      event.currentTarget.textContent = shouldOpen ? '折叠当前' : '展开当前';
    }});
    render();
  </script>
</body>
</html>'''


# 生成四个 SWE-bench 任务的自包含历史操作轨迹报告。
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sessions-root",
        type=Path,
        default=Path.home() / ".sztu" / "sessions",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/reports/swebench-four-task-operation-trace.html"),
    )
    args = parser.parse_args()

    traces = [
        _build_task_trace(task, args.sessions_root / session_id)
        for task, session_id in SESSIONS.items()
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_html_document(traces), encoding="utf-8", newline="\n")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
