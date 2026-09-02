import type { zhCN } from "./zh-CN";
import { app } from "./en-US/app";
import { chat } from "./en-US/chat";
import { common } from "./en-US/common";
import { composer } from "./en-US/composer";
import { git } from "./en-US/git";
import { inspector } from "./en-US/inspector";
import { model } from "./en-US/model";
import { palette } from "./en-US/palette";
import { questions } from "./en-US/questions";
import { session } from "./en-US/session";
import { settings } from "./en-US/settings";
import { skills } from "./en-US/skills";
import { splash } from "./en-US/splash";
import { timeline } from "./en-US/timeline";
import { tray } from "./en-US/tray";
import { workflow } from "./en-US/workflow";

/** en-US 语言包必须与 zh-CN 结构完全一致,由 TypeScript 编译期校验。 */
export const enUS: typeof zhCN = {
  common,
  app,
  settings,
  model,
  timeline,
  inspector,
  git,
  workflow,
  chat,
  skills,
  palette,
  composer,
  questions,
  session,
  splash,
  tray,
};
