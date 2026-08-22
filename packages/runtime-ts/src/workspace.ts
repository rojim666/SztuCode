import path from "node:path";
import { readFile, writeFile, readdir, stat, realpath } from "node:fs/promises";

export class WorkspaceBoundaryError extends Error {}

export class Workspace {
  readonly root: string;
  constructor(root: string) { this.root = path.resolve(root); }

  resolve(relativePath: string): string {
    const candidate = path.resolve(this.root, relativePath);
    const relative = path.relative(this.root, candidate);
    if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) throw new WorkspaceBoundaryError(`Path escapes workspace: ${relativePath}`);
    return candidate;
  }

  // 解析并校验真实路径（防符号链接逃逸）：从目标路径向上找到第一个
  // 存在的祖先做 realpath（覆盖新建文件/嵌套目录的场景），并确保其真实
  // 路径位于工作区根内；任一环节越界即拒绝
  async resolveExisting(relativePath: string): Promise<string> {
    const target = this.resolve(relativePath);
    const realRoot = await realpath(this.root);
    let cursor = target;
    let realTarget: string;
    for (;;) {
      try {
        realTarget = await realpath(cursor);
        break;
      } catch {
        const parent = path.dirname(cursor);
        if (parent === cursor) throw new WorkspaceBoundaryError(`Cannot resolve path: ${relativePath}`);
        cursor = parent;
      }
    }
    const relative = path.relative(realRoot, realTarget);
    if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) throw new WorkspaceBoundaryError(`Path escapes workspace: ${relativePath}`);
    return target;
  }

  async read(relativePath: string): Promise<string> { return readFile(await this.resolveExisting(relativePath), "utf8"); }
  async write(relativePath: string, content: string): Promise<void> { await writeFile(await this.resolveExisting(relativePath), content, "utf8"); }
  async list(relativePath = ".", maxDepth = 2, maxEntries = 200): Promise<string[]> {
    const root = this.resolve(relativePath); const output: string[] = [`${root}/`]; let count = 0;
    const walk = async (directory: string, depth: number, prefix: string): Promise<void> => {
      if (depth > maxDepth || count >= maxEntries) return;
      const entries = (await readdir(directory, { withFileTypes: true })).sort((a, b) => Number(a.isFile()) - Number(b.isFile()) || a.name.localeCompare(b.name));
      for (let index = 0; index < entries.length && count < maxEntries; index += 1) {
        const entry = entries[index]; const last = index === entries.length - 1; const suffix = entry.isDirectory() ? "/" : "";
        output.push(`${prefix}${last ? "└── " : "├── "}${entry.name}${suffix}`); count += 1;
        if (entry.isDirectory() && depth < maxDepth) await walk(path.join(directory, entry.name), depth + 1, `${prefix}${last ? "    " : "│   "}`);
      }
      if (count >= maxEntries) output.push(`${prefix}... (truncated)`);
    };
    if (!(await stat(root)).isDirectory()) throw new Error(`not a directory: ${relativePath}`);
    await walk(root, 1, ""); return output;
  }
}
