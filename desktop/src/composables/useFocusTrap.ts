import { nextTick, type Ref } from "vue";

/**
 * 模态框焦点陷阱 composable（Issue #28）
 *
 * - setInitialFocus: 打开后把焦点放到弹窗内首个可聚焦控件
 * - trapTab: 让 Tab / Shift+Tab 在当前容器内循环，不逸出到遮罩后的工作台
 * - restoreFocus: 关闭后把焦点恢复到打开前的触发控件
 */
export function useFocusTrap() {
  function isFocusable(el: HTMLElement): boolean {
    if (el.hasAttribute("disabled") || el.getAttribute("aria-hidden") === "true") return false;
    const tag = el.tagName.toLowerCase();
    if (tag === "button" || tag === "input" || tag === "select" || tag === "textarea") return true;
    if (tag === "a") return el.hasAttribute("href");
    return el.tabIndex >= 0;
  }

  function focusableElements(container: HTMLElement): HTMLElement[] {
    return Array.from(container.querySelectorAll<HTMLElement>(
      "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex='-1'])",
    )).filter((el) => isFocusable(el) && el.offsetParent !== null);
  }

  async function setInitialFocus(container: Ref<HTMLElement | null> | (() => HTMLElement | null)) {
    await nextTick();
    const root = typeof container === "function" ? container() : container.value;
    if (!root) return;
    const els = focusableElements(root);
    (els[0] ?? root)?.focus();
  }

  function trapTab(event: KeyboardEvent, container: Ref<HTMLElement | null> | (() => HTMLElement | null)) {
    const root = typeof container === "function" ? container() : container.value;
    if (!root) return;
    const els = focusableElements(root);
    if (!els.length) return;
    const first = els[0]!;
    const last = els[els.length - 1]!;
    const active = document.activeElement;

    if (event.shiftKey) {
      if (active === first || !root.contains(active)) {
        event.preventDefault();
        last.focus();
      }
    } else if (active === last || !root.contains(active)) {
      event.preventDefault();
      first.focus();
    }
  }

  async function restoreFocus(trigger: HTMLElement | null | undefined, fallback?: HTMLElement | null) {
    await nextTick();
    if (trigger && trigger.isConnected) trigger.focus();
    else fallback?.focus();
  }

  return { setInitialFocus, trapTab, restoreFocus, focusableElements };
}
