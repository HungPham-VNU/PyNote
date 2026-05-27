import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // The API runs on a different origin in dev; rewrites let us call /api/* paths
  // from the browser and proxy them, avoiding CORS preflight on every call.
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [
      { source: "/api/v1/:path*", destination: `${apiUrl}/api/v1/:path*` },
      { source: "/healthz", destination: `${apiUrl}/healthz` },
    ];
  },
};

export default config;
