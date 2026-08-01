import type { NextConfig } from "next";

// Two modes:
//  * dev (`npm run dev`): rewrites proxy /api/* to the FastAPI backend on :8000
//  * static build (`BUILD_STATIC=1 npm run build`): emits a fully static site
//    into `out/`, which the Python backend serves same-origin (so /api/* hits
//    FastAPI directly and no Node is needed at runtime — `python run.py` only)
const isStatic = !!process.env.BUILD_STATIC;

const nextConfig: NextConfig = {
  // Use relative path for cross-platform compatibility.
  turbopack: {},
  ...(isStatic
    ? { output: "export" as const }
    : {
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: "http://localhost:8000/api/:path*",
            },
          ];
        },
      }),
};

export default nextConfig;
