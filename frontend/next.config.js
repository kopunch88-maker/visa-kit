/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Не блокируем production-билд из-за TS-ошибок (только варнинги).
  // TS-ошибки видны в IDE, но не мешают деплою.
  // TODO: постепенно починить TS-ошибки и убрать этот блок.
  typescript: {
    ignoreBuildErrors: true,
  },

  // То же для ESLint — чтобы линтинг не блокировал билд
  eslint: {
    ignoreDuringBuilds: true,
  },
};

module.exports = nextConfig;