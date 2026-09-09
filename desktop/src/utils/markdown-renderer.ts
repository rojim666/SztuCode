import { Renderer, type Tokens } from "marked";

/** Keep native table sizing; only the surrounding region should scroll. */
export class ScrollableTableRenderer extends Renderer {
  override table(token: Tokens.Table): string {
    return `<div class="markdown-table-scroll" tabindex="0">${super.table(token)}</div>\n`;
  }
}
