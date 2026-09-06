/**
 * 图片 OCR 识别工具
 *
 * 使用 tesseract.js 在浏览器端进行文字识别，支持中文（简体）+英文。
 * 通过动态 import 按需加载，避免增大初始包体积。
 */

// 懒加载 tesseract.js 模块（首次调用时才加载 WASM 和核心代码）
let tesseractModule: typeof import("tesseract.js") | null = null;

async function loadTesseract(): Promise<typeof import("tesseract.js")> {
  if (!tesseractModule) {
    tesseractModule = await import("tesseract.js");
  }
  return tesseractModule;
}

// 复用 worker 避免重复初始化（首次识别后缓存）
let cachedWorker: Awaited<ReturnType<typeof import("tesseract.js")["createWorker"]>> | null = null;
let cachedWorkerLang = "";

export type OcrProgress = {
  status: string;
  progress: number;
};

export type OcrResult = {
  text: string;
  confidence: number;
};

/**
 * 对 base64 编码的图片执行 OCR 识别。
 *
 * @param dataBase64 - 图片的 base64 数据（不含 data: 前缀）或完整 data URL
 * @param mediaType - 图片 MIME 类型（如 image/png）
 * @param onProgress - 进度回调（可选）
 * @returns 识别出的文本和置信度
 */
export async function recognizeImage(
  dataBase64: string,
  mediaType = "image/png",
  onProgress?: (p: OcrProgress) => void,
): Promise<OcrResult> {
  const Tesseract = await loadTesseract();

  // 构造可识别的图片源（data URL）
  const src = dataBase64.startsWith("data:")
    ? dataBase64
    : `data:${mediaType};base64,${dataBase64}`;

  const lang = "chi_sim+eng";

  // 创建或复用 worker
  if (!cachedWorker || cachedWorkerLang !== lang) {
    if (cachedWorker) {
      try { await cachedWorker.terminate(); } catch { /* ignore */ }
    }
    cachedWorker = await Tesseract.createWorker(lang, 1, {
      logger: (m) => {
        if (onProgress && m && typeof m.progress === "number") {
          onProgress({ status: String(m.status || ""), progress: m.progress });
        }
      },
    });
    cachedWorkerLang = lang;
  }

  try {
    const result = await cachedWorker.recognize(src);
    const text = (result?.data?.text || "").trim();
    const confidence = result?.data?.confidence ?? 0;
    return { text, confidence };
  } catch (error) {
    // 如果 worker 出错，清除缓存以便下次重建
    if (cachedWorker) {
      try { await cachedWorker.terminate(); } catch { /* ignore */ }
      cachedWorker = null;
      cachedWorkerLang = "";
    }
    throw error;
  }
}

/**
 * 释放 OCR worker 资源（可在应用退出或长时间不用时调用）
 */
export async function terminateOcrWorker(): Promise<void> {
  if (cachedWorker) {
    try { await cachedWorker.terminate(); } catch { /* ignore */ }
    cachedWorker = null;
    cachedWorkerLang = "";
  }
}
