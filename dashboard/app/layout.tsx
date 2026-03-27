import type { Metadata } from "next";
import { Space_Grotesk } from "next/font/google";
import "./globals.css";
import BottomNav from "@/components/BottomNav";

const font = Space_Grotesk({ subsets: ["latin"], weight: ["400", "500", "600", "700"] });

export const metadata: Metadata = {
  title: "COIN_BOT",
  description: "AI 암호화폐 자동매매 대시보드",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className={`${font.className} min-h-screen`} style={{ background: "#080808", color: "#e0e0e0" }}>
        <main className="max-w-lg mx-auto pb-24 px-4">{children}</main>
        <BottomNav />
      </body>
    </html>
  );
}
