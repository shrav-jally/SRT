import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Deloitte Touchless Valuation TV 1",
  description:
    "Three-approach triangulated valuation (Income · Market · Asset) on real published multiples across the Indian listed universe.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="digital h-full antialiased">
      <body className="min-h-full flex flex-col">
        {/* Deloitte DDS Header (Section 5.8) */}
        <header className="dds-header">
          <div className="dds-header__logo">
            {/* Deloitte wordmark SVG — per DDS, green dot + "Deloitte" in white */}
            <svg viewBox="0 0 200 40" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ height: 28, width: "auto" }}>
              <circle cx="12" cy="20" r="6" fill="#86BC25" />
              <text x="26" y="26" fill="white" fontFamily="Open Sans, sans-serif" fontWeight="700" fontSize="18">Deloitte</text>
            </svg>
          </div>
          <span className="dds-header__project-name">Deloitte Touchless Valuation TV 1</span>
        </header>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
