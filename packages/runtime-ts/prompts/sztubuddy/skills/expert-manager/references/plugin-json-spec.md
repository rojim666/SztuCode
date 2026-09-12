# plugin.json 字段规范

## 基础字段（必填）

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 唯一标识，小写字母+连字符，也是技能命名空间前缀 |
| `version` | string | 语义化版本号（MAJOR.MINOR.PATCH） |
| `description` | string | 英文一句话描述 |

## 可选基础字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `author` | `{name, email}` | 作者信息 |
| `homepage` | string 或 `{url, type}` | 项目主页 |
| `license` | string | 许可证 |
| `keywords` | string[] | 搜索标签 |

## 类型字段

| 字段 | 说明 |
|------|------|
| `expertType` | `"agent"` / `"team"` |
| `agentName` | 主 Agent 名称（对应 agents/ 下 MD 文件名，不含 .md）。**必须有业务语义**，不能使用 `team-lead` 等通用名 |
| `teamInfo` | team 时必填：`{leadAgent, memberAgents[]}` |

## 资源声明

| 字段 | 类型 | 说明 |
|------|------|------|
| `agents` | string[] | Agent 定义文件路径列表（如 `["./agents/my-expert.md"]`） |
| `skills` | string[] | Skill 目录路径列表（如 `["./skills/my-skill"]`） |

## 展示字段（agent/team 上架市场时必填）

| 字段 | 类型 | 说明 |
|------|------|------|
| `displayName` | `{en, zh}` | 展示名称 |
| `profession` | `{en, zh}` | 职业/定位。**Team 型须与 displayName 一致** |
| `displayDescription` | `{en, zh}` | 展示描述。**中文 40-50 字，突出核心能力** |
| `avatar` | string | 头像相对路径 |
| `categoryId` | string | 行业分类 ID |
| `defaultInitPrompt` | `{en, zh}` | 默认引导语。**须与 quickPrompts 第一条一致** |
| `tags` | `{en, zh}[]` | 擅长领域标签（**固定 3 个**） |
| `quickPrompts` | `{en, zh}[]` | 推荐提示词（**固定 3 个**） |
| `plugin` | string | 值与 `name` 一致 |

## Team 专用字段

| 字段 | 说明 |
|------|------|
| `members[]` | 每个成员含 `{id, name:{en,zh}, profession:{en,zh}, avatar, role}` |

- `role` 取值：`"lead"` 或 `"member"`
- 主理人也必须在 members 中，role 为 `"lead"`
- `teamInfo.memberAgents` **不含**主理人

---

## 模板：Agent 型

```json
{
  "name": "{kebab-case-name}",
  "version": "1.0.0",
  "description": "{English one-line description}",
  "author": {
    "name": "{author-name}",
    "email": "{author-email}"
  },
  "agents": ["./agents/{agent-name}.md"],
  "skills": ["./skills/{skill-name}"],

  "expertType": "agent",
  "agentName": "{agent-name}",

  "displayName": {
    "en": "{English display name}",
    "zh": "{中文显示名称}"
  },
  "profession": {
    "en": "{English profession}",
    "zh": "{中文职业头衔}"
  },
  "displayDescription": {
    "en": "{English detailed description}",
    "zh": "{中文详细描述，40-50字}"
  },
  "avatar": "avatars/expert.png",
  "categoryId": "{XX-CategoryName}",
  "defaultInitPrompt": {
    "zh": "{中文首次对话提示}",
    "en": "{English first prompt}"
  },
  "plugin": "{kebab-case-name}",
  "tags": [
    { "en": "{Tag1 EN}", "zh": "{标签1}" },
    { "en": "{Tag2 EN}", "zh": "{标签2}" },
    { "en": "{Tag3 EN}", "zh": "{标签3}" }
  ],
  "quickPrompts": [
    { "en": "{Prompt1 EN}", "zh": "{提示词1}" },
    { "en": "{Prompt2 EN}", "zh": "{提示词2}" },
    { "en": "{Prompt3 EN}", "zh": "{提示词3}" }
  ]
}
```

> 如果没有 skills，则省略 `"skills"` 字段。

## 模板：Team 型

```json
{
  "name": "{kebab-case-name}",
  "version": "1.0.0",
  "description": "{English one-line description}",
  "author": {
    "name": "{author-name}",
    "email": "{author-email}"
  },
  "agents": [
    "./agents/{team}-team-lead.md",
    "./agents/{member-a}.md",
    "./agents/{member-b}.md"
  ],
  "skills": ["./skills/{skill-name}"],

  "expertType": "team",
  "agentName": "{team}-team-lead",
  "teamInfo": {
    "leadAgent": "{team}-team-lead",
    "memberAgents": ["{member-a}", "{member-b}"]
  },

  "displayName": {
    "en": "{English team name}",
    "zh": "{中文团队名称}"
  },
  "profession": {
    "en": "{English team name}",
    "zh": "{中文团队名称}"
  },
  "displayDescription": {
    "en": "{English team description}",
    "zh": "{中文团队描述，40-50字}"
  },
  "avatar": "avatars/team.png",
  "categoryId": "{XX-CategoryName}",
  "defaultInitPrompt": {
    "zh": "{中文首次问候}",
    "en": "{English first prompt}"
  },
  "plugin": "{kebab-case-name}",
  "tags": [
    { "en": "{Tag1 EN}", "zh": "{标签1}" },
    { "en": "{Tag2 EN}", "zh": "{标签2}" },
    { "en": "{Tag3 EN}", "zh": "{标签3}" }
  ],
  "quickPrompts": [
    { "en": "{Prompt1 EN}", "zh": "{提示词1}" },
    { "en": "{Prompt2 EN}", "zh": "{提示词2}" },
    { "en": "{Prompt3 EN}", "zh": "{提示词3}" }
  ],
  "members": [
    {
      "id": "{team}-team-lead",
      "displayName": { "en": "{EN}", "zh": "{ZH}" },
      "profession": { "en": "{EN}", "zh": "{ZH}" },
      "avatar": "avatars/{team}-team-lead.png",
      "role": "lead"
    },
    {
      "id": "{member-name}",
      "displayName": { "en": "{EN}", "zh": "{ZH}" },
      "profession": { "en": "{EN}", "zh": "{ZH}" },
      "avatar": "avatars/{member-name}.png",
      "role": "member"
    }
  ]
}
```

