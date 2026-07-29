import { FileCode2, FolderOpen } from "lucide-react";
import type { FileNode } from "../../types";

type FilePanelProps = {
  nodes: FileNode[];
  onOpenFile: (node: FileNode) => void;
  onRefresh: () => void;
};

/** 工作区文件树面板 */
export function FilePanel({ nodes, onOpenFile, onRefresh }: FilePanelProps) {
  if (!nodes.length) return null;

  function renderTree(items: FileNode[], depth = 0): React.ReactNode {
    return items.map((node) =>
      node.kind === "directory" ? (
        <div className="tree-directory" key={node.path} style={{ paddingLeft: depth * 10 }}>
          <span>
            <FolderOpen size={13} />
            {node.name}
          </span>
          {node.children && renderTree(node.children, depth + 1)}
        </div>
      ) : (
        <button
          className="tree-file"
          key={node.path}
          style={{ paddingLeft: depth * 10 + 4 }}
          onClick={() => onOpenFile(node)}
        >
          <FileCode2 size={13} />
          {node.name}
        </button>
      ),
    );
  }

  return (
    <section className="file-panel">
      <header>
        <FolderOpen size={15} />
        <span>文件</span>
        <button onClick={onRefresh}>刷新</button>
      </header>
      <div className="file-tree">{renderTree(nodes)}</div>
    </section>
  );
}
