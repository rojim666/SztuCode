import { X } from "lucide-react";
import type { ProviderStatus, RuntimeSettings } from "../../types";
import { modeLabel, modeDescription } from "../../types";

type SettingsDialogProps = {
  open: boolean;
  loading: boolean;
  runtimeSettings: RuntimeSettings | null;
  providerStatus: ProviderStatus | null;
  mode: string;
  modelDraft: string;
  onClose: () => void;
  onModelDraftChange: (value: string) => void;
  onModelDraftBlur: () => void;
  onProviderChange: (provider: string) => void;
  onPermissionModeChange: (mode: string) => void;
};

const MODES = ["normal", "plan", "accept_edits", "auto"] as const;

/** 设置对话框：Provider 选择、模型配置、执行策略、MCP/Skills */
export function SettingsDialog({
  open,
  loading,
  runtimeSettings,
  providerStatus,
  mode,
  modelDraft,
  onClose,
  onModelDraftChange,
  onModelDraftBlur,
  onProviderChange,
  onPermissionModeChange,
}: SettingsDialogProps) {
  if (!open) return null;

  return (
    <section
      className="settings-drawer"
      role="dialog"
      aria-modal="true"
      aria-label="运行设置"
    >
      <div className="settings-sheet settings-sheet-wide">
        <header>
          <div>
            <span className="eyebrow">本地运行配置</span>
            <h2>设置与连接</h2>
          </div>
          <button onClick={onClose} aria-label="关闭设置">
            <X size={18} />
          </button>
        </header>

        {loading ? (
          <div className="diagnostics-empty">正在读取运行时配置…</div>
        ) : (
          <div className="settings-sections">
            {/* 模型 Provider */}
            <section className="settings-section">
              <header>
                <span>模型 Provider</span>
                <i className={providerStatus?.ready_for_next_run ? "ok" : "warn"} />
              </header>
              <div className="setting-grid">
                <label>
                  服务
                  <select
                    value={runtimeSettings?.provider ?? "anthropic"}
                    onChange={(event) => onProviderChange(event.target.value)}
                  >
                    <option value="anthropic">Anthropic</option>
                    <option value="openai">OpenAI 兼容</option>
                  </select>
                </label>
                <label>
                  模型
                  <input
                    value={modelDraft}
                    onChange={(event) => onModelDraftChange(event.target.value)}
                    onBlur={onModelDraftBlur}
                  />
                </label>
              </div>
              <p>
                {providerStatus?.api_key_configured
                  ? "凭据已配置；修改将在下一轮任务生效。"
                  : "未发现当前 Provider 的 API Key；可查看本地环境变量后重试。"}
                {providerStatus?.custom_endpoint_configured
                  ? " 使用自定义端点。"
                  : ""}
              </p>
            </section>

            {/* 执行策略 */}
            <section className="settings-section">
              <header>
                <span>执行策略</span>
                <small>高风险操作仍会明确审批</small>
              </header>
              <div className="policy-list">
                {MODES.map((item) => (
                  <button
                    className={mode === item ? "selected" : ""}
                    key={item}
                    onClick={() => onPermissionModeChange(item)}
                  >
                    <i />
                    <div>
                      <b>{modeLabel(item)}</b>
                      <span>{modeDescription(item)}</span>
                    </div>
                  </button>
                ))}
              </div>
            </section>

            {/* MCP 与 Skills */}
            <section className="settings-section integration-section">
              <header>
                <span>MCP 与 Skills</span>
                <small>{providerStatus?.skills.length ?? 0} 个 Skills</small>
              </header>
              {providerStatus?.mcp_servers.length ? (
                <div className="integration-list">
                  {providerStatus.mcp_servers.map((server) => (
                    <div key={server.name}>
                      <i className={server.status === "connected" ? "ok" : "warn"} />
                      <b>{server.name}</b>
                      <span>
                        {server.status === "connected"
                          ? `${server.tool_count} 个工具可用`
                          : "当前不可用"}
                      </span>
                      <em>{server.transport}</em>
                    </div>
                  ))}
                </div>
              ) : (
                <p>
                  没有配置 MCP 服务。Skills 与 Provider 状态来自本地 daemon，不会上传凭据。
                </p>
              )}
              <div className="skill-strip">
                {providerStatus?.skills.slice(0, 6).map((skill) => (
                  <span key={skill.name} title={skill.description}>
                    #{skill.name}
                  </span>
                ))}
              </div>
            </section>
          </div>
        )}
      </div>
    </section>
  );
}
