import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import BottomNav from "@/components/BottomNav";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "coin_bot 대시보드",
  description: "AI 암호화폐 자동매매 대시보드",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className={`${inter.className} bg-gray-950 text-white min-h-screen`}>
        <main className="max-w-lg mx-auto pb-20 px-4">{children}</main>
        <BottomNav />
      </body>
    </html>
  );
}
