export function officeTaskState(sessionStatus: string, operationStatus?: string): string {
  if (operationStatus === "unknown") return "结果未知";
  if (operationStatus === "failed") return "失败";
  if (operationStatus === "succeeded") return "完成";
  if (sessionStatus === "waiting_for_input") return "等待用户";
  if (sessionStatus === "active" || operationStatus === "running") return "运行中";
  if (sessionStatus === "closed") return "完成";
  return "未执行";
}
