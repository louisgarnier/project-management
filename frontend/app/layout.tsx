import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Call Tracker",
  description: "Turn client call recordings into structured artifacts and a living topic dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
