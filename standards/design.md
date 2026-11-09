--
name: design
description: This file for my design standards. While designing, you must follow the instructions below
--

- Use LESS as the dynamic preprocessor stylesheet language.
- Add the fonts and font sizes used in the project to a file named `typography.less` within the `wwwroot/src/css` directory. 
This file should be parametric, allowing for modes such as `big-font` or `small-font` when imported into the project's main stylesheet.
- Add the colors used in the project to a file named `color.less` within the `wwwroot/src/css` directory. 
This file should be parametric, allowing for modes such as `dark` or `light` when imported into the project's main stylesheet.
- Add the borders used in the project to a file named `border.less` within the `wwwroot/src/css` directory.
This file should define the `border`, `border-radius`, and `box-shadow` values ​​used across components.
- Ensure consistent spacing throughout the pages; define these spacing values ​​in a file named `spaces.less` within the `wwwroot/src/css` directory.
- Organize and store images within the `wwwroot/src/image` directory.

- Architectural decisions must be determined by the "Google Modern Web Guidance" MCP (Model Context Protocol).
- When making these decisions, the "Google Modern Web Guidance" should leverage "UI/UX Pro Max" skills.

- Define component styles in a separate file located within the same directory as the component itself. No CSS code should be present within the component's HTML or TypeScript files.
- All design-related files for a component must reside within the component's own directory.

- Designs will be created using "Claude Design."
- If "Claude Code" is being used for development, retrieve designs via the `/design-sync` skill. Otherwise, reference the designs from the specified location.