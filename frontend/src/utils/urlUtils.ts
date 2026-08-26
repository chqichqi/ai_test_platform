/**
 * URL 工具函数
 */

/**
 * 规范化 URL 中的冒号
 * 将 URL 中可能被转义的冒号（%3A）还原为标准冒号（:）
 */
export const normalizeUrlColon = (url: string): string => {
  if (!url) return url;
  return url.replace(/%3A/gi, ':');
};
