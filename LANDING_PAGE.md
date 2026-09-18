# AI Stack landing page

## Design direction
Modular Playground. Palette: Cobalt, acid yellow, ink, and porcelain. The hero uses authored CSS 3D transforms and SVG/CSS 2D motion. This is a static visual illustration, not live telemetry or an interactive backend demo.

## Content and scope
Project positioning is grounded in the repository README inspected on 2026-09-18. No performance, savings, uptime, or adoption claims are added. Root `index.html` is a dependency-free landing page. No application service, credentials, or backend routes are changed.
The previous root index is preserved in status.html with a snapshot notice and a link from the new page. Its historical status claims have not been independently verified.

## Local preview
From this repository root, run `python3 -m http.server 8080` and open `http://localhost:8080`. No package installation or build step is required.

## Motion and accessibility
The page respects `prefers-reduced-motion`, offers a motion pause button, has visible keyboard focus, semantic sections, a skip link, and hides decorative art from assistive technology. The content and navigation work without JavaScript. Mobile uses a single-column layout. No remote fonts, images, libraries, or analytics are requested.

## Publishing
This change supplies static source only. Review and merge before enabling or changing hosting. No deployment workflow is introduced.

## Verification
JavaScript syntax, unique IDs, one main heading, internal anchor targets, local linked-file existence, and the presence of reduced-motion/pause support were checked. Browser screenshots and runtime interaction checks could not run because Chromium is absent and its download did not complete. Visual review on desktop and mobile remains required before merging.
