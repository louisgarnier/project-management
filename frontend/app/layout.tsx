import type { Metadata } from "next";
import "./globals.css";
import TopNav from "@/components/TopNav";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "Call Tracker",
  description: "Turn client call recordings into structured artifacts and a living topic dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body suppressHydrationWarning className="h-full flex flex-col overflow-hidden">
        <TopNav />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-auto bg-white">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
