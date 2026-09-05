import type { NextConfig } from "next";

const httpBase = process.env.NEXT_PUBLIC_HTTP_BASE || "http://localhost:8000";
const quantHttp =
  process.env.NEXT_PUBLIC_QUANT_HTTP_BASE || httpBase;

const nextConfig: NextConfig = {
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
        source: "/signals/:id",
        destination: `${quantHttp}/signals/:id`,
      },
    ];
  },
};

export default nextConfig;
