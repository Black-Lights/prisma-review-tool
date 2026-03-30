import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { Sidebar } from "@/components/Sidebar";
import ScrollRestoration from "@/components/ScrollRestoration";
import TutorialOverlay from "@/components/Tutorial";

export const metadata: Metadata = {
  title: "PRISMA Review Tool",
  description: "AI-assisted systematic literature review following PRISMA 2020",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0"
          rel="stylesheet"
        />
      </head>
      <body className="h-full" style={{ fontFamily: "'DM Sans', system-ui, sans-serif" }}>
        <Providers>
          <div className="flex h-full">
            <Sidebar />
            <main className="flex-1 ml-64 overflow-y-auto p-8">
              <ScrollRestoration />
              {children}
            </main>
            <TutorialOverlay />
          </div>
        </Providers>
      </body>
    </html>
  );
}
