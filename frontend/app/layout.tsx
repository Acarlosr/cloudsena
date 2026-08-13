import type { Metadata } from "next";

import Sidebar from "@/components/Sidebar";
import MobileNav from "@/components/MobileNav";
import "./globals.css";

// Fontes do sistema por escolha: o CloudSena roda local, muitas vezes sem
// internet. Nada de buscar webfonts em tempo de build ou de carregamento.

export const metadata: Metadata = {
  title: "CloudSena — Biblioteca inteligente de vídeos",
  description:
    "Transforme sua biblioteca de vídeos e cursos em um segundo cérebro pesquisável, com respostas rastreáveis até o minuto exato.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen">
        <Sidebar />
        <MobileNav />
        <main className="lg:pl-[248px]">
          <div className="mx-auto max-w-[1400px] px-5 pb-24 pt-6 sm:px-8 lg:pt-10">{children}</div>
        </main>
      </body>
    </html>
  );
}
