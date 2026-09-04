(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();

  var fontFamily = "'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', sans-serif";

  // --- Chart 1: 经验数据价值挖掘的代表性实证增益（横向条形图） ---
  var el = document.getElementById('chart-gain');
  if (el) {
    var chart = echarts.init(el, null, { renderer: 'svg' });

    // 数据来源：各文献原文报告的数值
    // 升序排列（echarts category 轴 index 0 显示在底部）
    var cats = [
      'TopoCurate · BFCLv3（SFT 轨迹选择）',
      'TopoCurate · Tau2-Bench（RL 任务选择）',
      'SWE-Prime · SWE-Bench Pro（精选10% vs 全量）',
      'SWE-Prime · SWE-Bench Verified（精选10% vs 全量）',
      'ToE · Game of 24 准确率（vs 无经验基线）',
      'ToE · FinEvolveBench tsIC（vs 无经验管线）',
      'SkillMentor · AppWorld/BFCLv3 平均（冻结执行器）'
    ];
    var vals = [4.2, 6.9, 12.2, 24.2, 31.4, 41.24, 44.2];
    // 前 4 项为数据筛选类（灰），后 3 项为经验/技能管理类（青）
    var colors = [accent, accent, accent, accent, accent2, accent2, accent2];

    chart.setOption({
      animation: false,
      fontFamily: fontFamily,
      title: {
        text: '相对提升（%）',
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
          var notes = [
            'SFT 轨迹选择相对 SOTA 基线的绝对提升',
            'RL 任务选择相对 SOTA 基线的绝对提升',
            '精选 10% 轨迹训练相对全量成功轨迹的相对提升',
            '精选 10% 轨迹训练相对全量成功轨迹的相对提升',
            '经验树管理相对无经验 ToT 基线的相对提升',
            '经验树管理相对无经验管线的平均相对提升（12 项设置）',
            '盲区诊断技能注入相对冻结执行器的平均绝对提升'
          ];
          return p.name + '<br/>提升：' + p.value + '%<br/><span style="color:#5b6472">口径：' + notes[p.dataIndex] + '</span>';
        }
      },
      grid: { left: 4, right: 60, top: 36, bottom: 10, containLabel: true },
      xAxis: {
        type: 'value',
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
            return { value: v, itemStyle: { color: colors[i] } };
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
              return '+' + p.value + '%';
            }
          },
          markLine: {
            silent: true,
            symbol: 'none',
            data: [
              {
                xAxis: 10,
                lineStyle: { color: muted, type: 'dashed', width: 1.5 },
                label: {
                  formatter: '数据筛选类增益下限',
                  position: 'insideEndTop',
                  color: muted,
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

  // --- Chart 2: 多代际闭环进化的预期形态（折线图，概念示意） ---
  var el2 = document.getElementById('chart-loop');
  if (el2) {
    var chart2 = echarts.init(el2, null, { renderer: 'svg' });

    var gens = ['G0', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8', 'G9', 'G10'];

    chart2.setOption({
      animation: false,
      fontFamily: fontFamily,
      title: {
        text: '任务成功率（%，示意）',
        left: 0,
        top: 0,
        textStyle: { fontSize: 13, color: muted, fontWeight: 400, fontFamily: fontFamily }
      },
      tooltip: {
        trigger: 'axis',
        appendToBody: true,
        textStyle: { fontFamily: fontFamily }
      },
      legend: {
        top: 0,
        right: 0,
        textStyle: { color: ink, fontFamily: fontFamily, fontSize: 12 },
        itemWidth: 18,
        itemHeight: 10
      },
      grid: { left: 8, right: 24, top: 52, bottom: 10, containLabel: true },
      xAxis: {
        type: 'category',
        data: gens,
        name: '进化代际',
        nameLocation: 'end',
        nameTextStyle: { color: muted, fontFamily: fontFamily, fontSize: 12 },
        axisLabel: { color: muted, fontFamily: fontFamily },
        axisLine: { lineStyle: { color: rule } },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        min: 20,
        max: 70,
        axisLabel: { color: muted, fontFamily: fontFamily, formatter: '{value}%' },
        axisLine: { lineStyle: { color: rule } },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } }
      },
      series: [
        {
          name: '开环自训练（无验证器）',
          type: 'line',
          data: [42, 47, 51, 54, 52, 47, 41, 35, 30, 27, 25],
          lineStyle: { color: '#c2452d', width: 2.5 },
          itemStyle: { color: '#c2452d' },
          symbol: 'circle',
          symbolSize: 6,
          markPoint: {
            symbol: 'pin',
            symbolSize: 1,
            label: {
              formatter: '倒 U 崩溃',
              color: '#c2452d',
              fontSize: 11,
              fontFamily: fontFamily,
              position: 'top',
              offset: [26, -2]
            },
            itemStyle: { color: 'transparent' },
            coord: ['G4', 52]
          }
        },
        {
          name: '验证器分级 + 配比控制（本课题机制）',
          type: 'line',
          data: [42, 44, 47, 49, 51, 52, 53, 54, 54, 55, 55],
          lineStyle: { color: accent, width: 2.5 },
          itemStyle: { color: accent },
          symbol: 'circle',
          symbolSize: 6,
          markPoint: {
            symbol: 'pin',
            symbolSize: 1,
            label: {
              formatter: '单调上升后趋平台',
              color: accent,
              fontSize: 11,
              fontFamily: fontFamily,
              position: 'top',
              offset: [-16, -2]
            },
            itemStyle: { color: 'transparent' },
            coord: ['G10', 55]
          }
        },
        {
          name: '新鲜真实数据持续补给（参考上界）',
          type: 'line',
          data: [42, 45, 49, 52, 55, 57, 59, 60, 62, 63, 64],
          lineStyle: { color: accent2, width: 2, type: 'dashed' },
          itemStyle: { color: accent2 },
          symbol: 'none'
        },
        {
          name: '恒定基线（不进化）',
          type: 'line',
          data: [42, 42, 42, 42, 42, 42, 42, 42, 42, 42, 42],
          lineStyle: { color: muted, width: 1.5, type: 'dotted' },
          itemStyle: { color: muted },
          symbol: 'none'
        }
      ]
    });

    window.addEventListener('resize', function () { chart2.resize(); });
  }
})();
