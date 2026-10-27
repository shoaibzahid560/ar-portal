import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },

  /** The home page opens the dashboard. */
  async redirects() {
    return [{ source: "/", destination: "/dashboard", permanent: false }];
  },

  /**
   * The browser only talks to this domain. Requests to /api/* are forwarded to the
   * FastAPI project, so the session cookie stays first-party.
   * API_ORIGIN is set per environment in Vercel (and in .env.local for development).
   */
  async rewrites() {
    const apiOrigin = process.env.API_ORIGIN;
    if (!apiOrigin) return [];
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
};

export default nextConfig;
