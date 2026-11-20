import { api } from "./api";
import type { ChatAttachment } from "../types";

export const MAX_CHAT_ATTACHMENTS = 6;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const MAX_IMAGE_DIM = 1600;
const COMPRESS_THRESHOLD_BYTES = 1.5 * 1024 * 1024;

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error(`无法读取图片「${file.name || "剪贴板图片"}」。`));
    reader.readAsDataURL(file);
  });
}

async function compressImageIfNeeded(dataUrl: string, mimeType: string, rawBytes: number): Promise<{ dataUrl: string; mimeType: string }> {
  if (rawBytes <= COMPRESS_THRESHOLD_BYTES || typeof Image === "undefined") {
    return { dataUrl, mimeType };
  }
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, MAX_IMAGE_DIM / Math.max(img.width || 1, img.height || 1));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(img.width * scale));
      canvas.height = Math.max(1, Math.round(img.height * scale));
      const ctx = canvas.getContext("2d");
      if (!ctx) { resolve({ dataUrl, mimeType }); return; }
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const outMime = mimeType === "image/png" && rawBytes < 3 * 1024 * 1024 ? "image/png" : "image/jpeg";
      resolve({ dataUrl: canvas.toDataURL(outMime, 0.86), mimeType: outMime });
    };
    img.onerror = () => resolve({ dataUrl, mimeType });
    img.src = dataUrl;
  });
}

export async function prepareChatAttachment(file: File): Promise<ChatAttachment> {
  const isImage = file.type.startsWith("image/") || /\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name);
  if (isImage) {
    if (file.size > MAX_IMAGE_BYTES) {
      throw new Error(`图片「${file.name || "剪贴板图片"}」超过 8 MB，请压缩后再粘贴。`);
    }
    const rawUrl = await readAsDataUrl(file);
    const mime = file.type || "image/png";
    const { dataUrl, mimeType } = await compressImageIfNeeded(rawUrl, mime, file.size);
    return {
      type: "image",
      name: file.name || `粘贴图片-${new Date().toLocaleTimeString("zh-CN", { hour12: false }).replace(/:/g, "")}.png`,
      mime_type: mimeType,
      data_url: dataUrl,
    };
  }
  const result = await api.extractChatAttachment(file);
  return result.attachment;
}
