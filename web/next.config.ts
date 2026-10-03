import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root to web/ so stray lockfiles higher up are never picked up.
  turbopack: { root: path.join(__dirname) },
};

export default nextConfig;
