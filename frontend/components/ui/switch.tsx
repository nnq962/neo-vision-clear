"use client"

import { Switch as SwitchPrimitive } from "@base-ui/react/switch"
import { cn } from "cn"

function Switch({
  className,
  size = "default",
  ...props
}: SwitchPrimitive.Root.Props & {
  size?: "sm" | "default"
}) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      data-size={size}
      className={cn(
        "peer group/switch relative inline-flex shrink-0 items-center rounded-full border-2 outline-none transition-[background-color,border-color,transform] duration-100 after:absolute after:-inset-x-3 after:-inset-y-2 focus-visible:ring-3 focus-visible:ring-ring/50 active:translate-y-0.5 active:drop-shadow-none aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 data-[size=default]:h-6 data-[size=default]:w-11 data-[size=sm]:h-5 data-[size=sm]:w-9 data-checked:border-[#4a8a00] data-checked:bg-[#58a700] data-checked:drop-shadow-[0_2px_0_#4a8a00] data-checked:active:drop-shadow-none data-unchecked:border-[#c4c4c4] data-unchecked:bg-[#e5e5e5] data-unchecked:drop-shadow-[0_2px_0_#c4c4c4] data-unchecked:active:drop-shadow-none data-disabled:cursor-not-allowed data-disabled:opacity-50 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 dark:data-unchecked:border-[#3f4650] dark:data-unchecked:bg-[#59616d] dark:data-unchecked:drop-shadow-[0_2px_0_#3f4650] dark:data-unchecked:active:drop-shadow-none",
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none ml-0.5 block rounded-full bg-white ring-1 ring-black/10 transition-transform duration-100 group-data-[size=default]/switch:size-4 group-data-[size=sm]/switch:size-3 group-data-[size=default]/switch:data-checked:translate-x-5 group-data-[size=sm]/switch:data-checked:translate-x-4 group-data-[size=default]/switch:data-unchecked:translate-x-0 group-data-[size=sm]/switch:data-unchecked:translate-x-0"
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
