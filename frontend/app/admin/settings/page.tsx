"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Building2, Briefcase, UserCheck, MapPin, Loader2 } from "lucide-react";
import { getToken } from "@/lib/api";
import { CompaniesTab } from "@/components/admin/settings/CompaniesTab";
import { PositionsTab } from "@/components/admin/settings/PositionsTab";
import { RepresentativesTab } from "@/components/admin/settings/RepresentativesTab";
import { SpainAddressesTab } from "@/components/admin/settings/SpainAddressesTab";

const TABS = [
  { id: "companies", label: "Компании", icon: Building2 },
  { id: "positions", label: "Должности", icon: Briefcase },
  { id: "representatives", label: "Представители", icon: UserCheck },
  { id: "addresses", label: "Адреса в Испании", icon: MapPin },
];

export default function SettingsPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState("companies");
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/admin/login");
    } else {
      setAuthChecked(true);
    }
  }, [router]);

  if (!authChecked) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-tertiary" />
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-4 py-4">
      {/* Шапка */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/admin")}
            className="p-1.5 rounded-md text-tertiary hover:text-primary hover:bg-secondary transition-colors"
            title="Вернуться к заявкам"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-xl font-semibold text-primary">Настройки</h1>
        </div>
      </div>

      {/* Табы */}
      <div className="flex gap-1 mb-4 border-b" style={{ borderColor: "var(--color-border-tertiary)", borderBottomWidth: 0.5 }}>
        {TABS.map((tab) => {
          const isActive = tab.id === activeTab;
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium transition-colors flex items-center gap-2 border-b-2 -mb-[0.5px] ${
                isActive ? "text-primary" : "text-tertiary hover:text-secondary"
              }`}
              style={{
                borderColor: isActive ? "var(--color-accent)" : "transparent",
              }}
            >
              <Icon className="w-4 h-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Контент таба */}
      <div>
        {activeTab === "companies" && <CompaniesTab />}
        {activeTab === "positions" && <PositionsTab />}
        {activeTab === "representatives" && <RepresentativesTab />}
        {activeTab === "addresses" && <SpainAddressesTab />}
      </div>
    </div>
  );
}
