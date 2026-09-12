---
name: ardot-ui-design
description: "Use this skill for Ardot canvas design tasks whose deliverable is a UI / interface design — web pages, web apps, dashboards, landing pages, marketing sites, official sites, homepages, mobile app screens (iOS / Android / 小程序), forms, tables, components, and design systems / design tokens / component libraries. Trigger phrases: generate/create/design a page, design a screen, create a landing page, make a dashboard, design a login screen, build a UI, generate homepage, design a form, design an App, WebApp, 设计页面, 创建界面, 生成页面, 生成网站, 设计App, 做一个页面, 画一个页面, 设计后台, 组件库规范, 设计系统, Design System, Design Token, 移动端, 手机App, 小程序. Pairs with ardot-design-core (injected alongside). NOT for slides/posters/design-to-code (separate Ardot skills) and NOT for PowerPoint .pptx files (pptx skill)."
allowed-tools: 
disable-model-invocation: true
user-invocable: false
---

# Ardot UI Design

Domain guidelines for **UI / interface** deliverables on the Ardot canvas: web pages, web apps, dashboards, landing pages, mobile app screens, tables, forms, components, and design systems.

> **The general workflow and hard rules live in `ardot-design-core`**, which is injected alongside this skill. This skill only adds the **domain-specific guidelines** for UI work. Follow `ardot-design-core` for the step sequence (Step 0 file-open → Step 8 validate), schema, editing rules, effects, and screenshot verification.

## Domain Guidelines (load in Step 3)

Load **one or more** guideline based on the deliverable, first match wins:

| Priority | Trigger | File |
|---|---|---|
| 1 | any mobile app design task — mobile, app, iOS, Android, app UI, 移动端, 手机 App, 移动应用, 小程序 | `{SKILL_ROOT}/references/guidelines-mobile-app.md` |
| 2 | any website task — landing, marketing, SaaS, product site, official site, homepage, 网站, 官网, 落地页, 营销 | `{SKILL_ROOT}/references/guidelines-landing-page.md` |
| 3 | table, dashboard with tables, 表格 | `{SKILL_ROOT}/references/guidelines-table.md` |
| 4 | (web app / design system / generic UI, default) | `{SKILL_ROOT}/references/guidelines-web-app.md` |

- **Design system / component library / design tokens** tasks use the default `guidelines-web-app.md` as the base, applying the same component/typography/color discipline at library scope (build a token set, component states, spacing scale).
- **Image-to-UI** (reproducing a UI from a reference image): follow the same guidelines, but treat the supplied image as the layout/visual source of truth and reproduce its structure faithfully before restyling.

When code generation is also involved, load `guidelines-code.md` / `guidelines-tailwind.md` from the `ardot-design-to-code` skill alongside the chosen guideline above.
