# doc-typeset / meeting-minutes prompt

继承 `base.md` 的全部规则，并应用以下会议纪要专属排版规范。

## 会议基本信息表

使用两列 `<th scope="row">` 布局：

```html
<table class="meeting-meta">
  <tbody>
    <tr><th scope="row">会议名称</th><td>{{meeting_name}}</td></tr>
    <tr><th scope="row">会议时间</th><td>{{date}} {{time}}</td></tr>
    <tr><th scope="row">会议地点</th><td>{{location}}</td></tr>
    <tr><th scope="row">主持人</th><td>{{host}}</td></tr>
    <tr><th scope="row">记录人</th><td>{{recorder}}</td></tr>
  </tbody>
</table>
```

## 出席人员表

```html
<table class="attendee-table">
  <thead>
    <tr><th>姓名</th><th>部门</th><th>职务</th><th>参会方式</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>{{name}}</td><td>{{dept}}</td>
      <td>{{title}}</td><td>{{attendance_mode}}</td>
    </tr>
  </tbody>
</table>
```

`attendance_mode` 值：现场、视频、电话

## 议题列表

```html
<ol class="agenda-list">
  <li class="agenda-item" id="agenda-{{n}}">
    <h3 class="agenda-title">议题{{n}}：{{topic_title}}</h3>
    <div class="agenda-content">{{discussion_content}}</div>
  </li>
</ol>
```

## 决议与待办

```html
<!-- 决议 -->
<ul class="resolution-list">
  <li class="resolution-item resolution-done">
    <span class="resolution-status">✅</span>
    <span class="resolution-content">{{resolution_text}}</span>
    <span class="resolution-owner">负责人：{{owner}}</span>
  </li>
</ul>

<!-- 待办事项 -->
<ul class="action-list">
  <li class="action-item action-pending">
    <span class="action-status">🔄</span>
    <span class="action-content">{{action_text}}</span>
    <span class="action-owner">负责人：{{owner}} / 截止：{{deadline}}</span>
  </li>
</ul>
```

## 签署区

```html
<footer class="sign-info">
  <p>记录人：_______________</p>
  <p>审核人：_______________</p>
  <p>批准人：_______________</p>
  <p>日期：_______________</p>
</footer>
```

## 装饰组件触发规则

| 触发位置 | 组件 | style/variant |
|---------|------|---------------|
| 会议信息区与议题区之间 | divider | simple |
| 各议题之间（议题较多时） | divider | section-break |
| 重要决议 | callout | info |
