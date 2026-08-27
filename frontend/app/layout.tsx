import Link from 'next/link';
import NavLinks from '@/components/NavLinks';
import './globals.css';

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="site-nav">
            <Link href="/" className="brand">POLICY<span>FORGE</span></Link>
            <NavLinks />
          </div>
        </header>
        {children}
        <footer className="site-footer">
          <div><b>PolicyForge</b><span> · Chennai-calibrated policy simulation</span></div>
          <div>Built by Mahadevan Rajagopalan, Asvath M, Sanjit S, Krish Muralidharan &amp; Sai retheka</div>
          <span>Decision support, not a real-world forecast.</span>
        </footer>
      </body>
    </html>
  );
}
