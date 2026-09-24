import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const raisedButtonClass =
  "relative isolate bg-transparent pb-1 before:absolute before:inset-x-0 before:top-0 before:bottom-1 before:-z-10 before:rounded-[inherit] before:content-[''] active:translate-y-1 active:before:shadow-none"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border-0 bg-clip-padding text-sm font-medium whitespace-nowrap outline-none select-none transition-[background-color,color,transform,border-color,border-width,box-shadow] duration-100 focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          `${raisedButtonClass} text-white before:bg-[#58a700] before:shadow-[0_4px_0_#4a8a00] hover:before:bg-[#61bd00]`,
        blue:
          `${raisedButtonClass} text-white before:bg-[#1cb0f6] before:shadow-[0_4px_0_#1899d6] hover:before:bg-[#2bc1ff]`,
        yellow:
          `${raisedButtonClass} text-[#3c3c3c] before:bg-[#ffc800] before:shadow-[0_4px_0_#d7a900] hover:before:bg-[#ffd333]`,
        purple:
          `${raisedButtonClass} text-white before:bg-[#ce82ff] before:shadow-[0_4px_0_#a560d0] hover:before:bg-[#d996ff]`,
        outline:
          "relative isolate bg-transparent pb-0.5 text-foreground before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:bottom-0.5 before:z-0 before:translate-y-0.5 before:rounded-[inherit] before:bg-border before:content-[''] after:pointer-events-none after:absolute after:inset-x-0 after:top-0 after:bottom-0.5 after:z-10 after:rounded-[inherit] after:border-2 after:border-border after:bg-background after:content-[''] after:transition-[background-color,transform] after:duration-75 hover:after:bg-muted active:after:translate-y-0.5 aria-expanded:text-foreground aria-expanded:after:bg-muted dark:before:bg-[color-mix(in_oklab,var(--foreground)_15%,var(--background))] dark:after:border-[color-mix(in_oklab,var(--foreground)_15%,var(--background))] dark:after:bg-[color-mix(in_oklab,var(--foreground)_5%,var(--background))] dark:hover:after:bg-[color-mix(in_oklab,var(--foreground)_8%,var(--background))]",
        secondary:
          `${raisedButtonClass} text-[#4b4b4b] before:bg-[#e5e5e5] before:shadow-[0_4px_0_#c4c4c4] hover:before:bg-[#eeeeee] aria-expanded:before:bg-[#e5e5e5] dark:text-white dark:before:bg-[#59616d] dark:before:shadow-[0_4px_0_#3f4650] dark:hover:before:bg-[#66707d] dark:aria-expanded:before:bg-[#59616d]`,
        ghost:
          "hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:hover:bg-muted/50",
        destructive:
          `${raisedButtonClass} text-white before:bg-[#ff4b4b] before:shadow-[0_4px_0_#d33131] hover:before:bg-[#ff5c5c] focus-visible:ring-destructive/30`,
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  children,
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    >
      {variant === "outline" ? (
        <span
          data-slot="button-content"
          className="relative z-20 inline-flex items-center justify-center [gap:inherit] transition-transform duration-75 group-active/button:translate-y-0.5"
        >
          {children}
        </span>
      ) : (
        children
      )}
    </ButtonPrimitive>
  )
}

export { Button, buttonVariants }
