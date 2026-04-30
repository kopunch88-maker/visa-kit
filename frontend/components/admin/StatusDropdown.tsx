"use client";

import { useState, useEffect, useRef } from "react";
import { ChevronDown, Check } from "lucide-react";
import { STATUS_LABELS } from "@/lib/api";

interface Props {
  currentStatus: string;
  onChange: (newStatus: string) => void;
}

// Статусы которые менеджер может назначить вручную
const MANUAL_STATUSES = [
  "ready_to_assign",
  "assigned",
  "drafts_generated",
  "at_translator",
  "awaiting_scans",
  "awaiting_digital_sign",
  "submitted",
  "approved",
  "rejected",
  "needs_followup",
  "hold",
  "cancelled",
];

export function StatusDropdown({ currentStatus, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function handleSelect(status: string) {
    setOpen(false);
    if (status !== currentStatus) {
      onChange(status);
    }
  }

  return (
    <div className="relative w-full" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-3 py-1.5 rounded-md text-sm font-medium text-white flex items-center justify-center gap-1.5 transition-colors"
        style={{ background: "var(--color-accent)" }}
      >
        Изменить статус
        <ChevronDown className={`w-4 h-4 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-1 z-20 bg-primary rounded-lg border shadow-lg overflow-hidden min-w-[240px]"
          style={{
            borderColor: "var(--color-border-tertiary)",
            borderWidth: 0.5,
          }}
        >
          {MANUAL_STATUSES.map((status) => {
            const isCurrent = status === currentStatus;
            return (
              <button
                key={status}
                onClick={() => handleSelect(status)}
                disabled={isCurrent}
                className="w-full px-3 py-2 text-sm text-left text-secondary hover:bg-secondary disabled:opacity-40 disabled:cursor-default flex items-center justify-between gap-2"
              >
                <span>{STATUS_LABELS[status] || status}</span>
                {isCurrent && (
                  <Check className="w-4 h-4 text-success flex-shrink-0" />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
