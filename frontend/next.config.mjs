/** @type {import('next').NextConfig} */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig = {
  // Eksport statyczny (GitHub Pages / demo). Produkcja z backendem: usun output
  // i ustaw NEXT_PUBLIC_API_URL na adres API.
  ...(process.env.NEXT_PUBLIC_DEMO_MODE === "1"
    ? { output: "export", basePath, images: { unoptimized: true } }
    : {}),
};

export default nextConfig;
