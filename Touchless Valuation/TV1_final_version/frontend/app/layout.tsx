import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Touchless Valuation Platform",
  description:
    "Touchless MSME valuation with listed search, guided intake, annual-report extraction, and board-ready reports.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="digital h-full antialiased">
      <body className="min-h-full flex flex-col">
        <header className="dds-header">
          <div className="dds-header__logo">
            <span style={{ fontWeight: 700, fontSize: '1.25rem', letterSpacing: '-0.02em' }}>Deloitte<span style={{ color: '#86BC25' }}>.</span></span>
          </div>
          <div className="dds-header__project-name">
            Touchless Valuation
          </div>
        </header>
        <div className="flex-1 flex flex-col">{children}</div>
      </body>
    </html>
  );
}
