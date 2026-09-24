<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## shadcn/ui-first design rules

- Build the website from shadcn/ui components whenever an appropriate component exists.
- At the beginning of every design or UI implementation request, first plan which shadcn/ui components are appropriate for each part of the interface.
- Check the components already available in `components/ui` before implementing the design. If a required shadcn/ui component is missing, install it through the shadcn CLI and then use the installed component.
- Do not recreate a component with custom markup when shadcn/ui already provides a suitable component.
- Once a shadcn/ui component is used, preserve its natural default appearance and behavior. Do not customize its shape, colors, typography, borders, radius, shadows, visual styles, animations, or effects. Use only its default implementation, documented props, and built-in variants.
- Do not modify files in `components/ui` to restyle shadcn/ui components for a page-specific design.
- Use Tailwind CSS normally on page, section, and wrapper elements for layout concerns such as grid, flexbox, spacing, sizing, alignment, positioning, and responsive behavior. Layout utilities must not override the visual appearance or effects of nested shadcn/ui components.