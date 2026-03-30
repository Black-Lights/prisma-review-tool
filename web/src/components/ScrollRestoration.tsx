"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

/**
 * Saves and restores scroll position for the <main> container.
 *
 * The app uses a scrollable <main> element (not window scroll),
 * so the browser's native scroll restoration doesn't work.
 * This component manually saves scroll position to sessionStorage
 * on scroll, and restores it when navigating back to a page.
 */
export default function ScrollRestoration() {
  const pathname = usePathname();

  useEffect(() => {
    const main = document.querySelector("main");
    if (!main) return;

    // Restore scroll position for this path
    const saved = sessionStorage.getItem(`scroll:${pathname}`);
    if (saved) {
      const pos = parseInt(saved, 10);
      // Use requestAnimationFrame to ensure DOM is painted
      requestAnimationFrame(() => {
        main.scrollTop = pos;
      });
    }

    // Save scroll position on scroll (debounced)
    let timer: ReturnType<typeof setTimeout>;
    const handleScroll = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        sessionStorage.setItem(`scroll:${pathname}`, String(main.scrollTop));
      }, 100);
    };

    main.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      clearTimeout(timer);
      main.removeEventListener("scroll", handleScroll);
    };
  }, [pathname]);

  return null;
}
