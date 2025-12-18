import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone',
  // Disable request logging in production
  logging: false,
};

export default nextConfig;
