import { readFile } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import type { ContentBlock, KnownContentBlock } from "../context.js";

const SUPPORTED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
const EXTENSION_MIME: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
};

export function getMimeTypeFromPath(filePath: string): string | null {
  return EXTENSION_MIME[path.extname(filePath).toLowerCase()] ?? null;
}

export function isSupportedImageType(mediaType: string): boolean {
  return SUPPORTED_IMAGE_TYPES.has(mediaType.toLowerCase());
}

export function dataUrlFromBase64(mediaType: string, data: string): string {
  const validated = validateBase64Image(mediaType, data);
  return `data:${validated.mediaType};base64,${validated.data}`;
}

export function validateBase64Image(mediaType: string, data: string, maxSizeBytes = 20 * 1024 * 1024): { mediaType: string; data: string; decodedBytes: number } {
  const normalizedMediaType = mediaType.toLowerCase();
  if (!isSupportedImageType(normalizedMediaType)) throw new Error(`Unsupported image type: ${mediaType}`);
  if (!data || data.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(data)) throw new Error("Image data must be valid base64");
  const padding = data.endsWith("==") ? 2 : data.endsWith("=") ? 1 : 0;
  const decodedBytes = (data.length / 4) * 3 - padding;
  if (decodedBytes > maxSizeBytes) throw new Error(`Image too large: ${decodedBytes} bytes (max ${maxSizeBytes})`);
  return { mediaType: normalizedMediaType, data, decodedBytes };
}

export function base64FromDataUrl(url: string): { mediaType: string; data: string } | null {
  const match = /^data:([^;,]+);base64,([\s\S]+)$/i.exec(url);
  if (!match) return null;
  const validated = validateBase64Image(match[1]!, match[2]!);
  return { mediaType: validated.mediaType, data: validated.data };
}

export function base64ImageSource(block: ContentBlock): { mediaType: string; data: string } | null {
  if (block.type !== "image") return null;
  const source = block.source;
  if (!source || typeof source !== "object" || Array.isArray(source)) throw new Error("Image block requires a base64 source");
  const value = source as Record<string, unknown>;
  const mediaType = String(value.media_type ?? "").toLowerCase();
  const data = String(value.data ?? "");
  if (!mediaType || !data) throw new Error("Image block requires media_type and data");
  const validated = validateBase64Image(mediaType, data);
  return { mediaType: validated.mediaType, data: validated.data };
}

export type ImagePreprocessOptions = { maxLongEdge?: number; maxShortEdge?: number; maxBytes?: number };
export type ProcessedImage = { bytes: Buffer; mediaType: string; width: number; height: number; originalWidth: number; originalHeight: number; originalBytes: number };

/** Resize only when necessary. Animated GIF is explicitly rejected rather than silently dropping frames. */
export async function preprocessImage(bytes: Buffer, mediaType: string, options: ImagePreprocessOptions = {}): Promise<ProcessedImage> {
  const normalized = mediaType.toLowerCase();
  if (!isSupportedImageType(normalized)) throw new Error(`Unsupported image type: ${mediaType}`);
  const maxLongEdge = options.maxLongEdge ?? 2_048; const maxShortEdge = options.maxShortEdge ?? 2_048; const maxBytes = options.maxBytes ?? 20 * 1024 * 1024;
  // Keep sharp external to esbuild: desktop's existing prepare-runtime copies its native binary and libvips.
  const sharp = createRequire(import.meta.url)("sharp") as typeof import("sharp");
  const input = sharp(bytes, { animated: false, limitInputPixels: 40_000_000 }); const metadata = await input.metadata();
  const originalWidth = metadata.width ?? 0; const originalHeight = metadata.height ?? 0;
  if (!(originalWidth > 0 && originalHeight > 0)) throw new Error("Image dimensions could not be determined");
  if (normalized === "image/gif" && (metadata.pages ?? 1) > 1) throw new Error("Animated GIF is not supported; upload a still image instead");
  const scale = Math.min(1, maxLongEdge / Math.max(originalWidth, originalHeight), maxShortEdge / Math.min(originalWidth, originalHeight));
  const pipeline = scale < 1 ? input.resize({ width: Math.max(1, Math.floor(originalWidth * scale)), height: Math.max(1, Math.floor(originalHeight * scale)), fit: "fill", withoutEnlargement: true }) : input;
  const output = await pipeline.toBuffer({ resolveWithObject: true });
  if (output.data.length > maxBytes) throw new Error(`Image too large after preprocessing: ${output.data.length} bytes (max ${maxBytes})`);
  return { bytes: output.data, mediaType: normalized, width: output.info.width, height: output.info.height, originalWidth, originalHeight, originalBytes: bytes.length };
}

export async function imageToContentBlock(filePath: string, maxSizeBytes = 20 * 1024 * 1024): Promise<Extract<KnownContentBlock, { type: "image" }>> {
  const mediaType = getMimeTypeFromPath(filePath);
  if (!mediaType) throw new Error(`Unsupported image type: ${filePath}`);
  const bytes = await readFile(filePath);
  const processed = await preprocessImage(bytes, mediaType, { maxBytes: maxSizeBytes });
  return { type: "image", source: { media_type: processed.mediaType, data: processed.bytes.toString("base64"), width: processed.width, height: processed.height, original_width: processed.originalWidth, original_height: processed.originalHeight, original_bytes: processed.originalBytes } };
}
