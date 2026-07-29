import { useCallback, useState } from "react";
import { IpcClient } from "../lib/ipc";
import type { RuntimeSettings, ProviderStatus, Diagnostics } from "../types";
import { errorText } from "../types";

/** 运行时设置与 Provider 状态 */
export function useSettings(client: IpcClient) {
  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettings | null>(null);
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);
  const [modelDraft, setModelDraft] = useState("");
  const [settingsLoading, setSettingsLoading] = useState(false);

  // 加载设置
  const loadSettings = useCallback(async () => {
    setSettingsLoading(true);
    try {
      const [settingsResult, providerResult] = await Promise.all([
        client.request("settings.get"),
        client.request("provider.status"),
      ]);
      const settings = settingsResult.settings as RuntimeSettings;
      setRuntimeSettings(settings);
      setModelDraft(settings.model);
      setProviderStatus(providerResult as unknown as ProviderStatus);
      return { settings, providerResult: providerResult as unknown as ProviderStatus };
    } catch (error) {
      console.error(`读取设置失败：${errorText(error)}`);
      return null;
    } finally {
      setSettingsLoading(false);
    }
  }, [client]);

  // 更新运行时设置
  const updateRuntimeSettings = useCallback(
    async (update: Record<string, string>, setNotice: (msg: string) => void) => {
      try {
        const result = await client.request("settings.update", update);
        const settings = result.settings as RuntimeSettings;
        setRuntimeSettings(settings);
        setModelDraft(settings.model);
        setNotice("设置已保存，将在下一轮 Agent 任务生效。");
        await loadSettings();
      } catch (error) {
        setNotice(`更新设置失败：${errorText(error)}`);
      }
    },
    [client, loadSettings],
  );

  // 获取诊断信息
  const getDiagnostics = useCallback(
    async (
      getWorkspaceStatus: () => Promise<Record<string, unknown> | null>,
    ): Promise<Diagnostics | null> => {
      try {
        const ping = await client.request("core.ping", { client: "sztucode-desktop" });
        const status = await getWorkspaceStatus();
        return {
          version: String(ping.server_version ?? "unknown"),
          uptime: `${Math.max(0, Math.round(Number(ping.uptime_ms ?? 0) / 1000))} s`,
          branch: String(status?.branch ?? "—"),
          changes: Number(status?.changed_file_count ?? 0),
          repository: Boolean(status?.is_git_repository),
        };
      } catch {
        return null;
      }
    },
    [client],
  );

  return {
    runtimeSettings,
    providerStatus,
    modelDraft,
    settingsLoading,
    setModelDraft,
    loadSettings,
    updateRuntimeSettings,
    getDiagnostics,
  };
}
