import type { NextConfig } from "next";

const isDevelopment = process.env.NODE_ENV === "development";
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "");

const nextConfig: NextConfig = {
  allowedDevOrigins: ["10.70.22.170", "192.168.68.144"],
  ...(isDevelopment
    ? {
        async rewrites() {
          if (!backendUrl) return [];
          return [
            {
              source: "/api/:path*/",
              destination: `${backendUrl}/api/:path*`,
            },
          ];
        },
      }
    : { output: "export" as const }),
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
