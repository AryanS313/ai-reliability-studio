import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'AI Reliability Studio',
  description: 'Review assistant answers against your sources, record findings, and compare replacement answers.',
  metadataBase: new URL('https://ai-reliability-studio.a3103.chatgpt.site'),
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
