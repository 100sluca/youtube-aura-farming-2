"use client";

import { usePathname } from "next/navigation";

import { pageTitle } from "@/components/nav-items";

export function PageTitle() {
  const pathname = usePathname();
  return <h1 className="truncate text-base font-semibold md:text-lg">{pageTitle(pathname)}</h1>;
}
