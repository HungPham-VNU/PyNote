import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "PyNote",
  description: "A NotebookLM-style RAG application.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className="min-h-screen bg-neutral-50 text-neutral-900 antialiased">
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
