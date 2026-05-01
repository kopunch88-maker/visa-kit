/**
 * Pack 13.1.3 — конвертация PDF → JPEG на клиенте через PDF.js.
 *
 * Стратегия:
 * - PDF.js загружается lazy (только при необходимости)
 * - Используем CDN-версию (cloudflare cdnjs) чтобы не тащить в bundle
 * - DPI 200 для хорошего качества OCR при разумном размере
 * - Worker подключается с того же CDN
 *
 * Использование:
 *   const pages = await pdfToImagePages(pdfFile, { dpi: 200 });
 *   // pages: [{ pageNum: 1, dataUrl: "data:image/jpeg;base64,...", blob: Blob }, ...]
 *
 *   const jpegFile = await blobToFile(pages[0].blob, "passport.jpg");
 */

const PDFJS_VERSION = "4.0.379";
const PDFJS_CDN = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}`;

let pdfjsLibPromise: Promise<any> | null = null;

/**
 * Lazy-load PDF.js из CDN. Кеширует промис чтобы не загружать дважды.
 */
async function loadPdfJs(): Promise<any> {
  if (pdfjsLibPromise) return pdfjsLibPromise;

  pdfjsLibPromise = new Promise((resolve, reject) => {
    // Проверим если уже загружен
    if (typeof window !== "undefined" && (window as any).pdfjsLib) {
      resolve((window as any).pdfjsLib);
      return;
    }

    if (typeof document === "undefined") {
      reject(new Error("PDF.js can only be loaded in a browser environment"));
      return;
    }

    const script = document.createElement("script");
    script.src = `${PDFJS_CDN}/pdf.min.js`;
    script.async = true;
    script.onload = () => {
      const pdfjsLib = (window as any).pdfjsLib;
      if (!pdfjsLib) {
        reject(new Error("PDF.js loaded but pdfjsLib is undefined"));
        return;
      }
      // Setup worker
      pdfjsLib.GlobalWorkerOptions.workerSrc = `${PDFJS_CDN}/pdf.worker.min.js`;
      resolve(pdfjsLib);
    };
    script.onerror = () => reject(new Error("Failed to load PDF.js from CDN"));
    document.head.appendChild(script);
  });

  return pdfjsLibPromise;
}


export interface PdfPagePreview {
  pageNum: number;
  dataUrl: string;       // для <img src=...>
  blob: Blob;            // для отправки
  width: number;         // в пикселях
  height: number;
}


export interface PdfConversionOptions {
  dpi?: number;          // default 200
  maxPages?: number;     // default 10 (защита от огромных PDF)
  jpegQuality?: number;  // 0-1, default 0.92
}


/**
 * Конвертирует PDF в массив JPEG-страниц.
 *
 * @throws Error если PDF не валидный или браузер не поддерживает canvas
 */
export async function pdfToImagePages(
  pdfFile: File | Blob,
  options: PdfConversionOptions = {},
): Promise<PdfPagePreview[]> {
  const { dpi = 200, maxPages = 10, jpegQuality = 0.92 } = options;

  const pdfjsLib = await loadPdfJs();

  // Читаем PDF в ArrayBuffer
  const arrayBuffer = await pdfFile.arrayBuffer();

  // Загружаем PDF
  const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(arrayBuffer) }).promise;

  const totalPages = Math.min(pdf.numPages, maxPages);
  const pages: PdfPagePreview[] = [];

  // PDF.js использует viewport.scale = 1.0 = 72 DPI (стандартный PDF DPI)
  // Чтобы получить N DPI, нужен scale = N / 72
  const scale = dpi / 72;

  for (let pageNum = 1; pageNum <= totalPages; pageNum++) {
    const page = await pdf.getPage(pageNum);
    const viewport = page.getViewport({ scale });

    // Создаём canvas нужного размера
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("Canvas 2D context not available");
    }

    // Белый фон (на случай если PDF прозрачный)
    ctx.fillStyle = "white";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Рендерим страницу
    await page.render({ canvasContext: ctx, viewport }).promise;

    // Конвертируем в Blob (JPEG)
    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (b) => {
          if (b) resolve(b);
          else reject(new Error(`Failed to convert page ${pageNum} to Blob`));
        },
        "image/jpeg",
        jpegQuality,
      );
    });

    // dataUrl для превью
    const dataUrl = canvas.toDataURL("image/jpeg", jpegQuality);

    pages.push({
      pageNum,
      dataUrl,
      blob,
      width: canvas.width,
      height: canvas.height,
    });
  }

  return pages;
}


/**
 * Конвертирует Blob в File (для отправки через FormData).
 */
export function blobToFile(blob: Blob, fileName: string): File {
  return new File([blob], fileName, {
    type: blob.type,
    lastModified: Date.now(),
  });
}


/**
 * Возвращает true если файл — PDF (по MIME или расширению).
 */
export function isPdfFile(file: File): boolean {
  if (file.type === "application/pdf") return true;
  return file.name.toLowerCase().endsWith(".pdf");
}


/**
 * Возвращает true если файл — HEIC/HEIF (формат iPhone).
 * Браузеры пока не умеют рендерить HEIC, но мы можем их отправить
 * как оригинал, а primary конвертирует backend через pillow-heif.
 */
export function isHeicFile(file: File): boolean {
  const lowerType = file.type.toLowerCase();
  if (lowerType === "image/heic" || lowerType === "image/heif") return true;
  const lowerName = file.name.toLowerCase();
  return lowerName.endsWith(".heic") || lowerName.endsWith(".heif");
}
