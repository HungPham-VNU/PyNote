import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "PyNote — Research Workspace",
  description: "A NotebookLM-style RAG application.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider
      appearance={{
        variables: {
          colorBackground: "#1c1b1c",
          colorText: "#e5e2e3",
          colorTextSecondary: "#c2c6d6",
          colorPrimary: "#4d8eff",
          colorTextOnPrimaryBackground: "#00285d",
          colorInputBackground: "#201f20",
          colorInputText: "#e5e2e3",
          colorNeutral: "#e5e2e3",
          colorDanger: "#f87171",
          colorSuccess: "#4edea3",
          colorWarning: "#fcd34d",
          borderRadius: "0.5rem",
        },
        elements: {
          rootBox: { colorScheme: "dark" },
          card: { backgroundColor: "#1c1b1c", border: "1px solid #2a2a2b" },
          headerTitle: { color: "#e5e2e3" },
          headerSubtitle: { color: "#c2c6d6" },
          formFieldLabel: { color: "#e5e2e3" },
          formFieldHintText: { color: "#8c909f" },
          formFieldInput: { color: "#e5e2e3", backgroundColor: "#201f20" },
          formFieldInputShowPasswordButton: { color: "#c2c6d6" },
          formButtonPrimary: { color: "#00285d", fontWeight: 600 },
          socialButtonsBlockButton: {
            borderColor: "#424754",
            color: "#e5e2e3",
          },
          socialButtonsBlockButtonText: { color: "#e5e2e3" },
          dividerLine: { backgroundColor: "#2a2a2b" },
          dividerText: { color: "#8c909f" },
          footerActionText: { color: "#c2c6d6" },
          footerActionLink: { color: "#4d8eff" },
          identityPreviewText: { color: "#e5e2e3" },
          identityPreviewEditButton: { color: "#adc6ff" },
          formResendCodeLink: { color: "#adc6ff" },
        },
      }}
    >
      <html lang="en" className="dark">
        <head>
          <link rel="preconnect" href="https://fonts.googleapis.com" />
          <link
            rel="preconnect"
            href="https://fonts.gstatic.com"
            crossOrigin=""
          />
          <link
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
            rel="stylesheet"
          />
        </head>
        <body className="min-h-screen bg-[#131314] text-[#e5e2e3] antialiased">
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
