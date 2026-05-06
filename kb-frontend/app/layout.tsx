import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import "@copilotkit/react-ui/styles.css";
import { Brain } from "lucide-react";

import { AuthProvider } from "@/components/providers/AuthProvider";
import { NavLinks } from "@/components/NavLinks";
import { DemoModeBanner } from "@/components/DemoModeBanner";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "KnowledgeForge",
  description: "Knowledge Base Agent powered by ADK and CopilotKit",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} min-h-screen bg-[var(--background)] text-[var(--foreground)] antialiased transition-colors duration-300 selection:bg-orange-500/30`}>
        <DemoModeBanner />
        <AuthProvider>
          <div className="flex min-h-screen flex-col">
            {/* Navbar Globale */}
            <header className="sticky top-0 z-50 w-full border-b border-[var(--card-border)] bg-[var(--background)]/80 backdrop-blur">
              <div className="container mx-auto flex h-14 items-center gap-6 px-4">
                <div className="font-bold text-lg flex items-center gap-2 shrink-0">
                  <Brain className="w-5 h-5 text-orange-500" />
                  <span className="text-orange-500">Knowledge</span><span className="text-blue-500">Forge</span>
                </div>
                <NavLinks />
              </div>
            </header>
            
            {/* Contenuto di pagina */}
            <main className="flex-1">
              {children}
            </main>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
