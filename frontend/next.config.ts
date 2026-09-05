import type { NextConfig } from "next";

const httpBase = process.env.NEXT_PUBLIC_HTTP_BASE || "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/v1/:path*",
        destination: `${httpBase}/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
