import { NextResponse } from "next/server";
import * as mammoth from "mammoth";
import * as xlsx from "xlsx";
import JSZip from "jszip";

export async function POST(req: Request) {
  try {
    const formData = await req.formData();
    const file = formData.get("file") as File;

    if (!file) {
      return NextResponse.json({ error: "No file uploaded" }, { status: 400 });
    }

    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);
    const fileName = file.name.toLowerCase();

    let extractedText = "";
    const extractedImages: any[] = [];

    // GESTIONE PPTX (ZIP con slide XML)
    if (fileName.endsWith(".pptx")) {
      const zip = await JSZip.loadAsync(buffer);
      const slideFiles = Object.keys(zip.files)
        .filter((f) => /^ppt\/slides\/slide\d+\.xml$/i.test(f))
        .sort((a, b) => {
          const numA = parseInt(a.match(/slide(\d+)/)?.[1] || "0");
          const numB = parseInt(b.match(/slide(\d+)/)?.[1] || "0");
          return numA - numB;
        });

      for (const slideFile of slideFiles) {
        const slideNum = slideFile.match(/slide(\d+)/)?.[1] || "?";
        const xml = await zip.files[slideFile].async("text");
        // Estrai testo dai tag <a:t> (DrawingML text runs)
        const textMatches = xml.match(/<a:t>([^<]*)<\/a:t>/g);
        if (textMatches && textMatches.length > 0) {
          const slideTexts = textMatches.map((m: string) => m.replace(/<\/?a:t>/g, "")).join(" ");
          extractedText += `\n--- Slide ${slideNum} ---\n${slideTexts}\n`;
        }
      }

      // Estrai note del presentatore
      const noteFiles = Object.keys(zip.files)
        .filter((f) => /^ppt\/notesSlides\/notesSlide\d+\.xml$/i.test(f))
        .sort();
      for (const noteFile of noteFiles) {
        const noteNum = noteFile.match(/notesSlide(\d+)/)?.[1] || "?";
        const xml = await zip.files[noteFile].async("text");
        const textMatches = xml.match(/<a:t>([^<]*)<\/a:t>/g);
        if (textMatches && textMatches.length > 0) {
          const noteTexts = textMatches.map((m: string) => m.replace(/<\/?a:t>/g, "")).join(" ");
          if (noteTexts.trim()) {
            extractedText += `\n--- Note Slide ${noteNum} ---\n${noteTexts}\n`;
          }
        }
      }
    }
    // GESTIONE DOCX
    else if (fileName.endsWith(".docx")) {
      const result = await mammoth.extractRawText({ buffer });
      extractedText = result.value;
    }
    // GESTIONE XLSX
    else if (fileName.endsWith(".xlsx")) {
      const workbook = xlsx.read(buffer, { type: "buffer" });
      const sheetNames = workbook.SheetNames;
      for (const sheetName of sheetNames) {
        extractedText += `\n--- Foglio: ${sheetName} ---\n`;
        extractedText += xlsx.utils.sheet_to_csv(workbook.Sheets[sheetName]);
      }
    }
    // GESTIONE PDF — LiteParse Cloud Run (text + images in one call)
    else if (fileName.endsWith(".pdf")) {
      const LITEPARSE_URL = process.env.LITEPARSE_URL;
      if (!LITEPARSE_URL) {
        throw new Error("LITEPARSE_URL env var is required for PDF parsing");
      }

      const lpFormData = new FormData();
      lpFormData.append("file", new Blob([buffer]), fileName);
      lpFormData.append("output_format", "markdown");

      // Get identity token for Cloud Run auth
      let lpHeaders: Record<string, string> = {};
      try {
        // On GCP: use metadata server
        const metadataUrl = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=" + LITEPARSE_URL;
        const tokenRes = await fetch(metadataUrl, { headers: { "Metadata-Flavor": "Google" }, signal: AbortSignal.timeout(1000) });
        if (tokenRes.ok) {
          lpHeaders["Authorization"] = `Bearer ${await tokenRes.text()}`;
        }
      } catch {
        // Local dev: use gcloud CLI identity token
        try {
          const { execFileSync } = await import("child_process");
          const token = execFileSync("gcloud", ["auth", "print-identity-token"], { encoding: "utf-8" }).trim();
          if (token) lpHeaders["Authorization"] = `Bearer ${token}`;
        } catch {
          console.log("LiteParse auth: no credentials available, trying without auth");
        }
      }

      const liteparseRes = await fetch(`${LITEPARSE_URL}/parse`, {
        method: "POST",
        body: lpFormData,
        headers: lpHeaders,
      });

      if (!liteparseRes.ok) {
        const errText = await liteparseRes.text().catch(() => "");
        return NextResponse.json(
          { error: `LiteParse returned ${liteparseRes.status}: ${errText.slice(0, 200)}` },
          { status: 502 }
        );
      }

      const lpData = await liteparseRes.json() as any;
      console.log(`LiteParse Cloud: ${lpData.metadata?.text_length} chars, ${lpData.metadata?.num_images} images, ${lpData.metadata?.parse_time_ms}ms`);
      return NextResponse.json({
        text: lpData.text || "",
        images: lpData.images || [],
        engine: "liteparse-cloud",
      });
    }
    // GESTIONE ALTRI FORMATI (plain text)
    else {
      extractedText = buffer.toString("utf-8");
    }

    return NextResponse.json({
      text: extractedText,
      images: extractedImages,
    });
  } catch (error: any) {
    console.error("Universal parsing error:", error);
    return NextResponse.json({ error: error.message || "Error during extraction" }, { status: 500 });
  }
}
