import type { NextConfig } from "next";

const isDevelopment = process.env.NODE_ENV === "development";
const lanIp = process.env.NVC_LAN_IP?.trim();
const backendUrl = (
  process.env.BACKEND_UPSTREAM ?? process.env.NEXT_PUBLIC_BACKEND_URL
)?.replace(/\/$/, "");
const mediaMtxUrl = (
  process.env.MEDIAMTX_UPSTREAM ?? "http://127.0.0.1:8889"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  ...(isDevelopment && lanIp ? { allowedDevOrigins: [lanIp] } : {}),
  ...(isDevelopment
    ? {
        async rewrites() {
          const rules = [
            {
              source: "/webrtc/:path*/",
              destination: `${mediaMtxUrl}/:path*/`,
            },
          ];
          if (backendUrl) {
            rules.unshift({
              source: "/api/:path*/",
              destination: `${backendUrl}/api/:path*`,
            });
          }
          return rules;
        },
      }
    : { output: "export" as const }),
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
