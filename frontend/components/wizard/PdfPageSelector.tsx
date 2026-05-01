"use client";

import { useEffect, useState } from "react";
import { Loader2, X, FileText, AlertCircle, Check } from "lucide-react";
import {
  pdfToImagePages,
  blobToFile,
  PdfPagePreview,
} from "@/lib/pdfConverter";

interface Props {
  pdfFile: File;
  onSelect: (primaryFile: File, originalFile: File) => void; // primary = JPEG, original = PDF
  onCancel: () => void;
}

/**
 * Pack 13.1.3 — модалка выбора страницы из PDF.
 *
 * Логика:
 * - Открывается когда клиент загрузил PDF
 * - Конвертирует все страницы (макс 10) в JPEG превью
 * - Показывает грид превью
 * - Если 1 страница → автоматически выбирает её
 * - Если N страниц → клиент выбирает
 * - При выборе вызывает onSelect(primaryFile, originalFile)
 */
export function PdfPageSelector({ pdfFile, onSelect, onCancel }: Props) {
  const [pages, setPages] = useState<PdfPagePreview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedPageNum, setSelectedPageNum] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const result = await pdfToImagePages(pdfFile, { dpi: 200 });
        if (cancelled) return;
        setPages(result);
        // Если одна страница — авто-выбор
        if (result.length === 1) {
          setSelectedPageNum(1);
        }
        setLoading(false);
      } catch (e) {
        if (cancelled) return;
        setError(
          (e as Error).message ||
            "Не удалось обработать PDF. Попробуйте загрузить как фото."
        );
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pdfFile]);

  // Авто-confirm если 1 страница и она выбрана
  useEffect(() => {
    if (
      pages &&
      pages.length === 1 &&
      selectedPageNum === 1
    ) {
      // Микро-задержка для плавного UX
      const t = setTimeout(() => {
        handleConfirm();
      }, 300);
      return () => clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pages, selectedPageNum]);

  function handleConfirm() {
    if (!pages || selectedPageNum === null) return;
    const page = pages.find((p) => p.pageNum === selectedPageNum);
    if (!page) return;

    // Имена файлов
    const baseName = pdfFile.name.replace(/\.pdf$/i, "");
    const primaryName = `${baseName}_page${page.pageNum}.jpg`;

    const primaryFile = blobToFile(page.blob, primaryName);
    onSelect(primaryFile, pdfFile);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.5)" }}
    >
      <div
        className="rounded-xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col"
        style={{
          background: "var(--color-bg-primary)",
          border: "0.5px solid var(--color-border-secondary)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4 border-b"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderBottomWidth: 0.5,
          }}
        >
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5" style={{ color: "var(--color-accent)" }} />
            <span className="text-sm font-semibold text-primary">
              {pages && pages.length === 1
                ? "Обрабатываем PDF..."
                : "Выберите нужную страницу"}
            </span>
          </div>
          <button
            onClick={onCancel}
            className="p-1.5 rounded-md hover:bg-secondary transition-colors text-tertiary"
            aria-label="Закрыть"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-5">
          {loading && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-secondary" />
              <div className="text-sm text-tertiary">Конвертируем PDF...</div>
              <div className="text-xs text-tertiary">
                Это занимает 2–10 секунд в зависимости от размера
              </div>
            </div>
          )}

          {error && (
            <div
              className="p-4 rounded-md text-sm flex gap-2 items-start"
              style={{
                background: "var(--color-bg-danger)",
                color: "var(--color-text-danger)",
                border: "0.5px solid var(--color-border-danger)",
              }}
            >
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">Не удалось обработать PDF</div>
                <div className="mt-1 opacity-80">{error}</div>
                <div className="mt-2 text-xs">
                  Попробуйте: открыть PDF на компьютере, сделать скриншот
                  нужной страницы и загрузить как изображение.
                </div>
              </div>
            </div>
          )}

          {pages && pages.length > 1 && (
            <>
              <div className="text-xs text-tertiary mb-3">
                В вашем PDF {pages.length} страниц. Выберите ту, которую нужно
                распознать.
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {pages.map((page) => {
                  const selected = selectedPageNum === page.pageNum;
                  return (
                    <button
                      key={page.pageNum}
                      onClick={() => setSelectedPageNum(page.pageNum)}
                      className="relative rounded-md overflow-hidden text-left transition-all"
                      style={{
                        borderWidth: selected ? 2 : 0.5,
                        borderStyle: "solid",
                        borderColor: selected
                          ? "var(--color-accent)"
                          : "var(--color-border-secondary)",
                        background: "var(--color-bg-secondary)",
                      }}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={page.dataUrl}
                        alt={`Страница ${page.pageNum}`}
                        className="w-full h-auto block"
                        style={{ aspectRatio: `${page.width}/${page.height}` }}
                      />
                      <div
                        className="absolute top-1.5 left-1.5 rounded-full px-2 py-0.5 text-xs font-medium"
                        style={{
                          background: "rgba(0,0,0,0.6)",
                          color: "white",
                        }}
                      >
                        Стр. {page.pageNum}
                      </div>
                      {selected && (
                        <div
                          className="absolute top-1.5 right-1.5 rounded-full w-6 h-6 flex items-center justify-center"
                          style={{ background: "var(--color-accent)" }}
                        >
                          <Check className="w-3.5 h-3.5 text-white" />
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </>
          )}

          {pages && pages.length === 1 && !loading && (
            <div className="flex flex-col items-center justify-center py-8 gap-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={pages[0].dataUrl}
                alt="Страница 1"
                className="max-w-xs max-h-64 rounded-md"
                style={{
                  border: "0.5px solid var(--color-border-secondary)",
                }}
              />
              <div className="text-sm text-tertiary">
                Загружаем единственную страницу...
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {pages && pages.length > 1 && (
          <div
            className="px-5 py-4 border-t flex justify-between gap-3"
            style={{
              borderColor: "var(--color-border-tertiary)",
              borderTopWidth: 0.5,
            }}
          >
            <button
              onClick={onCancel}
              className="px-4 py-2 rounded-md text-sm border border-tertiary text-secondary hover:bg-secondary transition-colors"
              style={{ borderWidth: 0.5 }}
            >
              Отмена
            </button>

            <button
              onClick={handleConfirm}
              disabled={selectedPageNum === null}
              className="px-5 py-2 rounded-md text-sm font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              style={{ background: "var(--color-accent)" }}
            >
              {selectedPageNum
                ? `Использовать страницу ${selectedPageNum}`
                : "Выберите страницу"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
