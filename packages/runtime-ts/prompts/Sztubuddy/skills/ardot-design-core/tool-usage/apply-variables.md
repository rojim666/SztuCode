# Usage

- By default (merge mode), only the specified variable sets and variables are created or updated; existing ones not mentioned are left untouched.
- When `replace` is true, variable sets and variables NOT present in the input will be **deleted**. Use with caution.

## Input Format
`variables` is a map of **variable set name** \u2192 **definition**:
> **Naming restriction**: Variable set names and variable names must NOT contain `$` or `:` characters, as these are reserved for the variable reference syntax `$:<SetName>:<VariableName>` used in `batch_edit`.

```json
{
  "<SetName>": {
    "modes": ["<Mode1>", "<Mode2>"],
    "variables": {
      "<varName>": {
        "type": "FLOAT" | "BOOLEAN" | "STRING" | "COLOR",
        "valuesByMode": { "<Mode1>": <value>, "<Mode2>": <value> },
        "scopes": ["ALL_FILLS"]
      }
    }
  }
}
```
**Fields**:
- **SetName**: Variable set name. Must NOT contain `$` or `:` characters.
- **varName**: Variable name within the set. Must NOT contain `$` or `:` characters.
- **modes**: Optional string array. If omitted, keeps default "Mode 1". If specified, "Mode 1" is renamed to the first mode.
- **type**: `"BOOLEAN"`, `"FLOAT"`, `"STRING"`, or `"COLOR"`.
- **valuesByMode**: Values keyed by mode name. Or use `"value"` to set the same value for all modes.
- **scopes** (optional): `"ALL_SCOPES"`, `"TEXT_CONTENT"`, `"CORNER_RADIUS"`, `"WIDTH_HEIGHT"`, `"GAP"`, `"ALL_FILLS"`, `"FRAME_FILL"`, `"SHAPE_FILL"`, `"TEXT_FILL"`, `"STROKE"`, `"STROKE_FLOAT"`, `"EFFECT_FLOAT"`, `"EFFECT_COLOR"`, `"OPACITY"`, `"FONT_STYLE"`, `"FONT_FAMILY"`, `"FONT_SIZE"`, `"LINE_HEIGHT"`, `"LETTER_SPACING"`, `"PARAGRAPH_SPACING"`, `"PARAGRAPH_INDENT"`, `"FONT_VARIATIONS"`
**Value formats**: BOOLEAN \u2192 `true/false`, FLOAT \u2192 number, STRING \u2192 string, COLOR \u2192 `{"r": 0~1, "g": 0~1, "b": 0~1, "a": 0~1}` (NOT hex strings).

## Example
```json
{
  "Design Tokens": {
    "modes": ["Light", "Dark"],
    "variables": {
      "bgColor": {
        "type": "COLOR",
        "valuesByMode": {
          "Light": {"r": 1, "g": 1, "b": 1, "a": 1},
          "Dark": {"r": 0.1, "g": 0.1, "b": 0.1, "a": 1}
        },
        "scopes": ["ALL_FILLS"]
      },
      "borderRadius": { "type": "FLOAT", "value": 8 }
    }
  }
}
```