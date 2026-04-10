import nextra from 'nextra'

const withNextra = nextra({})

const isGhPages = process.env.GITHUB_PAGES === 'true'

export default withNextra({
  output: isGhPages ? 'export' : 'standalone',
  basePath: isGhPages ? '/kaizen' : '',
  images: isGhPages ? { unoptimized: true } : undefined,
  reactStrictMode: true,
})
