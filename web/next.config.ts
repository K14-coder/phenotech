import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root to web/ so stray lockfiles higher up are never picked up.
  turbopack: { root: path.join(__dirname) },
  // Local isolated test servers only (e.g. NEXT_DIST_DIR=.data/next-e2e), so they never share .next with another server.
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
};

export default nextConfig;
