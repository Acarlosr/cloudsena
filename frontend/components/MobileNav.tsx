"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cx } from "@/lib/format";

const NAV = [
  { href: "/", label: "Painel", icon: "◆" },
  { href: "/biblioteca", label: "Biblioteca", icon: "▤" },
  { href: "/perguntar", label: "Perguntar", icon: "✧" },
  { href: "/fila", label: "Fila", icon: "⟳" },
  { href: "/conexoes", label: "IA", icon: "⌁" },
];

export default function MobileNav() {
  const pathname = usePathname();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-white/[.08] bg-ink-900/90 backdrop-blur-xl lg:hidden">
      <div className="flex">
        {NAV.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cx(
                "flex flex-1 flex-col items-center gap-1 py-2.5 text-[10px] transition",
                active ? "text-accent-soft" : "text-slate-500",
              )}
            >
              <span className="text-sm">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
