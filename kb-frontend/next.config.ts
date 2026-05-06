import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone',
  serverExternalPackages: ["@llamaindex/liteparse", "mammoth", "xlsx", "tesseract.js", "pdfjs-dist", "@hyzyla/pdfium", "sharp"],
};

export default nextConfig;
