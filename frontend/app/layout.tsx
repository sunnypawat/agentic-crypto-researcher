import "./globals.css";

export const metadata = {
  title: "Agentic Crypto Researcher",
  description: "MVP chat UI for the FastAPI crypto research agent."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}


