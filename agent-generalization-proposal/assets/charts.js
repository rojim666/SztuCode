(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  var fontFamily = "'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', sans-serif";

  // --- Chart 1: 泛化鸿沟对比（横向条形图）---
  var el = document.getElementById('chart-gap');
  if (el) {
    var chart = echarts.init(el, null, { renderer: 'svg' });

    // 数据来源：各基准论文原文报告的数值
    var cats = [
      '人类 · ComplexMCP',
      '顶级模型上限 · ComplexMCP',
      '静态基线最佳 · tau2-bench 漂移实验',
      'GPT-5 (high) · Gaia2 总体最强',
      'Kimi-K2 · Gaia2 开源最强',
      '静态基线最差 · tau2-bench 漂移实验'
    ];
    var vals = [90, 60, 43.2, 42, 21, 13.0];
    var colors = [accent2, accent, accent, accent, accent, accent];

    chart.setOption({
      animation: false,
      fontFamily: fontFamily,
      title: {
        text: '任务成功率（%）',
        left: 0,
        top: 0,
        textStyle: { fontSize: 13, color: muted, fontWeight: 400, fontFamily: fontFamily }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        appendToBody: true,
        formatter: function (params) {
          var p = params[0];
          var note = '';
          if (p.dataIndex === 0) note = '（人类水平，论文报告为 90% 以上）';
          if (p.dataIndex === 1) note = '（论文表述为"顶级模型未能超过 60%"，此处取上限）';
          if (p.dataIndex === 2 || p.dataIndex === 5) note = '（五个被测模型静态条件成功率范围 13.0–43.2%）';
          return p.name + '<br/>成功率：' + p.value + '%' + note;
        }
      },
      grid: { left: 4, right: 56, top: 36, bottom: 10, containLabel: true },
      xAxis: {
        type: 'value',
        max: 100,
        axisLabel: { color: muted, fontFamily: fontFamily, formatter: '{value}%' },
        axisLine: { lineStyle: { color: rule } },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      yAxis: {
        type: 'category',
        data: cats,
        axisLabel: { color: ink, fontSize: 12, fontFamily: fontFamily },
        axisLine: { lineStyle: { color: rule } },
        axisTick: { show: false }
      },
      series: [
        {
          type: 'bar',
          data: vals.map(function (v, i) {
            return { value: v, itemStyle: { color: colors[i], opacity: i === 1 ? 0.55 : 1 } };
          }),
          barWidth: '55%',
          label: {
            show: true,
            position: 'right',
            color: ink,
            fontFamily: fontFamily,
            fontSize: 12,
            fontWeight: 600,
            formatter: function (p) {
              return p.value + '%';
            }
          },
          markLine: {
            silent: true,
            symbol: 'none',
            data: [
              {
                xAxis: 50,
                lineStyle: { color: accent2, type: 'dashed', width: 1.5 },
                label: {
                  formatter: 'MAVEN 多数模型 <50%',
                  position: 'insideEndTop',
                  color: accent2,
                  fontSize: 11,
                  fontFamily: fontFamily
                }
              }
            ]
          }
        }
      ]
    });

    window.addEventListener('resize', function () { chart.resize(); });
  }
})();
