"use client"

import * as React from "react"
import Link from "next/link"
import {
  CameraIcon,
  ChartNoAxesCombinedIcon,
  FocusIcon,
  ScanLineIcon,
  SettingsIcon,
} from "lucide-react"

import { NavMain } from "@/components/nav-main"
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

const data = {
  navMain: [
    {
      title: "Tổng quan",
      url: "/overview",
      icon: <ChartNoAxesCombinedIcon />,
    },
    {
      title: "Camera",
      url: "/cameras",
      icon: <CameraIcon />,
    },
    {
      title: "Calibration",
      url: "/calibration",
      icon: <FocusIcon />,
    },
    {
      title: "Cài đặt",
      url: "/settings",
      icon: <SettingsIcon />,
    },
  ],
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar variant="inset" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link href="/overview" />}>
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <ScanLineIcon className="size-4" />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium">Neo Vision Clear</span>
                <span className="truncate text-xs">Walkway Monitor</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
      </SidebarContent>
    </Sidebar>
  )
}
