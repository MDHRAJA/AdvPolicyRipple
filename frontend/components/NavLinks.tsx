'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const links = [
  { href: '/simulate', label: 'Simulator' },
  { href: '/results', label: 'Results' },
  { href: '/scenarios', label: 'Scenarios' },
  { href: '/learning', label: 'Learning' },
  { href: '/evidence', label: 'Chennai data' },
  { href: '/about', label: 'About' },
];

export default function NavLinks() {
  const pathname = usePathname();
  return (
    <nav>
      {links.map((link) => (
        <Link key={link.href} href={link.href} className={pathname?.startsWith(link.href) ? 'active' : ''}>
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
