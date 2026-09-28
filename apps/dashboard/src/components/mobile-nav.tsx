"use client";

import * as React from "react";
import { Menu } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { IS_MOCK, SidebarBrand, SidebarNav } from "@/components/app-sidebar";
import { SystemPanel } from "@/components/system/system-panel";

export function MobileNav() {
  const [open, setOpen] = React.useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden" aria-label="Ouvrir le menu">
          <Menu />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="bg-sidebar text-sidebar-foreground w-72 gap-0 p-0">
        <SheetHeader className="sr-only">
          <SheetTitle>Navigation</SheetTitle>
          <SheetDescription>Sections du tableau de bord</SheetDescription>
        </SheetHeader>
        <SidebarBrand />
        <SidebarNav onNavigate={() => setOpen(false)} />
        {IS_MOCK ? null : <SystemPanel />}
      </SheetContent>
    </Sheet>
  );
}
