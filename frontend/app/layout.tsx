import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AirAlert Monitor — monitoring publicznych komunikatów",
  description:
    "To nie jest oficjalny system alarmowania. Monitoring publicznych komunikatów i wskaźników ryzyka (OSINT).",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pl">
      <body>{children}</body>
    </html>
  );
}
