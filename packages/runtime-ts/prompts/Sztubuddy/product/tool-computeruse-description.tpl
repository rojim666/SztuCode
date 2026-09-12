Control the macOS desktop by taking screenshots and simulating mouse/keyboard
input. This tool follows Anthropic's `computer_20250124` parameter schema.

**Experimental.** This tool is macOS-only and disabled unless
`CODEBUDDY_COMPUTER_USE_ENABLED=1` is set in the environment. Behavior may
change in future releases. Each action requires the user's approval unless an
allow rule is configured.

## Actions

- `screenshot` — Capture the current display. The image is returned
  directly in the tool_result so you can see it immediately — you do NOT
  need a separate Read call. Images are downscaled to 1280px on the longest
  edge and returned as JPEG to keep context costs low.

  **MANDATORY observation protocol (防幻视):**
  After EVERY screenshot, BEFORE any click/type/key action, your first
  response MUST be a literal pixel-level observation of what is actually
  visible in the returned image:
    - Top menu bar: which app name, which menu items
    - Active window: title bar text, which app owns it
    - Key regions: what text, buttons, input fields are visible; what is
      in each input; where the cursor/focus is
    - For list/candidate UIs (search results, contact lists, file pickers):
      describe the items near the coordinate you plan to click, including
      ±20px neighbors
  Do NOT skip observation and jump to the next action based on an expected
  workflow. Do NOT describe the screen from memory or assumption. If you
  cannot see an element you expected, say so and take another screenshot
  rather than guessing coordinates.

- `left_click` / `right_click` / `middle_click` / `double_click` /
  `triple_click` / `mouse_move` — Interact with a point. Requires
  `coordinate: [x, y]` in logical pixels (top-left origin). Before any
  irreversible click (send message, confirm, submit), take a fresh
  screenshot and observe again.

- `left_click_drag` — Press at `start_coordinate`, drag to `coordinate`,
  release. Both are `[x, y]` arrays.

- `type` — Type arbitrary text (`text` field) at the current focus.
  Supports Unicode (including CJK). Do NOT use this for keyboard shortcuts.

- `key` — Press a key or shortcut with xdotool syntax in the `text` field:
  `"escape"`, `"return"`, `"cmd+shift+a"`, `"ctrl+c"`. Supported modifiers:
  `cmd`, `ctrl`, `alt`/`option`, `shift`, `fn`. Supported named keys: return,
  tab, space, delete/backspace, escape, left, right, up, down, home, end,
  pageup, pagedown, f1-f12. Single characters use the character directly.

- `hold_key` — Hold a single named key (`text`) for `duration` seconds.
  Modifiers are not supported in hold_key.

- `scroll` — Scroll at `coordinate: [x, y]` in `scroll_direction`
  (up/down/left/right) for `scroll_amount` ticks (default 3). Requires
  cliclick (`brew install cliclick`).

- `wait` — Pause for `duration` seconds. Use this to let UI transitions
  settle before another action.

- `cursor_position` — Return the current mouse position.

## Usage notes

- Coordinates use LOGICAL pixels, not physical. Always take a fresh
  `screenshot` first — never reuse old coordinates.

- Launching an app: prefer `key: "cmd+space"` (Spotlight) → `type: "<app>"`
  → `key: "return"` over hunting for Dock/desktop icons, which depends on
  unreliable UI layout.

- Brand confusion on macOS: searching "WeChat" in Spotlight opens **企业
  微信 (WeCom)**, not personal 微信 (WeChat). Search "微信" for personal
  WeChat. Always confirm the opened app by reading the top menu bar app
  name in the next screenshot.

- First-time invocation may trigger macOS Accessibility / Screen Recording
  permission prompts. If an action returns a permission error, ask the user
  to open System Settings → Privacy & Security → Accessibility and enable
  their terminal application, then restart it.

- `cliclick` is an optional dependency. When installed, it provides faster
  and more reliable mouse control and is required for `mouse_move`,
  `middle_click`, `triple_click`, `left_click_drag`, and `scroll`. Without
  it, the other actions fall back to AppleScript (osascript).
