/** @type {import('next').NextConfig} */
const isExport = process.env.EXPORT_MODE === "1";

const nextConfig = isExport
  ? { output: "export", images: { unoptimized: true }, env: { NEXT_PUBLIC_API: "" } }
  : {
      async rewrites() {
        return [{ source: "/api/:path*", destination: "http://127.0.0.1:7860/api/:path*" }];
      },
      async headers() {
        return [{
          source: "/:path*",
          headers: [
            { key: "X-Content-Type-Options", value: "nosniff" },
            { key: "X-Frame-Options", value: "DENY" },
            { key: "Referrer-Policy", value: "same-origin" },
          ],
        }];
      },
    };

export default nextConfig;
