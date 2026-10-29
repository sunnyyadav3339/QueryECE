import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

// Apple devices use SF Pro via -apple-system; Inter is the closest match elsewhere.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "QueryECE — IIT Roorkee ECE Assistant",
  description: "Ask anything about the Department of Electronics & Communication Engineering, IIT Roorkee.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="h-full font-sans">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
