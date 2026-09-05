import type { NextConfig } from "next";

const httpBase = process.env.NEXT_PUBLIC_HTTP_BASE || "http://localhost:8000";
const quantHttp =
  process.env.NEXT_PUBLIC_QUANT_API_BASE ||
  process.env.NEXT_PUBLIC_QUANT_HTTP_BASE ||
  "http://localhost:8001";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return [
      {
        source: "/v1/:path*",
        destination: `${httpBase}/v1/:path*`,
      },
      {
        source: "/signals",
        destination: `${quantHttp}/signals`,
      },
      {
        source: "/signals/history",
        destination: `${quantHttp}/signals/history`,
      },
      {
        source: "/signals/:id",
        destination: `${quantHttp}/signals/:id`,
      },
      {
        source: "/performance/summary",
        destination: `${quantHttp}/performance/summary`,
      },
    ];
  },
};

export default nextConfig;
