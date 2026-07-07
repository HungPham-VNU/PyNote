"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

/** Debounced title search — updates ?q= so the server component re-fetches. */
export function NotebookSearch({ initialQuery }: { initialQuery: string }) {
  const router = useRouter();
  const [value, setValue] = useState(initialQuery);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const t = setTimeout(() => {
      const q = value.trim();
      router.replace(q ? `/dashboard?q=${encodeURIComponent(q)}` : "/dashboard");
    }, 300);
    return () => clearTimeout(t);
  }, [value, router]);

  return (
    <input
      type="search"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      placeholder="Search notebooks by name…"
      aria-label="Search notebooks by name"
      className="w-full rounded-xl border border-[#424754] bg-[#201f20] px-4 py-2.5 text-sm text-[#e5e2e3] placeholder:text-[#8c909f] focus:border-[#4d8eff] focus:outline-none focus:ring-2 focus:ring-[#4d8eff]/30"
    />
  );
}
