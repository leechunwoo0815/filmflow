/** @type {import('next').NextConfig} */
const isExport = process.env.EXPORT_MODE === "1";

// 本机全生命周期产品不外呼：Next 的遥测（版本检查同一条路径）会连 Vercel 端点。
// 关掉它不是洁癖——FR-41 判据③"进程无外部请求"要能对整个工作台成立，
// 而 e2e_fr40_keyboard.py 的 lsof 检查就是按 pid 断言这一点的。
const telemetry = { enabled: false };

const nextConfig = isExport
  ? { output: "export", images: { unoptimized: true }, env: { NEXT_PUBLIC_API: "" }, telemetry }
  : {
      telemetry,
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
