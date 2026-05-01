/**
 * Pack 13.1.3 (fix) — конвертация PDF → JPEG на клиенте через PDF.js.
 *
 * История:
 * - Изначально использовали cdnjs с версией 4.0.379, но клиент получал
 *   "Failed to load PDF.js from CDN" — возможно cdnjs блокировался адблокером
 *   или конкретный путь был недоступен.
 *
 * Текущая стратегия:
 * - Используем unpkg.com (npm зеркало) — отдаёт UMD-build надёжно
 * - Версия 3.11.174 — последняя UMD-версия PDF.js которая работает через <script>
 *   (5.x перешли на ES modules, через <script> не подключаются)
 * - Если unpkg недоступен — fallback на jsdelivr
 * - Если оба недоступны — fallback на cdnjs
 * - Worker подгружается с того же CDN откуда основной файл
 *
 * DPI 200 — золотая середина для OCR.
 */

interface CdnSource {
  name: string;
  scriptUrl: string;
  workerUrl: string;
}

const PDFJS_VERSION = "3.11.174";

// Список CDN в порядке приоритета — каждый пробуем по очереди
const CDN_SOURCES: CdnSource[] = [
  {
    name: "unpkg",
    scriptUrl: `https://unpkg.com/pdfjs-dist@${PDFJS_VERSION}/legacy/build/pdf.min.js`,
    workerUrl: `https://unpkg.com/pdfjs-dist@${PDFJS_VERSION}/legacy/build/pdf.worker.min.js`,
  },
  {
    name: "jsdelivr",
    scriptUrl: `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}/legacy/build/pdf.min.js`,
    workerUrl: `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}/legacy/build/pdf.worker.min.js`,
  },
  {
    name: "cdnjs",
    scriptUrl: `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}/pdf.min.js`,
    workerUrl: `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}/pdf.worker.min.js`,
  },
];

let pdfjsLibPromise: Promise<any> | null = null;


function loadScriptFrom(source: CdnSource, timeoutMs = 15000): Promise<any> {
  return new Promise((resolve, reject) => {
    if (typeof window !== "undefined" && (window as any).pdfjsLib) {
      resolve((window as any).pdfjsLib);
      return;
    }
    if (typeof document === "undefined") {
      reject(new Error("Not in browser environment"));
      return;
    }

    const script = document.createElement("script");
    script.src = source.scriptUrl;
    script.async = true;

    const timeout = setTimeout(() => {
      script.remove();
      reject(new Error(`${source.name}: timeout after ${timeoutMs}ms`));
    }, timeoutMs);

    script.onload = () => {
      clearTimeout(timeout);
      const pdfjsLib = (window as any).pdfjsLib;
      if (!pdfjsLib) {
        reject(new Error(`${source.name}: loaded but window.pdfjsLib undefined`));
        return;
      }
      pdfjsLib.GlobalWorkerOptions.workerSrc = source.workerUrl;
      console.log(`[pdfConverter] PDF.js ${PDFJS_VERSION} loaded from ${source.name}`);
      resolve(pdfjsLib);
    };

    script.onerror = () => {
      clearTimeout(timeout);
      script.remove();
      reject(new Error(`${source.name}: script load failed`));
    };

    document.head.appendChild(script);
  });
}


/**
 * Lazy-load PDF.js. Пробует CDN из CDN_SOURCES по очереди.
 * Кеширует результат — повторный вызов вернёт тот же промис.
 */
async function loadPdfJs(): Promise<any> {
  if (pdfjsLibPromise) return pdfjsLibPromise;

  pdfjsLibPromise = (async () => {
    const errors: string[] = [];
    for (const source of CDN_SOURCES) {
      try {
        const lib = await loadScriptFrom(source);
        return lib;
      } catch (e) {
        const msg = (e as Error).message;
        errors.push(msg);
        console.warn(`[pdfConverter] ${msg} — trying next CDN`);
      }
    }
    // Все CDN провалились
    throw new Error(
      `Не удалось загрузить PDF.js ни с одного CDN. Возможно, блокирует расширение браузера ` +
        `или сетевой фильтр. Попытки: ${errors.join("; ")}`
    );
  })();

  // Если все CDN провалились — сбросим кеш чтобы при следующей попытке снова попробовать
  pdfjsLibPromise.catch(() => {
    pdfjsLibPromise = null;
  });

  return pdfjsLibPromise;
}


export interface PdfPagePreview {
  pageNum: number;
  dataUrl: string;
  blob: Blob;
  width: number;
  height: number;
}


export interface PdfConversionOptions {
  dpi?: number;
  maxPages?: number;
  jpegQuality?: number;
}


export async function pdfToImagePages(
  pdfFile: File | Blob,
  options: PdfConversionOptions = {},
): Promise<PdfPagePreview[]> {
  const { dpi = 200, maxPages = 10, jpegQuality = 0.92 } = options;

  const pdfjsLib = await loadPdfJs();

  const arrayBuffer = await pdfFile.arrayBuffer();

  const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(arrayBuffer) }).promise;

  const totalPages = Math.min(pdf.numPages, maxPages);
  const pages: PdfPagePreview[] = [];

  // PDF.js: scale = 1.0 = 72 DPI (стандарт PDF)
  const scale = dpi / 72;

  for (let pageNum = 1; pageNum <= totalPages; pageNum++) {
    const page = await pdf.getPage(pageNum);
    const viewport = page.getViewport({ scale });

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

    await page.render({ canvasContext: ctx, viewport }).promise;

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


export function blobToFile(blob: Blob, fileName: string): File {
  return new File([blob], fileName, {
    type: blob.type,
    lastModified: Date.now(),
  });
}


export function isPdfFile(file: File): boolean {
  if (file.type === "application/pdf") return true;
  return file.name.toLowerCase().endsWith(".pdf");
}


export function isHeicFile(file: File): boolean {
  const lowerType = file.type.toLowerCase();
  if (lowerType === "image/heic" || lowerType === "image/heif") return true;
  const lowerName = file.name.toLowerCase();
  return lowerName.endsWith(".heic") || lowerName.endsWith(".heif");
}