import { ShieldCheck } from "lucide-react";
import type { Permission } from "../../types";

type PermissionBarProps = {
  permission: Permission;
  onDenyOnce: () => void;
  onAllowOnce: () => void;
  onAlwaysAllow: () => void;
};

/** 权限审批栏：底部固定的工具调用确认条 */
export function PermissionBar({
  permission,
  onDenyOnce,
  onAllowOnce,
  onAlwaysAllow,
}: PermissionBarProps) {
  return (
    <section className="permission-bar">
      <div className="permission-copy">
        <ShieldCheck size={18} />
        <div>
          <b>需要你的确认：{permission.tool_name}</b>
          <span>{JSON.stringify(permission.params)}</span>
        </div>
      </div>
      <div className="permission-actions">
        <button onClick={onDenyOnce}>拒绝</button>
        <button onClick={onAllowOnce}>允许一次</button>
        <button className="always" onClick={onAlwaysAllow}>
          始终允许
        </button>
      </div>
    </section>
  );
}
