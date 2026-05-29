import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  transpilePackages: ["@react-pdf/renderer"],
  experimental: {
    // Enable server actions
  },
};

export default nextConfig;
