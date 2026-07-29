import { useCallback, useRef, useState } from "react";
import { IpcClient } from "../lib/ipc";
import type { Workspace, FileNode, Change } from "../types";
import { errorText } from "../types";
import { open } from "@tauri-apps/plugin-dialog";

/** 工作区管理（打开、切换、文件树、变更列表） */
export function useWorkspace(client: IpcClient) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [changes, setChanges] = useState<Change[]>([]);
  const [treeNodes, setTreeNodes] = useState<FileNode[]>([]);
  const workspaceRef = useRef<Workspace | null>(null);
  const workspacesRef = useRef<Workspace[]>([]);

  workspaceRef.current = workspace;
  workspacesRef.current = workspaces;

  // 刷新变更列表
  const refreshChanges = useCallback(
    async (
      selected?: Workspace | null,
      runId?: string | null,
    ) => {
      const target = selected ?? workspaceRef.current;
      if (!target) return;
      const result = await client.request("change.list", {
        workspace_id: target.workspace_id,
        ...(runId ? { run_id: runId } : {}),
      });
      setChanges((result.changes as Change[]) ?? []);
    },
    [client],
  );

  // 刷新文件树
  const refreshTree = useCallback(
    async (selected?: Workspace | null) => {
      const target = selected ?? workspaceRef.current;
      if (!target) return;
      const result = await client.request("workspace.tree", {
        workspace_id: target.workspace_id,
        max_depth: 2,
        max_entries: 180,
      });
      setTreeNodes((result.nodes as FileNode[]) ?? []);
    },
    [client],
  );

  // 选择本地工作区
  const chooseWorkspace = useCallback(
    async (setNotice: (msg: string) => void) => {
      const selected = await open({
        directory: true,
        multiple: false,
        title: "选择代码仓库",
      });
      if (!selected || Array.isArray(selected)) return;
      try {
        const result = await client.request("workspace.open", { path: selected });
        const next = result.workspace as Workspace;
        setWorkspace(next);
        setWorkspaces((items) => [
          next,
          ...items.filter((item) => item.workspace_id !== next.workspace_id),
        ]);
        setNotice(`已打开 ${next.name}。接下来可以从任务、文件和变更三个视角推进工作。`);
        await refreshChanges(next);
        await refreshTree(next);
      } catch (error) {
        setNotice(`打开工作区失败：${errorText(error)}`);
      }
    },
    [client, refreshChanges, refreshTree],
  );

  // 打开文件内容
  const openFile = useCallback(
    async (
      node: FileNode,
      setNotice: (msg: string) => void,
    ): Promise<{ path: string; content: string } | null> => {
      const target = workspaceRef.current;
      if (!target || node.kind !== "file") return null;
      try {
        const result = await client.request("file.read", {
          workspace_id: target.workspace_id,
          path: node.path,
        });
        return { path: node.path, content: String(result.content ?? "") };
      } catch (error) {
        setNotice(`无法读取文件：${errorText(error)}`);
        return null;
      }
    },
    [client],
  );

  // 获取 diff
  const getDiff = useCallback(
    async (change: Change, setNotice: (msg: string) => void): Promise<string | null> => {
      const target = workspaceRef.current;
      if (!target) return null;
      try {
        const result = await client.request("change.diff", {
          workspace_id: target.workspace_id,
          path: change.path,
        });
        return String(result.diff ?? "");
      } catch (error) {
        setNotice(`无法读取 Diff：${errorText(error)}`);
        return null;
      }
    },
    [client],
  );

  // 撤销变更
  const revertChange = useCallback(
    async (
      change: Change,
      setNotice: (msg: string) => void,
    ): Promise<boolean> => {
      const target = workspaceRef.current;
      if (!target || !change.agent_owned || !change.run_id) return false;
      try {
        const result = await client.request("change.revert", {
          workspace_id: target.workspace_id,
          run_id: change.run_id,
          paths: [change.path],
          confirm: "revert",
        });
        const reverted = (result.reverted_paths as string[]) ?? [];
        const blocked = result.blocked_paths as Record<string, string> | undefined;
        if (reverted.length) {
          setNotice(`已恢复 ${reverted.join("、")} 到本轮 Agent 运行前的内容。`);
        } else {
          setNotice(
            `未执行覆盖：${Object.values(blocked ?? {})[0] ?? "文件不再满足安全回退条件"}`,
          );
        }
        await refreshChanges(target, change.run_id);
        return true;
      } catch (error) {
        setNotice(`撤销失败：${errorText(error)}`);
        return false;
      }
    },
    [client, refreshChanges],
  );

  // 获取工作区诊断信息
  const getWorkspaceStatus = useCallback(async () => {
    const target = workspaceRef.current;
    if (!target) return null;
    return client.request("workspace.status", { workspace_id: target.workspace_id });
  }, [client]);

  return {
    workspace,
    workspaces,
    changes,
    treeNodes,
    workspaceRef,
    workspacesRef,
    setWorkspace,
    setWorkspaces,
    setChanges,
    refreshChanges,
    refreshTree,
    chooseWorkspace,
    openFile,
    getDiff,
    revertChange,
    getWorkspaceStatus,
  };
}
