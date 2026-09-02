/* Recuris 调研报告 — 图表脚本（ECharts + Mermaid） */
(function () {
  'use strict';

  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim() || '#b4531f';
  var accent2 = style.getPropertyValue('--accent2').trim() || '#54504a';
  var ink = style.getPropertyValue('--ink').trim() || '#1a1917';
  var muted = style.getPropertyValue('--muted').trim() || '#73706b';
  var rule = style.getPropertyValue('--rule').trim() || '#e5e3df';
  var bg2 = style.getPropertyValue('--bg2').trim() || '#f4f3f1';

  var CJK = "'Instrument Sans', 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'Microsoft YaHei', sans-serif";

  function baseAxisLabel() {
    return { color: muted, fontSize: 12, fontFamily: CJK };
  }

  var charts = [];

  function makeChart(id, option) {
    var el = document.getElementById(id);
    if (!el) return null;
    var c = echarts.init(el, null, { renderer: 'svg' });
    c.setOption(option);
    charts.push(c);
    return c;
  }

  /* ---------- 图 2：τ²-Retail 裸 Agent vs +Recuris ---------- */
  var retailModels = [
    'Granite-4.1-3B', 'Qwen3.5-4B', 'Qwen3.5-9B', 'GPT-OSS-20B', 'Qwen3.6-27B',
    'Qwen3.6-35B', 'Gemini 3.7 Flash', 'GPT-5.6 Sol', 'Claude Opus 5', 'Doubao-2.0-Pro'
  ];
  var bareScores = [9.7, 68.0, 77.6, 50.6, 62.8, 78.2, 73.5, 58.3, 72.4, 58.1];
  var recurisScores = [23.0, 68.3, 79.6, 60.8, 71.2, 78.5, 78.3, 76.1, 87.9, 81.4];

  makeChart('chart-retail', {
    animation: false,
    textStyle: { fontFamily: CJK },
    grid: { left: 130, right: 40, top: 44, bottom: 30 },
    legend: {
      top: 0,
      itemWidth: 14,
      itemHeight: 9,
      textStyle: { color: ink, fontSize: 12, fontFamily: CJK }
    },
    tooltip: {
      appendToBody: true,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: function (v) { return v + '%'; },
      textStyle: { fontFamily: CJK }
    },
    xAxis: {
      type: 'value',
      max: 100,
      name: '任务成功率（%）',
      nameTextStyle: { color: muted, fontSize: 11, fontFamily: CJK },
      axisLabel: baseAxisLabel(),
      splitLine: { lineStyle: { color: rule } },
      axisLine: { show: false }
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: retailModels,
      axisLabel: { color: ink, fontSize: 12, fontFamily: CJK },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [
      {
        name: '裸 Agent',
        type: 'bar',
        data: bareScores,
        barWidth: 10,
        itemStyle: { color: muted, borderRadius: [0, 2, 2, 0] },
        label: { show: false }
      },
      {
        name: '+ Recuris',
        type: 'bar',
        data: recurisScores,
        barWidth: 10,
        itemStyle: { color: accent, borderRadius: [0, 2, 2, 0] },
        label: {
          show: true,
          position: 'right',
          color: ink,
          fontSize: 11,
          fontFamily: CJK,
          formatter: function (p) {
            var d = (p.value - bareScores[p.dataIndex]).toFixed(1);
            return '+' + d;
          }
        }
      }
    ]
  });

  /* ---------- 图 3：按交互轮次的成功率提升 ---------- */
  var lenCats = ['≤15 轮', '15–18 轮', '18–21 轮', '21–24 轮', '24–31 轮', '>31 轮'];
  var lenVals = [12.5, 20.0, 27.9, 28.7, 25.7, 32.2];

  makeChart('chart-length', {
    animation: false,
    textStyle: { fontFamily: CJK },
    grid: { left: 50, right: 30, top: 30, bottom: 40 },
    tooltip: {
      appendToBody: true,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: function (v) { return '+' + v + ' 个百分点'; },
      textStyle: { fontFamily: CJK }
    },
    xAxis: {
      type: 'category',
      data: lenCats,
      axisLabel: { color: ink, fontSize: 12, fontFamily: CJK },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'value',
      max: 36,
      name: '提升（百分点）',
      nameTextStyle: { color: muted, fontSize: 11, fontFamily: CJK },
      axisLabel: baseAxisLabel(),
      splitLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar',
      data: lenVals,
      barWidth: '52%',
      itemStyle: { color: accent, borderRadius: [3, 3, 0, 0] },
      label: {
        show: true,
        position: 'top',
        color: accent,
        fontWeight: 700,
        fontSize: 12,
        fontFamily: CJK,
        formatter: '+{c}'
      }
    }]
  });

  /* ---------- 图 4：六类失败模式削减 ---------- */
  var failCats = ['幻觉式完成', '遗漏写入', '零写入回合', '首个工具调用错误', '错误级联', '遗漏读取'];
  var failVals = [86, 80, 62, 44, 24, 20];

  makeChart('chart-failure', {
    animation: false,
    textStyle: { fontFamily: CJK },
    grid: { left: 130, right: 60, top: 16, bottom: 30 },
    tooltip: {
      appendToBody: true,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: function (v) { return '↓' + v + '%'; },
      textStyle: { fontFamily: CJK }
    },
    xAxis: {
      type: 'value',
      max: 100,
      name: '失败率下降（%）',
      nameTextStyle: { color: muted, fontSize: 11, fontFamily: CJK },
      axisLabel: baseAxisLabel(),
      splitLine: { lineStyle: { color: rule } },
      axisLine: { show: false }
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: failCats,
      axisLabel: { color: ink, fontSize: 12, fontFamily: CJK },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar',
      data: failVals,
      barWidth: 14,
      itemStyle: { color: accent2, borderRadius: [0, 3, 3, 0] },
      label: {
        show: true,
        position: 'right',
        color: accent,
        fontWeight: 700,
        fontSize: 12,
        fontFamily: CJK,
        formatter: '↓{c}%'
      }
    }]
  });

  /* ---------- 图 5：故障定位准确率 ---------- */
  var locCats = ['只看最终成败', '随机基线', '原始轨迹', '结构化轨迹 Γ'];
  var locVals = [13.0, 33.3, 37.0, 64.8];

  makeChart('chart-localize', {
    animation: false,
    textStyle: { fontFamily: CJK },
    grid: { left: 50, right: 30, top: 30, bottom: 40 },
    tooltip: {
      appendToBody: true,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      valueFormatter: function (v) { return v + '%'; },
      textStyle: { fontFamily: CJK }
    },
    xAxis: {
      type: 'category',
      data: locCats,
      axisLabel: { color: ink, fontSize: 12, fontFamily: CJK },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: rule } }
    },
    yAxis: {
      type: 'value',
      max: 70,
      name: '组件归因准确率（%）',
      nameTextStyle: { color: muted, fontSize: 11, fontFamily: CJK },
      axisLabel: baseAxisLabel(),
      splitLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'bar',
      data: locVals.map(function (v, i) {
        return {
          value: v,
          itemStyle: { color: i === 3 ? accent : muted, borderRadius: [3, 3, 0, 0] }
        };
      }),
      barWidth: '48%',
      label: {
        show: true,
        position: 'top',
        color: ink,
        fontWeight: 700,
        fontSize: 12,
        fontFamily: CJK,
        formatter: '{c}%'
      }
    }]
  });

  /* ---------- Mermaid 架构图 ---------- */
  if (typeof mermaid !== 'undefined' && document.querySelector('.mermaid')) {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'neutral',
      securityLevel: 'loose',
      themeVariables: {
        primaryColor: '#f4f3f1',
        primaryBorderColor: '#73706b',
        primaryTextColor: '#1a1917',
        lineColor: '#73706b',
        fontFamily: CJK,
        fontSize: '14px'
      },
      flowchart: { curve: 'basis', htmlLabels: true }
    });
    try {
      mermaid.run({ querySelector: '.mermaid' });
    } catch (e) {
      /* mermaid 渲染失败时保留源码文本 */
    }
  }

  /* ---------- 自适应 ---------- */
  var resizeTimer = null;
  window.addEventListener('resize', function () {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      charts.forEach(function (c) { c.resize(); });
    }, 120);
  });
})();
