import type { TimelineItem as TimelineItemType } from "../../types";

type Props = {
  item: TimelineItemType;
  measureRef?: (el: HTMLElement | null) => void;
};

const kindLabel: Record<string, string> = {
  system: "系统",
  tool: "工具调用",
  user: "你",
  agent: "Agent",
};

/** 单条时间线条目 */
export function TimelineEntry({ item, measureRef }: Props) {
  return (
    <article
      className={`timeline-item ${item.kind}`}
      ref={measureRef}
    >
      <div className="item-rail"><i /></div>
      <div className="item-content">
        {item.title && (
          <header>
            <span>{kindLabel[item.kind] ?? item.kind}</span>
            <b>{item.title}</b>
            <em>{item.state}</em>
          </header>
        )}
        <pre className={item.kind === "agent" ? "prose" : "code"}>
          {item.body}
        </pre>
      </div>
    </article>
  );
}
