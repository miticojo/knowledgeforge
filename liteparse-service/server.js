/**
 * LiteParse Document Parsing Service.
 *
 * Lightweight Cloud Run microservice for PDF/document parsing using LiteParse + PDFium.
 * Extracts text, images, and page structure from PDFs.
 *
 * Endpoints:
 *   POST /parse     — Parse uploaded file (multipart/form-data)
 *   GET  /health    — Health check
 */
import express from "express";
import multer from "multer";
import { LiteParse } from "@llamaindex/liteparse";
import sharp from "sharp";
import fs from "fs/promises";
import path from "path";
import os from "os";

const app = express();
const upload = multer({ dest: os.tmpdir(), limits: { fileSize: 100 * 1024 * 1024 } }); // 100MB max

app.get("/health", (_req, res) => {
  res.json({ status: "ok", service: "liteparse" });
});

app.post("/parse", upload.single("file"), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: "No file uploaded" });
  }

  const t0 = Date.now();
  const filePath = req.file.path;
  const fileName = req.file.originalname || "document";
  const ext = path.extname(fileName).toLowerCase();

  try {
    const parser = new LiteParse();

    // 1. Extract text
    const result = await parser.parse(filePath);
    const text = result.text || "";

    // 2. Extract images via PDFium
    const images = [];
    if (ext === ".pdf") {
      try {
        const pdfiumPath = path.join(
          process.cwd(),
          "node_modules/@llamaindex/liteparse/dist/src/engines/pdf/pdfium-renderer.js"
        );
        const { PdfiumRenderer } = await import("file://" + pdfiumPath);
        const renderer = new PdfiumRenderer();
        await renderer.loadDocument(filePath);

        const totalPages = result.pages?.length || 1;
        const pagesWithImages = [];

        for (let p = 1; p <= totalPages; p++) {
          try {
            const imageBounds = await renderer.extractImageBounds(filePath, p);
            if (imageBounds.length > 0) {
              pagesWithImages.push({ pageNum: p, images: imageBounds });
            }
          } catch {
            break;
          }
        }

        if (pagesWithImages.length > 0) {
          const pageNums = pagesWithImages.map((p) => p.pageNum);
          const screenshots = await parser.screenshot(filePath, pageNums, true);
          const screenshotMap = new Map(screenshots.map((s) => [s.pageNum, s]));

          for (const pageInfo of pagesWithImages) {
            const screenshot = screenshotMap.get(pageInfo.pageNum);
            if (!screenshot) continue;

            const pdfPage = result.pages?.find((pg) => pg.pageNum === pageInfo.pageNum);
            const pdfW = pdfPage?.width || screenshot.width;
            const pdfH = pdfPage?.height || screenshot.height;
            const scaleX = screenshot.width / pdfW;
            const scaleY = screenshot.height / pdfH;

            for (const img of pageInfo.images) {
              const cropX = Math.max(0, Math.round(img.x * scaleX));
              const cropY = Math.max(0, Math.round(img.y * scaleY));
              const cropW = Math.min(Math.round(img.width * scaleX), screenshot.width - cropX);
              const cropH = Math.min(Math.round(img.height * scaleY), screenshot.height - cropY);

              // Skip tiny images (likely artifacts, icons, or decorations)
              if (cropW < 50 || cropH < 50) continue;

              let imageBuffer;
              try {
                // Crop the figure from the full-page screenshot
                imageBuffer = await sharp(screenshot.imageBuffer)
                  .extract({ left: cropX, top: cropY, width: cropW, height: cropH })
                  .png()
                  .toBuffer();
              } catch {
                // Fallback to full page if crop fails
                imageBuffer = screenshot.imageBuffer;
              }

              images.push({
                pageNum: pageInfo.pageNum,
                bounds: { x: cropX, y: cropY, width: cropW, height: cropH },
                pageWidth: screenshot.width,
                pageHeight: screenshot.height,
                dataUri: `data:image/png;base64,${imageBuffer.toString("base64")}`,
              });
            }
          }
        }

        renderer.close?.();
      } catch (imgErr) {
        console.log(`Image extraction skipped: ${imgErr?.message?.slice(0, 80)}`);
      }
    }

    const elapsed = Date.now() - t0;
    console.log(`Parsed ${fileName}: ${text.length} chars, ${images.length} images, ${elapsed}ms`);

    res.json({
      text,
      images,
      metadata: {
        filename: fileName,
        format: ext,
        text_length: text.length,
        num_images: images.length,
        num_pages: result.pages?.length || 0,
        parse_time_ms: elapsed,
        engine: "liteparse",
      },
    });
  } catch (err) {
    console.error(`Parse failed for ${fileName}:`, err?.message || err);
    res.status(500).json({ error: `Parsing failed: ${err?.message?.slice(0, 200)}` });
  } finally {
    await fs.unlink(filePath).catch(() => {});
  }
});

const PORT = process.env.PORT || 8090;
app.listen(PORT, () => {
  console.log(`LiteParse service running on port ${PORT}`);
});
