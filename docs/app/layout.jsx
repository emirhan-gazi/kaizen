import { Footer, Layout, Navbar } from 'nextra-theme-docs'
import { Head } from 'nextra/components'
import { getPageMap } from 'nextra/page-map'
import 'nextra-theme-docs/style.css'

const basePath = process.env.GITHUB_PAGES === 'true' ? '/kaizen' : ''

export const metadata = {
  title: 'Kaizen',
  description: 'CI/CD for LLM prompts — automatic optimization and delivery'
}

export default async function RootLayout({ children }) {
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning>
      <Head />
      <body>
        <Layout
          navbar={<Navbar logo={<span style={{display:'flex',alignItems:'center',gap:'8px'}}><img src={`${basePath}/kaizen.png`} alt="Kaizen" style={{height:'28px'}} /><b>Kaizen</b></span>} />}
          pageMap={await getPageMap()}
          docsRepositoryBase="https://github.com/emirhan-gazi/kaizen"
          footer={<Footer>MIT {new Date().getFullYear()} Kaizen</Footer>}
        >
          {children}
        </Layout>
      </body>
    </html>
  )
}
