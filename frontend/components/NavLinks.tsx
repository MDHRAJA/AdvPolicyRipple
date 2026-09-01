'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const links = [
  { href: '/planner', label: 'AI Planner' },
  { href: '/simulate', label: 'Simulator' },
  { href: '/results', label: 'Results' },
  { href: '/scenarios', label: 'Scenarios' },
  { href: '/evidence', label: 'Chennai data' },
  { href: '/map', label: 'Ward map' },
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
