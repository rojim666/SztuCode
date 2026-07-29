import { useCallback, useState } from "react";
import { IpcClient } from "../lib/ipc";
import type { Permission } from "../types";
import { modeLabel, errorText } from "../types";

/** 权限管理（审批请求、模式切换、决策响应） */
export function usePermissions(client: IpcClient) {
  const [permission, setPermission] = useState<Permission | null>(null);
  const [mode, setMode] = useState("normal");

  // 响应权限请求
  const decide = useCallback(
    async (decision: string, setNotice: (msg: string) => void) => {
      if (!permission) return;
      try {
        await client.request("permission.respond", {
          tool_use_id: permission.tool_use_id,
          decision,
        });
        setPermission(null);
      } catch (error) {
        setNotice(`审批未送达：${errorText(error)}`);
      }
    },
    [client, permission],
  );

  // 切换权限模式
  const setPermissionMode = useCallback(
    async (nextMode: string, setNotice: (msg: string) => void) => {
      try {
        const result = await client.request("permission.set_mode", { mode: nextMode });
        if (!result.ok) throw new Error(String(result.error ?? "权限策略未更新"));
        const resolvedMode = String(result.mode ?? nextMode);
        setMode(resolvedMode);
        setNotice(`已切换为${modeLabel(resolvedMode)}。`);
      } catch (error) {
        setNotice(`更新权限策略失败：${errorText(error)}`);
      }
    },
    [client],
  );

  return { permission, mode, setPermission, setMode, decide, setPermissionMode };
}
