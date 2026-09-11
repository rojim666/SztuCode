<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  name: string;
  size?: number;
}>();

const size = computed(() => props.size || 24);

// 技能图标映射 - 使用SVG内部HTML，一次性初始化
const skillIcons: Record<string, { bg: string; svg: string }> = {};

function registerIcon(name: string, bg: string, inner: string) {
  skillIcons[name] = { 
    bg, 
    svg: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" width="100%" height="100%">${inner}</svg>` 
  };
}

// ========== 核心技能 ==========
registerIcon("frontend-design", "#1683EF", `<path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-5l-3 3v-3H6a2 2 0 0 1-2-2V6z" fill="#4A9EFF"/><path d="M6 4a2 2 0 0 0-2 2v1h16V6a2 2 0 0 0-2-2H6z" fill="#1683EF"/><path d="M17 9l-4 3-4-3M9 8l-2 2 2 2M15 8l2 2-2 2" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("uicraft", "#DB2777", `<path d="M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-5l-3 3v-3H6a2 2 0 0 1-2-2V6z" fill="#F472B6"/><path d="M6 4a2 2 0 0 0-2 2v1h16V6a2 2 0 0 0-2-2H6z" fill="#DB2777"/><rect x="7" y="9" width="4" height="4" rx="1" fill="white" opacity="0.9"/><circle cx="15" cy="11" r="2" fill="white" opacity="0.7"/>`);
registerIcon("find-skills", "#7867D9", `<circle cx="11" cy="11" r="7" fill="#A89CF0"/><circle cx="11" cy="11" r="5" fill="#7867D9"/><path d="M8 11h6M11 8v6" stroke="white" stroke-width="1.5" stroke-linecap="round"/><path d="M16.5 16.5L21 21" stroke="#7867D9" stroke-width="2.5" stroke-linecap="round"/>`);
registerIcon("review-agent", "#1D8F6F", `<path d="M9 3h6l1 2h4a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h4l1-2z" fill="#3CB893"/><path d="M4 7h16v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7z" fill="#1D8F6F"/><path d="M8 12l2.5 2.5L16 10" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("review", "#2563EB", `<circle cx="12" cy="12" r="9" fill="#3B82F6"/><path d="M8 12l2 2 4-4" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("review-bugbot", "#E53935", `<circle cx="12" cy="12" r="9" fill="#EF5350"/><circle cx="9" cy="10" r="1.5" fill="white"/><circle cx="15" cy="10" r="1.5" fill="white"/><path d="M8 15c1.5 1.5 6.5 1.5 8 0" stroke="white" stroke-width="1.5" stroke-linecap="round" fill="none"/>`);
registerIcon("review-security", "#43A047", `<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="#66BB6A"/><path d="M9 12l2 2 4-4" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("presentations", "#E85D75", `<rect x="3" y="4" width="18" height="12" rx="2" fill="#FF8A9E"/><rect x="3" y="4" width="18" height="3" rx="2" fill="#E85D75"/><path d="M8 20l4-4 4 4M12 16v4" stroke="#E85D75" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/><rect x="7" y="9" width="3" height="4" rx="0.5" fill="white" opacity="0.9"/><rect x="11" y="7" width="3" height="6" rx="0.5" fill="white" opacity="0.7"/>`);
registerIcon("slides", "#E85D75", `<rect x="3" y="4" width="18" height="12" rx="2" fill="#FF8A9E"/><rect x="3" y="4" width="18" height="3" rx="2" fill="#E85D75"/><path d="M8 20l4-4 4 4M12 16v4" stroke="#E85D75" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("html-deck", "#E44D26", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#F16529"/><path d="M8 8l-1 8h10l-1-8H8z" fill="white" opacity="0.9"/><path d="M9 11h6l-.5 4H10l-.25-2h3.5" fill="#E44D26"/>`);
registerIcon("pdf", "#D34835", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#FF6B57"/><path d="M15 2v5h5" fill="#D34835"/><text x="12" y="16" text-anchor="middle" fill="white" font-size="7" font-weight="bold" font-family="Arial">PDF</text>`);
registerIcon("pdf-monster", "#7C3AED", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#A78BFA"/><path d="M15 2v5h5" fill="#7C3AED"/><circle cx="9" cy="13" r="1.5" fill="white"/><circle cx="15" cy="13" r="1.5" fill="white"/><path d="M8 16c1.5 1.5 6.5 1.5 8 0" stroke="white" stroke-width="1.5" stroke-linecap="round" fill="none"/>`);
registerIcon("imagegen", "#B763D9", `<rect x="3" y="4" width="18" height="16" rx="2" fill="#D89CF0"/><rect x="3" y="4" width="18" height="5" rx="2" fill="#B763D9"/><circle cx="8.5" cy="12" r="2" fill="#FFD700"/><path d="M5 18l5-5 4 4 3-3 4 4" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("imagen", "#B763D9", `<rect x="3" y="4" width="18" height="16" rx="2" fill="#D89CF0"/><rect x="3" y="4" width="18" height="5" rx="2" fill="#B763D9"/><circle cx="8.5" cy="12" r="2" fill="#FFD700"/><path d="M5 18l5-5 4 4 3-3 4 4" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("visualize", "#2E9E5C", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#6BC48B"/><rect x="6" y="13" width="3" height="6" rx="0.5" fill="white"/><rect x="10.5" y="9" width="3" height="10" rx="0.5" fill="white" opacity="0.9"/><rect x="15" y="5" width="3" height="14" rx="0.5" fill="white" opacity="0.8"/>`);
registerIcon("openai-docs", "#10A37F", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#10A37F"/><path d="M15 2v5h5" fill="#0D8A6C"/><circle cx="12" cy="12" r="3" fill="white"/><path d="M12 9v6M9 12h6" stroke="#10A37F" stroke-width="1.5" stroke-linecap="round" fill="none"/>`);
registerIcon("documents", "#2B5797", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#4A87D0"/><path d="M15 2v5h5" fill="#2B5797"/><rect x="8" y="11" width="8" height="1.5" rx="0.5" fill="white" opacity="0.9"/><rect x="8" y="14" width="6" height="1.5" rx="0.5" fill="white" opacity="0.7"/>`);
registerIcon("doc", "#2B5797", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#4A87D0"/><path d="M15 2v5h5" fill="#2B5797"/><text x="12" y="16" text-anchor="middle" fill="white" font-size="8" font-weight="bold" font-family="Arial">W</text>`);
registerIcon("docx", "#2B5797", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#4A87D0"/><path d="M15 2v5h5" fill="#2B5797"/><text x="12" y="16" text-anchor="middle" fill="white" font-size="7" font-weight="bold" font-family="Arial">DOC</text>`);
registerIcon("word", "#2B5797", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#4A87D0"/><path d="M15 2v5h5" fill="#2B5797"/><text x="12" y="16" text-anchor="middle" fill="white" font-size="8" font-weight="bold" font-family="Arial">W</text>`);
registerIcon("html-report", "#1976D2", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#42A5F5"/><rect x="6" y="8" width="12" height="2" rx="0.5" fill="white" opacity="0.9"/><rect x="6" y="12" width="8" height="2" rx="0.5" fill="white" opacity="0.7"/><rect x="6" y="16" width="10" height="2" rx="0.5" fill="white" opacity="0.7"/>`);

// ========== 办公软件 ==========
registerIcon("excel-live-control", "#217346", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#3D9964"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18" stroke="white" stroke-width="0.8" opacity="0.5" fill="none"/><rect x="3" y="3" width="18" height="6" rx="2" fill="#217346" opacity="0.3"/>`);
registerIcon("xlsx", "#217346", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#3D9964"/><path d="M15 2v5h5" fill="#217346"/><text x="12" y="16" text-anchor="middle" fill="white" font-size="7" font-weight="bold" font-family="Arial">XLS</text>`);
registerIcon("excel", "#217346", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#3D9964"/><path d="M15 2v5h5" fill="#217346"/><text x="12" y="16" text-anchor="middle" fill="white" font-size="8" font-weight="bold" font-family="Arial">X</text>`);
registerIcon("spreadsheet", "#A17200", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#D4A017"/><path d="M3 8h18M3 13h18M3 18h18M8 3v18M13 3v18" stroke="white" stroke-width="0.8" opacity="0.4" fill="none"/>`);
registerIcon("spreadsheets", "#A17200", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#D4A017"/><path d="M3 8h18M3 13h18M3 18h18M8 3v18M13 3v18" stroke="white" stroke-width="0.8" opacity="0.4" fill="none"/>`);
registerIcon("pptx", "#D24726", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#E86B50"/><path d="M15 2v5h5" fill="#D24726"/><text x="12" y="16" text-anchor="middle" fill="white" font-size="8" font-weight="bold" font-family="Arial">P</text>`);
registerIcon("jingmei-ppt", "#0D9488", `<rect x="3" y="4" width="18" height="12" rx="2" fill="#14B8A6"/><rect x="3" y="4" width="18" height="3" rx="2" fill="#0D9488"/><path d="M8 20l4-4 4 4M12 16v4" stroke="#0D9488" stroke-width="2" stroke-linecap="round" fill="none"/><circle cx="16" cy="9" r="2" fill="#FCD34D"/><path d="M6 15l4-4 3 3 5-5" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.9" fill="none"/>`);

// ========== 创作工具 ==========
registerIcon("skill-creator", "#E5921A", `<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" fill="#FFB84D"/>`);
registerIcon("create-skill", "#E5921A", `<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" fill="#FFB84D"/>`);
registerIcon("plugin-creator", "#C44D7E", `<path d="M12 2l3 3h4v4l3 3-3 3v4h-4l-3 3-3-3H5v-4l-3-3 3-3V5h4l3-3z" fill="#E87AA8"/><circle cx="12" cy="12" r="3" fill="white"/><path d="M12 9v6M9 12h6" stroke="#C44D7E" stroke-width="1.5" stroke-linecap="round" fill="none"/>`);
registerIcon("plan", "#307BC4", `<rect x="4" y="3" width="16" height="18" rx="2" fill="#5BA3E6"/><rect x="4" y="3" width="16" height="5" rx="2" fill="#307BC4"/><rect x="7" y="10" width="10" height="1.5" rx="0.5" fill="white" opacity="0.9"/><rect x="7" y="13" width="7" height="1.5" rx="0.5" fill="white" opacity="0.7"/><circle cx="17" cy="17" r="2" fill="#FFD700"/>`);
registerIcon("edits", "#8B6BC4", `<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" fill="#B8A0E8"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" fill="#8B6BC4"/>`);
registerIcon("auto", "#D36B44", `<circle cx="12" cy="12" r="9" fill="#FF9A76"/><circle cx="12" cy="12" r="7" fill="#D36B44"/><path d="M12 7v5l3 2" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("research-guide", "#00897B", `<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" fill="#4DB6AC"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" fill="#00897B"/><path d="M8 7h8M8 11h5M8 15h6" stroke="white" stroke-width="1.5" stroke-linecap="round" opacity="0.8" fill="none"/>`);
registerIcon("industry-research", "#0D9488", `<circle cx="12" cy="12" r="9" fill="#14B8A6"/><path d="M3 12h18M12 3v18" stroke="white" stroke-width="1.5" opacity="0.4" fill="none"/><circle cx="12" cy="12" r="4" fill="none" stroke="white" stroke-width="1.5" opacity="0.6"/>`);
registerIcon("doc-writing-guide", "#7B1FA2", `<path d="M12 2l3 3h4v4l3 3-3 3v4h-4l-3 3-3-3H5v-4l-3-3 3-3V5h4l3-3z" fill="#BA68C8"/><path d="M9 12h6M12 9v6" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("canvas", "#F57C00", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#FFB74D"/><circle cx="8" cy="9" r="2" fill="#FF5722"/><rect x="12" y="7" width="6" height="2" rx="0.5" fill="white" opacity="0.8"/><rect x="8" y="13" width="10" height="2" rx="0.5" fill="white" opacity="0.7"/>`);
registerIcon("automate", "#455A64", `<rect x="4" y="4" width="16" height="16" rx="2" fill="#78909C"/><path d="M9 9l3-3 3 3M15 15l-3 3-3-3" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/><circle cx="12" cy="12" r="2" fill="white"/>`);
registerIcon("loop", "#00ACC1", `<path d="M17 2l4 4-4 4M7 22l-4-4 4-4" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/><path d="M3 11v-1a4 4 0 0 1 4-4h14M21 13v1a4 4 0 0 1-4 4H3" stroke="#00ACC1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("share", "#0288D1", `<circle cx="18" cy="5" r="3" fill="#29B6F6"/><circle cx="6" cy="12" r="3" fill="#0288D1"/><circle cx="18" cy="19" r="3" fill="#29B6F6"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4" stroke="#0288D1" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("feedback", "#FBC02D", `<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" fill="#FFD54F"/>`);
registerIcon("create-rule", "#5D4037", `<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" fill="#8D6E63"/><path d="M14 2v6h6" fill="#5D4037"/><path d="M9 13l2 2 4-4" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("create-hook", "#689F38", `<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" fill="#9CCC65"/><path d="M13.73 21a2 2 0 0 1-3.46 0" stroke="#689F38" stroke-width="2" stroke-linecap="round" fill="none"/><circle cx="18" cy="4" r="2" fill="#FF5722"/>`);
registerIcon("new-repo", "#24292E", `<path d="M12 2C6.48 2 2 6.48 2 12c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.87 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0 0 12 2z" fill="#24292E"/>`);
registerIcon("git-commit", "#F05032", `<circle cx="12" cy="12" r="4" fill="#F05032"/><path d="M1 11h5v2H1M18 11h5v-2h-5" stroke="#F05032" stroke-width="2" stroke-linecap="round" fill="none"/><circle cx="12" cy="12" r="1.5" fill="white"/>`);
registerIcon("statusline", "#546E7A", `<rect x="2" y="9" width="20" height="6" rx="1" fill="#78909C"/><rect x="2" y="9" width="8" height="6" rx="1" fill="#4FC3F7"/>`);
registerIcon("autopilot", "#7C4DFF", `<circle cx="12" cy="12" r="9" fill="#B388FF"/><path d="M8 12l3 3 5-5" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("split-to-prs", "#0097A7", `<circle cx="6" cy="6" r="2" fill="#26C6DA"/><circle cx="6" cy="18" r="2" fill="#26C6DA"/><circle cx="18" cy="12" r="2" fill="#0097A7"/><path d="M6 8v8M8 12h8M14 9l3 3-3 3" stroke="#0097A7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("update-cli-config", "#6D4C41", `<circle cx="12" cy="12" r="3" fill="#A1887F"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" fill="none" stroke="#6D4C41" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>`);
registerIcon("update-cursor-settings", "#37474F", `<path d="M5 3l14 8-6 2-2 6-6-16z" fill="#78909C"/><path d="M13 13l6 8" stroke="#37474F" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("origin", "#24292E", `<path d="M12 2C6.48 2 2 6.48 2 12c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.87 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0 0 12 2z" fill="#24292E"/>`);
registerIcon("sdk", "#5C4EE5", `<path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#5C4EE5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);

// ========== 系统/自动化 ==========
registerIcon("computer-use", "#D97706", `<rect x="2" y="4" width="20" height="14" rx="2" fill="#F59E0B"/><path d="M8 21h8M12 18v3" stroke="#D97706" stroke-width="2" stroke-linecap="round" fill="none"/><rect x="5" y="7" width="14" height="8" rx="1" fill="white" opacity="0.9"/>`);
registerIcon("control-chrome", "#1A73E8", `<circle cx="12" cy="12" r="9" fill="#4285F4"/><circle cx="12" cy="12" r="3" fill="white"/><path d="M12 12l7-7M12 12l-6 3.5M12 12v9" stroke="#EA4335" stroke-width="2.5" stroke-linecap="round" fill="none"/><path d="M12 12l-7-4" stroke="#FBBC05" stroke-width="2.5" stroke-linecap="round" fill="none"/><path d="M12 12l3.5 7" stroke="#34A853" stroke-width="2.5" stroke-linecap="round" fill="none"/>`);
registerIcon("control-in-app-browser", "#0D9488", `<rect x="3" y="4" width="18" height="16" rx="2" fill="#14B8A6"/><rect x="3" y="4" width="18" height="4" rx="2" fill="#0D9488"/><circle cx="6" cy="6" r="0.8" fill="#EF4444"/><circle cx="8.5" cy="6" r="0.8" fill="#F59E0B"/><circle cx="11" cy="6" r="0.8" fill="#10B981"/>`);
registerIcon("github", "#24292E", `<path d="M12 2C6.48 2 2 6.48 2 12c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.87 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0 0 12 2z" fill="#24292E"/>`);
registerIcon("gh-address-comments", "#6B46C1", `<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" fill="#9F7AEA"/><path d="M9 10h6M9 13h4" stroke="white" stroke-width="1.5" stroke-linecap="round" fill="none"/>`);
registerIcon("gh-fix-ci", "#DC2626", `<path d="M9 11H7l3-7 3 7h-2l-2 7-2-7z" fill="#FCA5A5"/><circle cx="12" cy="12" r="9" fill="none" stroke="#DC2626" stroke-width="2"/><path d="M15 9l-6 6M9 9l6 6" stroke="#DC2626" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("init", "#0891B2", `<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" fill="#22D3EE"/>`);
registerIcon("linear", "#5E6AD2", `<circle cx="12" cy="12" r="9" fill="#818CF8"/><path d="M11 17l-4-4 1.5-1.5L11 14l5.5-5.5L18 10l-7 7z" fill="white"/>`);
registerIcon("orchestrate", "#1F2937", `<circle cx="12" cy="5" r="2" fill="#6B7280"/><circle cx="5" cy="19" r="2" fill="#6B7280"/><circle cx="19" cy="19" r="2" fill="#6B7280"/><path d="M12 7v4M8 17l3-4M16 17l-3-4" stroke="#1F2937" stroke-width="2" stroke-linecap="round" fill="none"/><circle cx="12" cy="12" r="2" fill="#374151"/>`);
registerIcon("skill-installer", "#059669", `<path d="M20 6h-8l-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2z" fill="#34D399"/><path d="M12 11v6M9 14l3 3 3-3" stroke="#059669" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("summarize", "#B45309", `<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" fill="#F59E0B"/><path d="M14 2v6h6" fill="#B45309"/><path d="M8 13h8M8 16h5M8 10h8" stroke="white" stroke-width="1.5" stroke-linecap="round" opacity="0.8" fill="none"/>`);
registerIcon("yeet", "#7C3AED", `<circle cx="18" cy="6" r="2" fill="#A78BFA"/><circle cx="6" cy="18" r="2" fill="#A78BFA"/><path d="M6 16V8a4 4 0 0 1 4-4h4" stroke="#7C3AED" stroke-width="2" stroke-linecap="round" fill="none"/><path d="M11 7l3-3-3-3" stroke="#7C3AED" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);

// ========== 浏览器控制 ==========
registerIcon("browser-control", "#EA580C", `<circle cx="12" cy="12" r="9" fill="#FB923C"/><circle cx="12" cy="12" r="5" fill="#EA580C"/><circle cx="12" cy="12" r="2" fill="white"/>`);
registerIcon("浏览器控制", "#EA580C", `<circle cx="12" cy="12" r="9" fill="#FB923C"/><circle cx="12" cy="12" r="5" fill="#EA580C"/><circle cx="12" cy="12" r="2" fill="white"/>`);

// ========== 原型制作 ==========
registerIcon("rapid-prototype-craft", "#7C3AED", `<rect x="3" y="4" width="18" height="14" rx="2" fill="#A78BFA"/><rect x="3" y="4" width="18" height="3" rx="2" fill="#7C3AED"/><circle cx="6" cy="5.5" r="0.6" fill="#EF4444"/><circle cx="8" cy="5.5" r="0.6" fill="#F59E0B"/><circle cx="10" cy="5.5" r="0.6" fill="#10B981"/><rect x="6" y="9" width="5" height="5" rx="1" fill="white" opacity="0.9"/><rect x="13" y="9" width="5" height="2" rx="0.5" fill="white" opacity="0.7"/>`);
registerIcon("prototype-craft", "#7C3AED", `<rect x="3" y="4" width="18" height="14" rx="2" fill="#A78BFA"/><rect x="3" y="4" width="18" height="3" rx="2" fill="#7C3AED"/><circle cx="6" cy="5.5" r="0.6" fill="#EF4444"/><circle cx="8" cy="5.5" r="0.6" fill="#F59E0B"/><circle cx="10" cy="5.5" r="0.6" fill="#10B981"/>`);

// ========== Runtype ==========
registerIcon("runtype", "#6366F1", `<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" fill="#818CF8"/>`);
registerIcon("runtype-build-product", "#6366F1", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#818CF8"/><path d="M8 16l2-8 4 8M9 13h6" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("runtype-admin", "#4F46E5", `<circle cx="12" cy="8" r="4" fill="#818CF8"/><path d="M4 20v-1a6 6 0 0 1 12 0v1" fill="#818CF8"/>`);
registerIcon("runtype-persona", "#8B5CF6", `<circle cx="9" cy="9" r="4" fill="#A78BFA"/><circle cx="16" cy="8" r="3" fill="#C4B5FD"/><path d="M3 20v-1a5 5 0 0 1 8-4" fill="#A78BFA"/>`);
registerIcon("runtype-templates", "#10B981", `<rect x="3" y="3" width="7" height="7" rx="1" fill="#34D399"/><rect x="14" y="3" width="7" height="7" rx="1" fill="#10B981"/><rect x="3" y="14" width="7" height="7" rx="1" fill="#059669"/><rect x="14" y="14" width="7" height="7" rx="1" fill="#047857"/>`);
registerIcon("runtype-sdk-marathon", "#0EA5E9", `<rect x="2" y="7" width="20" height="10" rx="2" fill="#38BDF8"/>`);

// ========== Dev Skills ==========
registerIcon("dev-auto", "#059669", `<circle cx="12" cy="12" r="9" fill="#10B981"/><path d="M12 7v5l3 2" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("dev-grill-docs", "#DC2626", `<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" fill="#FCA5A5"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" fill="#DC2626"/><path d="M9 7h6M9 11h6M9 15h4" stroke="white" stroke-width="1.5" stroke-linecap="round" fill="none"/>`);
registerIcon("dev-spec", "#DC2626", `<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" fill="#FCA5A5"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" fill="#DC2626"/>`);
registerIcon("dev-plan", "#2563EB", `<rect x="4" y="3" width="16" height="18" rx="2" fill="#3B82F6"/><rect x="4" y="3" width="16" height="5" rx="2" fill="#2563EB"/><path d="M7 11h10M7 14h7M7 17h5" stroke="white" stroke-width="1.5" stroke-linecap="round" opacity="0.8" fill="none"/>`);
registerIcon("dev-tdd", "#7C3AED", `<circle cx="12" cy="12" r="9" fill="#8B5CF6"/><path d="M9 12l2 2 4-4" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("dev-fix", "#DC2626", `<circle cx="12" cy="12" r="9" fill="#EF4444"/><path d="M15 9l-6 6M9 9l6 6" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("dev-verify", "#059669", `<circle cx="12" cy="12" r="9" fill="#10B981"/><path d="M8 12l3 3 5-5" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("dev-code-review", "#2563EB", `<circle cx="12" cy="12" r="9" fill="#3B82F6"/><path d="M9 9l-3 3 3 3M15 9l3 3-3 3" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("dev-commit-writer", "#F05032", `<circle cx="12" cy="12" r="4" fill="#F05032"/><path d="M1 11h5v2H1M18 11h5" stroke="#F05032" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("dev-finish", "#059669", `<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" fill="none" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M22 4L12 14.01l-3-3" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("dev-design-context", "#DB2777", `<path d="M12 2l3 3h4v4l3 3-3 3v4h-4l-3 3-3-3H5v-4l-3-3 3-3V5h4l3-3z" fill="#F472B6"/>`);

// ========== 视频/图片生成 ==========
registerIcon("seedance", "#7C3AED", `<rect x="2" y="6" width="15" height="12" rx="2" fill="#A78BFA"/><path d="M17 10l5-3v10l-5-3v-4z" fill="#7C3AED"/><circle cx="9.5" cy="12" r="3" fill="white" opacity="0.8"/>`);
registerIcon("seedream", "#EC4899", `<rect x="3" y="4" width="18" height="16" rx="2" fill="#F9A8D4"/><circle cx="8.5" cy="12" r="2" fill="#FCD34D"/><path d="M5 18l5-5 4 4 3-3 4 4" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);

// ========== Web开发 ==========
registerIcon("web-app-development", "#0EA5E9", `<rect x="3" y="4" width="18" height="14" rx="2" fill="#38BDF8"/><path d="M9 9l-2 2 2 2M15 9l2 2-2 2" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);

// ========== Lark 飞书系列 - 每个都有独特图标 ==========
registerIcon("lark-approval", "#3370FF", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#5C95FF"/><path d="M7 12l3 3 7-7" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("lark-calendar", "#3370FF", `<rect x="3" y="4" width="18" height="16" rx="2" fill="#5C95FF"/><rect x="3" y="4" width="18" height="4" rx="2" fill="#3370FF"/><path d="M8 2v4M16 2v4" stroke="white" stroke-width="1.5" stroke-linecap="round" fill="none"/><rect x="7" y="11" width="3" height="3" rx="0.5" fill="white" opacity="0.8"/>`);
registerIcon("lark-im", "#3370FF", `<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" fill="#5C95FF"/><circle cx="8.5" cy="10" r="1.5" fill="white"/><circle cx="12" cy="10" r="1.5" fill="white"/><circle cx="15.5" cy="10" r="1.5" fill="white"/>`);
registerIcon("lark-doc", "#3370FF", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#5C95FF"/><path d="M15 2v5h5" fill="#3370FF"/><rect x="8" y="11" width="8" height="1.5" rx="0.5" fill="white" opacity="0.9"/>`);
registerIcon("lark-sheets", "#3370FF", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#5C95FF"/><path d="M15 2v5h5" fill="#3370FF"/><path d="M8 11h8M8 14h8M11 11v8" stroke="white" stroke-width="1" opacity="0.5" fill="none"/>`);
registerIcon("lark-base", "#3370FF", `<rect x="3" y="3" width="8" height="8" rx="1" fill="#5C95FF"/><rect x="13" y="3" width="8" height="8" rx="1" fill="#7AADFF"/><rect x="3" y="13" width="8" height="8" rx="1" fill="#7AADFF"/><rect x="13" y="13" width="8" height="8" rx="1" fill="#5C95FF"/>`);
registerIcon("lark-drive", "#3370FF", `<path d="M12 2L2 22h20L12 2z" fill="#5C95FF"/><circle cx="12" cy="14" r="3" fill="white" opacity="0.9"/>`);
registerIcon("lark-task", "#3370FF", `<rect x="3" y="4" width="18" height="16" rx="2" fill="#5C95FF"/><rect x="3" y="4" width="18" height="4" rx="2" fill="#3370FF"/><circle cx="7" cy="12" r="1.5" fill="none" stroke="white" stroke-width="1.5"/><path d="M10 12h7" stroke="white" stroke-width="1.5" stroke-linecap="round" fill="none"/>`);
registerIcon("lark-vc", "#3370FF", `<rect x="2" y="6" width="15" height="12" rx="2" fill="#5C95FF"/><path d="M17 10l5-3v10l-5-3v-4z" fill="#3370FF"/>`);
registerIcon("lark-minutes", "#3370FF", `<circle cx="12" cy="12" r="9" fill="#5C95FF"/><path d="M12 6v6l4 2" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("lark-wiki", "#3370FF", `<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" fill="#7AADFF"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" fill="#5C95FF"/><circle cx="12" cy="10" r="3" fill="white"/>`);
registerIcon("lark-mail", "#3370FF", `<rect x="2" y="5" width="20" height="14" rx="2" fill="#5C95FF"/><path d="M3 7l9 6 9-6" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("lark-contact", "#3370FF", `<circle cx="12" cy="8" r="4" fill="white" opacity="0.9"/><path d="M4 20v-1a6 6 0 0 1 16 0v1" fill="#5C95FF"/>`);
registerIcon("lark-slides", "#3370FF", `<rect x="3" y="4" width="18" height="12" rx="2" fill="#5C95FF"/><rect x="3" y="4" width="18" height="3" rx="2" fill="#3370FF"/><path d="M8 20l4-4 4 4M12 16v4" stroke="#3370FF" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("lark-workflow-meeting-summary", "#3370FF", `<rect x="3" y="4" width="18" height="16" rx="2" fill="#5C95FF"/><path d="M7 9h10M7 12h7M7 15h8" stroke="white" stroke-width="1.5" stroke-linecap="round" opacity="0.8" fill="none"/>`);
registerIcon("lark-workflow-standup-report", "#3370FF", `<rect x="3" y="4" width="18" height="16" rx="2" fill="#5C95FF"/><rect x="6" y="8" width="5" height="10" rx="0.5" fill="white" opacity="0.7"/><rect x="13" y="11" width="5" height="7" rx="0.5" fill="white" opacity="0.5"/>`);
registerIcon("lark-okr", "#3370FF", `<circle cx="12" cy="12" r="8" fill="none" stroke="#5C95FF" stroke-width="3"/><circle cx="12" cy="12" r="4" fill="white"/><circle cx="12" cy="12" r="2" fill="#3370FF"/>`);
registerIcon("lark-attendance", "#3370FF", `<circle cx="12" cy="12" r="9" fill="#5C95FF"/><path d="M8 12l3 3 5-5" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("lark-shared", "#3370FF", `<circle cx="18" cy="5" r="2.5" fill="white" opacity="0.9"/><circle cx="6" cy="12" r="2.5" fill="white" opacity="0.9"/><circle cx="18" cy="19" r="2.5" fill="white" opacity="0.9"/><path d="M8.5 13l6 4.5M15.5 6.5l-6 4.5" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("lark-event", "#3370FF", `<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" fill="#5C95FF"/>`);
registerIcon("lark-markdown", "#3370FF", `<rect x="4" y="4" width="16" height="16" rx="1" fill="#5C95FF"/><path d="M7 15V9l3 3 3-3v6M15 9v6M17 13l-2 2-2-2" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("lark-note", "#3370FF", `<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z" fill="#5C95FF"/><path d="M14 2v6h6" fill="#3370FF"/>`);
registerIcon("lark-openapi-explorer", "#3370FF", `<circle cx="12" cy="12" r="9" fill="#5C95FF"/><path d="M3 12h18M12 3v18" stroke="white" stroke-width="1.5" opacity="0.4" fill="none"/>`);
registerIcon("lark-skill-maker", "#3370FF", `<path d="M12 2l3 3h4v4l3 3-3 3v4h-4l-3 3-3-3H5v-4l-3-3 3-3V5h4l3-3z" fill="#5C95FF"/><path d="M9 12h6M12 9v6" stroke="white" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("lark-whiteboard", "#3370FF", `<rect x="3" y="3" width="18" height="14" rx="1" fill="#5C95FF"/><path d="M8 21h8M12 17v4" stroke="#3370FF" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("lark", "#3370FF", `<rect x="3" y="4" width="18" height="16" rx="2" fill="#5C95FF"/><path d="M8 10l4 4 4-4" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);

// ========== Ardot 设计画布 ==========
registerIcon("ardot-design-core", "#7C3AED", `<rect x="3" y="4" width="18" height="16" rx="2" fill="#A78BFA"/><rect x="3" y="4" width="18" height="3" rx="2" fill="#7C3AED"/><rect x="6.5" y="10" width="5" height="6.5" rx="1" fill="white" opacity="0.92"/><rect x="13" y="10" width="4.5" height="3" rx="1" fill="white" opacity="0.68"/><rect x="13" y="14.5" width="4.5" height="2" rx="1" fill="white" opacity="0.5"/>`);
registerIcon("ardot-design-router", "#6D28D9", `<rect x="3" y="9.5" width="7" height="5" rx="1.5" fill="#A78BFA"/><path d="M10 12h3.5M13.5 12c1.5 0 1.5-4.4 3-4.4M13.5 12c1.5 0 1.5 4.4 3 4.4" stroke="#6D28D9" stroke-width="1.6" stroke-linecap="round" fill="none"/><rect x="16" y="5.4" width="5" height="4" rx="1" fill="#6D28D9"/><rect x="16" y="14.6" width="5" height="4" rx="1" fill="#6D28D9"/>`);
registerIcon("ardot-design-to-code", "#4F46E5", `<rect x="2.5" y="4.5" width="8" height="6" rx="1.5" fill="#A5B4FC"/><rect x="2.5" y="13.5" width="8" height="6" rx="1.5" fill="#A5B4FC"/><path d="M14.5 9l-2.5 3 2.5 3M18.5 9l2.5 3-2.5 3" stroke="#4F46E5" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("ardot-poster", "#DB2777", `<rect x="4" y="2.5" width="16" height="19" rx="2" fill="#F9A8D4"/><rect x="4" y="2.5" width="16" height="10" rx="2" fill="#DB2777"/><circle cx="8.5" cy="7" r="1.6" fill="#FCD34D"/><path d="M5.5 12l4-3.5 3 3 2.5-2 4 3.5" stroke="white" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" fill="none" opacity="0.85"/><rect x="7" y="15.5" width="10" height="1.6" rx="0.8" fill="#DB2777" opacity="0.8"/><rect x="7" y="18.5" width="6" height="1.6" rx="0.8" fill="#DB2777" opacity="0.5"/>`);
registerIcon("ardot-slides", "#E85D75", `<rect x="2.5" y="4" width="19" height="13" rx="2" fill="#FF8A9E"/><path d="M9 21h6M12 17v4" stroke="#E85D75" stroke-width="2" stroke-linecap="round" fill="none"/><rect x="5.5" y="7" width="7" height="2" rx="1" fill="white" opacity="0.95"/><rect x="5.5" y="10.5" width="5" height="1.6" rx="0.8" fill="white" opacity="0.7"/><circle cx="17.5" cy="10.5" r="2.6" fill="white" opacity="0.85"/>`);
registerIcon("ardot-ui-design", "#0284C7", `<rect x="2.5" y="3.5" width="19" height="17" rx="2" fill="#7DD3FC"/><rect x="2.5" y="3.5" width="19" height="3.5" rx="2" fill="#0284C7"/><circle cx="5.5" cy="5.2" r="0.9" fill="white" opacity="0.9"/><circle cx="8" cy="5.2" r="0.9" fill="white" opacity="0.7"/><rect x="5" y="9.5" width="6" height="8" rx="1" fill="white" opacity="0.9"/><rect x="13" y="9.5" width="6" height="3.4" rx="1" fill="white" opacity="0.75"/><rect x="13" y="14.2" width="6" height="3.3" rx="1" fill="white" opacity="0.6"/>`);
registerIcon("livestream-poster", "#F43F5E", `<rect x="2.5" y="6" width="13" height="12" rx="2" fill="#FDA4AF"/><path d="M15.5 11l6-3.5v9l-6-3.5v-2z" fill="#F43F5E"/><circle cx="9" cy="12" r="2.6" fill="white" opacity="0.9"/>`);
registerIcon("component-instance", "#8B5CF6", `<rect x="3.5" y="3.5" width="7" height="7" rx="1.5" fill="#C4B5FD"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" fill="#C4B5FD"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" fill="#C4B5FD"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" fill="#8B5CF6"/><path d="M8 8l8 8" stroke="white" stroke-width="1.5" stroke-linecap="round" opacity="0.85" fill="none"/>`);
registerIcon("design-variables", "#0EA5E9", `<rect x="3" y="5" width="18" height="14" rx="2" fill="#A5B4FC"/><rect x="3" y="5" width="18" height="4" rx="2" fill="#0EA5E9"/><text x="12" y="17.5" text-anchor="middle" fill="white" font-size="9" font-weight="bold" font-family="Arial">$</text>`);
registerIcon("shared-styles", "#9333EA", `<circle cx="9" cy="12" r="6" fill="#D8B4FE"/><circle cx="15" cy="12" r="6" fill="#9333EA" opacity="0.88"/><circle cx="12" cy="12" r="1.8" fill="white" opacity="0.9"/>`);

// ========== 内容与平台能力 ==========
registerIcon("3D模型与视频特效", "#7C3AED", `<path d="M12 2.5l8.5 4.8v9.4L12 21.5 3.5 16.7V7.3L12 2.5z" fill="#A78BFA"/><path d="M12 2.5l8.5 4.8L12 12 3.5 7.3 12 2.5z" fill="#C4B5FD"/><path d="M12 12v9.5M12 12L3.5 7.3M12 12l8.5-4.7" stroke="#7C3AED" stroke-width="1.1" opacity="0.7" fill="none"/>`);
registerIcon("buddy-multimodal-generation", "#7C3AED", `<path d="M12 2.5l8.5 4.8v9.4L12 21.5 3.5 16.7V7.3L12 2.5z" fill="#A78BFA"/><path d="M12 2.5l8.5 4.8L12 12 3.5 7.3 12 2.5z" fill="#C4B5FD"/><path d="M12 12v9.5M12 12L3.5 7.3M12 12l8.5-4.7" stroke="#7C3AED" stroke-width="1.1" opacity="0.7" fill="none"/>`);
registerIcon("资料库", "#0D9488", `<rect x="3" y="4" width="18" height="4" rx="1.5" fill="#5EEAD4"/><rect x="3" y="10" width="18" height="4" rx="1.5" fill="#2DD4BF"/><rect x="3" y="16" width="18" height="4" rx="1.5" fill="#0D9488"/><circle cx="7" cy="6" r="0.9" fill="white" opacity="0.9"/><circle cx="7" cy="12" r="0.9" fill="white" opacity="0.9"/><circle cx="7" cy="18" r="0.9" fill="white" opacity="0.9"/>`);
registerIcon("library", "#0D9488", `<rect x="3" y="4" width="18" height="4" rx="1.5" fill="#5EEAD4"/><rect x="3" y="10" width="18" height="4" rx="1.5" fill="#2DD4BF"/><rect x="3" y="16" width="18" height="4" rx="1.5" fill="#0D9488"/><circle cx="7" cy="6" r="0.9" fill="white" opacity="0.9"/><circle cx="7" cy="12" r="0.9" fill="white" opacity="0.9"/><circle cx="7" cy="18" r="0.9" fill="white" opacity="0.9"/>`);
registerIcon("发布为应用", "#4F46E5", `<circle cx="12" cy="12" r="9.5" fill="#A5B4FC"/><path d="M3.1 9.5h17.8M3.1 14.5h17.8" stroke="#4F46E5" stroke-width="1.2" opacity="0.75" fill="none"/><ellipse cx="12" cy="12" rx="4.2" ry="9.5" fill="none" stroke="#4F46E5" stroke-width="1.2" opacity="0.75"/><path d="M12 2.5v19" stroke="#4F46E5" stroke-width="1.2" opacity="0.5" fill="none"/>`);
registerIcon("sites", "#4F46E5", `<circle cx="12" cy="12" r="9.5" fill="#A5B4FC"/><path d="M3.1 9.5h17.8M3.1 14.5h17.8" stroke="#4F46E5" stroke-width="1.2" opacity="0.75" fill="none"/><ellipse cx="12" cy="12" rx="4.2" ry="9.5" fill="none" stroke="#4F46E5" stroke-width="1.2" opacity="0.75"/><path d="M12 2.5v19" stroke="#4F46E5" stroke-width="1.2" opacity="0.5" fill="none"/>`);
registerIcon("expert-manager", "#0F766E", `<circle cx="9.5" cy="8.5" r="4" fill="#5EEAD4"/><path d="M2.5 20.5c0-3.8 3.1-6.4 7-6.4s7 2.6 7 6.4z" fill="#0F766E"/><circle cx="18.5" cy="7" r="3.6" fill="#0F766E"/><path d="M16.9 7l1.1 1.1 2.1-2.1" stroke="white" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("geo-map-compliance-guard", "#15803D", `<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="#86EFAC"/><path d="M12 8.5a3 3 0 0 1 3 3c0 2-3 5-3 5s-3-3-3-5a3 3 0 0 1 3-3z" fill="#15803D"/><circle cx="12" cy="11.5" r="1" fill="white"/>`);
registerIcon("marketplace-skill-installer", "#059669", `<path d="M5 8h14l-1.2 12.4a1.6 1.6 0 0 1-1.6 1.5H7.8a1.6 1.6 0 0 1-1.6-1.5L5 8z" fill="#6EE7B7"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8" stroke="#059669" stroke-width="1.6" stroke-linecap="round" fill="none"/><path d="M12 11.5l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2z" fill="#059669"/>`);
registerIcon("recommend-connectors", "#0284C7", `<path d="M9 2.5v5M15 2.5v5" stroke="#0284C7" stroke-width="2" stroke-linecap="round" fill="none"/><path d="M6 8h12v3a6 6 0 0 1-12 0V8z" fill="#7DD3FC"/><path d="M12 17v4.5" stroke="#0284C7" stroke-width="2" stroke-linecap="round" fill="none"/>`);
registerIcon("recommend-experts", "#7C3AED", `<circle cx="11.5" cy="8" r="4" fill="#C4B5FD"/><path d="M4 21c0-4 3.4-6.8 7.5-6.8s7.5 2.8 7.5 6.8z" fill="#7C3AED"/><path d="M18.6 2.6l.9 1.8 2 .3-1.4 1.4.3 2-1.8-1-1.8 1 .3-2-1.4-1.4 2-.3.9-1.8z" fill="#FCD34D"/>`);
registerIcon("wb-finance-skill", "#B91C1C", `<rect x="3" y="12" width="3" height="7.5" rx="0.8" fill="#EF4444"/><rect x="8" y="7" width="3" height="9" rx="0.8" fill="#B91C1C"/><rect x="13" y="9.5" width="3" height="10" rx="0.8" fill="#EF4444"/><rect x="18" y="4" width="3" height="8" rx="0.8" fill="#B91C1C"/><path d="M4.5 9.5v2M9.5 4v2M14.5 7.5v2M19.5 2v2" stroke="#7F1D1D" stroke-width="1.2" stroke-linecap="round" fill="none"/>`);

// ========== 腾讯文档 / 本地办公 ==========
registerIcon("tencent-docs-routing", "#0052D9", `<path d="M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#7EA6F0"/><path d="M14 2v5h5" fill="#0052D9"/><path d="M6.5 9.5h3M6.5 13h4M6.5 16.5h8" stroke="white" stroke-width="1.2" stroke-linecap="round" opacity="0.9" fill="none"/><path d="M12.5 15l3 1.5-3 1.5" stroke="white" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("tencent-local-office-edit", "#0F766E", `<rect x="2.5" y="4" width="19" height="12" rx="2" fill="#5EEAD4"/><rect x="2.5" y="4" width="19" height="3.5" rx="2" fill="#0F766E"/><path d="M9 20h6M12 16v4" stroke="#0F766E" stroke-width="2" stroke-linecap="round" fill="none"/><rect x="6" y="10" width="12" height="4" rx="1" fill="white" opacity="0.9"/>`);
registerIcon("tencent-docs", "#0052D9", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#7EA6F0"/><path d="M15 2v5h5" fill="#0052D9"/><path d="M8 15.5c-1.7 0-3-1.2-3-2.7 0-1.4 1.2-2.6 2.7-2.7.4-1.6 1.9-2.8 3.7-2.8 2 0 3.6 1.4 3.8 3.2 1.4.1 2.5 1.3 2.5 2.7 0 1.5-1.2 2.7-2.7 2.7H8z" fill="white" opacity="0.92"/>`);
registerIcon("tencent-saas-docs", "#1E40AF", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#93B4F5"/><path d="M15 2v5h5" fill="#1E40AF"/><rect x="7" y="10.5" width="4" height="4" rx="1" fill="white" opacity="0.92"/><rect x="13" y="10.5" width="4" height="4" rx="1" fill="white" opacity="0.7"/><rect x="7" y="17" width="10" height="1.8" rx="0.9" fill="white" opacity="0.55"/>`);

// ========== tencent-docx 文档流水线 ==========
registerIcon("tencent-docx", "#2B5797", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#6E9BDB"/><path d="M15 2v5h5" fill="#2B5797"/><text x="12" y="17" text-anchor="middle" fill="white" font-size="8" font-weight="bold" font-family="Arial">W</text>`);
registerIcon("tdoc-orchestrator", "#2563EB", `<circle cx="12" cy="12" r="3.2" fill="#2563EB"/><circle cx="5" cy="6" r="2.2" fill="#93C5FD"/><circle cx="19" cy="6" r="2.2" fill="#93C5FD"/><circle cx="5" cy="18" r="2.2" fill="#93C5FD"/><circle cx="19" cy="18" r="2.2" fill="#93C5FD"/><path d="M7 7.5l3 2.5M17 7.5l-3 2.5M7 16.5l3-2.5M17 16.5l-3-2.5" stroke="#2563EB" stroke-width="1.5" stroke-linecap="round" fill="none"/>`);
registerIcon("brief-compose", "#2B5797", `<path d="M6 2.5h9l4.5 4.5v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4.5a2 2 0 0 1 2-2z" fill="#8FB3E8"/><path d="M15 2.5v4.5h4.5" fill="#2B5797"/><path d="M7 12h6M7 15.5h4" stroke="white" stroke-width="1.3" stroke-linecap="round" opacity="0.9" fill="none"/><path d="M16.5 14.5l3.5-3.5 1.5 1.5-3.5 3.5-2 .5.5-2z" fill="#FCD34D"/>`);
registerIcon("design-token", "#7C3AED", `<circle cx="12" cy="12" r="9.5" fill="#D8B4FE"/><circle cx="9" cy="9.5" r="2" fill="#7C3AED"/><circle cx="15" cy="9.5" r="2" fill="#0EA5E9"/><circle cx="9" cy="15.5" r="2" fill="#F59E0B"/><circle cx="15" cy="15.5" r="2" fill="#10B981"/>`);
registerIcon("doc-typeset", "#0D9488", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#5EEAD4"/><rect x="3" y="3" width="18" height="3" rx="2" fill="#0D9488"/><rect x="6" y="9" width="12" height="2" rx="1" fill="white" opacity="0.95"/><rect x="6" y="13" width="12" height="1.6" rx="0.8" fill="white" opacity="0.75"/><rect x="6" y="16.5" width="7" height="1.6" rx="0.8" fill="white" opacity="0.55"/>`);
registerIcon("format-extract", "#0F766E", `<path d="M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#5EEAD4"/><path d="M14 2v5h5" fill="#0F766E"/><path d="M8 12h5M13 12l-2-2M13 12l-2 2" stroke="#0F766E" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/><path d="M8 17h8" stroke="white" stroke-width="1.3" stroke-linecap="round" opacity="0.8" fill="none"/>`);
registerIcon("html-review", "#E11D48", `<rect x="2.5" y="3" width="14" height="18" rx="2" fill="#FDA4AF"/><path d="M6 8l-2 3 2 3M12 8l2 3-2 3" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/><circle cx="17" cy="16" r="4.4" fill="white"/><circle cx="17" cy="16" r="2.9" fill="#E11D48"/><path d="M15.7 16l1 1 1.7-1.8" stroke="white" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("html-to-docx", "#E34F26", `<rect x="2.5" y="4" width="7.5" height="16" rx="1.5" fill="#FCA5A5"/><rect x="14" y="4" width="7.5" height="16" rx="1.5" fill="#6E9BDB"/><path d="M5 9.5l-1.6 2.5L5 14.5M7.5 9.5l1.6 2.5-1.6 2.5" stroke="#E34F26" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/><path d="M16.5 10h3M16.5 13h3M16.5 16h2" stroke="white" stroke-width="1.2" stroke-linecap="round" opacity="0.9" fill="none"/><path d="M10.3 12h3.4M13.7 12l-1.4-1.4M13.7 12l-1.4 1.4" stroke="#2B5797" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("generate-fillable-contract-html", "#0E7490", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#7DD3FC"/><path d="M15 2v5h5" fill="#0E7490"/><path d="M7 10.5h4M7 14h4M7 17.5h3" stroke="white" stroke-width="1.3" stroke-linecap="round" stroke-dasharray="2 1.4" fill="none"/><path d="M12.5 19.4c1-1.7 2-2.5 3-1.5 1 1 2 .2 3-1.4" stroke="#0E7490" stroke-width="1.4" stroke-linecap="round" fill="none"/>`);

// ========== tencent-docx 写作专家 ==========
registerIcon("academic-paper-expert", "#1E3A8A", `<path d="M12 3l10 4.5-10 4.5L2 7.5 12 3z" fill="#93A9D8"/><path d="M6 10v4.6c0 1.7 2.7 3.1 6 3.1s6-1.4 6-3.1V10" fill="#1E3A8A"/><path d="M20.5 8.6v5.2" stroke="#1E3A8A" stroke-width="1.4" stroke-linecap="round" fill="none"/>`);
registerIcon("business-copy-expert", "#DB2777", `<path d="M4 9.5h4l8-4v13l-8-4H4a1.5 1.5 0 0 1-1.5-1.5v-2A1.5 1.5 0 0 1 4 9.5z" fill="#F9A8D4"/><path d="M16 7.5l4.5-2v13l-4.5-2" fill="#DB2777"/><path d="M7 14.5l1.5 5H11l-1.5-5" fill="#DB2777"/>`);
registerIcon("general-writer", "#475569", `<path d="M4 20l1-4.6L16 4.4a2.1 2.1 0 0 1 3 3L8 18.5 4 20z" fill="#94A3B8"/><path d="M14.6 5.8l3 3" stroke="white" stroke-width="1.4" stroke-linecap="round" fill="none"/><path d="M5 19l1.6-4 2.6 2.6L5 19z" fill="#475569"/>`);
registerIcon("legal-contract-expert", "#92400E", `<path d="M12 2.5v19M6 6.5h12" stroke="#D6A15C" stroke-width="1.8" stroke-linecap="round" fill="none"/><path d="M6 6.5l-3 6h6l-3-6z" fill="#92400E"/><path d="M18 6.5l-3 6h6l-3-6z" fill="#92400E"/><rect x="8" y="20" width="8" height="1.8" rx="0.9" fill="#92400E"/>`);
registerIcon("poetry-prose-expert", "#7E22CE", `<path d="M20 4c-6 0-11 3.5-13 9l-2 7 7-2c5.5-2 9-7 9-14z" fill="#D8B4FE"/><path d="M7 20l6-6M11 12c2.5-.5 5-2 6.5-4.5" stroke="#7E22CE" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("science-writing-expert", "#0891B2", `<circle cx="12" cy="12" r="2.2" fill="#0891B2"/><ellipse cx="12" cy="12" rx="9.5" ry="4" fill="none" stroke="#67E8F9" stroke-width="1.6"/><ellipse cx="12" cy="12" rx="9.5" ry="4" transform="rotate(60 12 12)" fill="none" stroke="#22D3EE" stroke-width="1.6"/><ellipse cx="12" cy="12" rx="9.5" ry="4" transform="rotate(-60 12 12)" fill="none" stroke="#06B6D4" stroke-width="1.6"/>`);
registerIcon("stock-research-report-expert", "#B91C1C", `<rect x="2.5" y="3" width="19" height="18" rx="2" fill="#FCA5A5"/><rect x="2.5" y="3" width="19" height="3" rx="2" fill="#B91C1C"/><path d="M6 16l3.5-4 3 2.5 5-6" stroke="#B91C1C" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/><path d="M6 18.6h12" stroke="white" stroke-width="1.2" stroke-linecap="round" opacity="0.8" fill="none"/>`);
registerIcon("tech-blog-expert", "#2563EB", `<rect x="2.5" y="3.5" width="19" height="17" rx="2" fill="#93C5FD"/><rect x="2.5" y="3.5" width="19" height="3.5" rx="2" fill="#2563EB"/><path d="M6.5 11l3 3-3 3M12.5 17h5" stroke="#1E3A8A" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
registerIcon("work-report-expert", "#0D9488", `<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#5EEAD4"/><path d="M15 2v5h5" fill="#0D9488"/><rect x="7.5" y="14" width="2.2" height="4.5" rx="0.6" fill="white" opacity="0.95"/><rect x="11" y="11.5" width="2.2" height="7" rx="0.6" fill="white" opacity="0.8"/><rect x="14.5" y="9.5" width="2.2" height="9" rx="0.6" fill="white" opacity="0.65"/>`);

// ========== 表格 / 演示 / 支付插件 ==========
registerIcon("tencent-docs-sheet-generation", "#217346", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#4CAF7D"/><rect x="3" y="3" width="18" height="4" rx="2" fill="#217346"/><path d="M3 11h18M3 16h18M9 7v14M15 7v14" stroke="white" stroke-width="0.9" opacity="0.6" fill="none"/><path d="M8 20v-4h8v4" fill="white" opacity="0.85"/>`);
registerIcon("tencent-docs-sheetagent", "#217346", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#4CAF7D"/><rect x="3" y="3" width="18" height="4" rx="2" fill="#217346"/><path d="M3 11h18M3 16h18M9 7v14M15 7v14" stroke="white" stroke-width="0.9" opacity="0.55" fill="none"/><circle cx="18" cy="18" r="3.4" fill="white"/><path d="M18 16.4v3.2M16.4 18h3.2" stroke="#217346" stroke-width="1.4" stroke-linecap="round" fill="none"/>`);
registerIcon("excel-generation", "#217346", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#4CAF7D"/><rect x="3" y="3" width="18" height="4" rx="2" fill="#217346"/><path d="M3 11h18M3 16h18M9 7v14M15 7v14" stroke="white" stroke-width="0.9" opacity="0.6" fill="none"/><path d="M8 20v-4h8v4" fill="white" opacity="0.85"/>`);
registerIcon("excel-handler", "#217346", `<rect x="3" y="3" width="18" height="18" rx="2" fill="#4CAF7D"/><rect x="3" y="3" width="18" height="4" rx="2" fill="#217346"/><path d="M3 11h18M3 16h18M9 7v14M15 7v14" stroke="white" stroke-width="0.9" opacity="0.55" fill="none"/><circle cx="18" cy="18" r="3.4" fill="white"/><path d="M18 16.4v3.2M16.4 18h3.2" stroke="#217346" stroke-width="1.4" stroke-linecap="round" fill="none"/>`);
registerIcon("tencent-pptx", "#D24726", `<rect x="2.5" y="4" width="19" height="13" rx="2" fill="#F08567"/><path d="M9 21h6M12 17v4" stroke="#D24726" stroke-width="2" stroke-linecap="round" fill="none"/><text x="12" y="13.5" text-anchor="middle" fill="white" font-size="6.5" font-weight="bold" font-family="Arial">PPT</text>`);
registerIcon("weixinpay-register", "#09BB07", `<rect x="2.5" y="5" width="15" height="10.5" rx="2" fill="#5EEAD4"/><rect x="2.5" y="7.5" width="15" height="2.4" fill="#09BB07"/><circle cx="18" cy="17.5" r="5" fill="#09BB07"/><path d="M18 15.3v4.4M15.8 17.5h4.4" stroke="white" stroke-width="1.6" stroke-linecap="round" fill="none"/>`);
registerIcon("weixinpay-pay", "#07C160", `<circle cx="12" cy="12" r="9.5" fill="#5EEAD4"/><circle cx="12" cy="12" r="6.6" fill="#07C160"/><text x="12" y="15.6" text-anchor="middle" fill="white" font-size="9" font-weight="bold" font-family="Arial">¥</text>`);
registerIcon("weixinpay-feedback", "#FBC02D", `<path d="M4 4.5h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-6l-4 4v-4H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z" fill="#FDE68A"/><path d="M12 7.5v4.2" stroke="#FBC02D" stroke-width="2" stroke-linecap="round" fill="none"/><circle cx="12" cy="14.6" r="1.1" fill="#B45309"/>`);

const iconData = computed(() => {
  const normalizedName = props.name.toLowerCase().replace(/^skill-/, "");
  return skillIcons[normalizedName] || skillIcons[props.name] || skillIcons[props.name.toLowerCase()] || null;
});

function initials(name: string): string {
  return name.split(/[-_\s/]+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "S";
}

function fallbackColor(name: string): string {
  const colors = ["#24282e", "#7867d9", "#1d8f6f", "#d36b44", "#307bc4", "#a27a20", "#be4d6b", "#6b7280", "#0d9488", "#9333ea"];
  return colors[[...name].reduce((sum, item) => sum + (item.codePointAt(0) ?? 0), 0) % colors.length];
}

const fallbackBg = computed(() => fallbackColor(props.name));
</script>

<template>
  <span v-if="iconData" class="skill-icon-svg" :style="{ width: size + 'px', height: size + 'px' }" v-html="iconData.svg" />
  <span v-else class="skill-icon-fallback" :style="{ background: fallbackBg, width: size + 'px', height: size + 'px', fontSize: (size * 0.4) + 'px' }">{{ initials(name) }}</span>
</template>

<style scoped>
.skill-icon-svg {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  border-radius: 10px;
  overflow: hidden;
  contain: strict;
}
.skill-icon-svg :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
}
.skill-icon-fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  border-radius: 10px;
  color: white;
  font-weight: 700;
  letter-spacing: -0.5px;
  contain: strict;
}
</style>
