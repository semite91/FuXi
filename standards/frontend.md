--
name: frontend-standards
description: This file for my frontend coding standards. While coding, you must follow the instructions below
--

- Never create a component without asking first.
- I will specify which components to create. If you notice any gaps in terms of design or functionality, or if you identify a need for additional components, please ask.
- Create components within the `/wwwroots/src/components` directory of the project.
- Place each component inside a folder bearing its own name.
- If a required task can be accomplished using a library already included in the project, use that library instead of writing new code. 
For example: If you need a button with a hover effect and a frontend library (e.g., "vow") already provides a "button" component, use that.
- Design all elements to be reusable.
- Do not include hardcoded values ​​within components.
- Do not include business logic within components.
- If you need to create a service specifically for a component, place it within the same folder as that component.
- Never place API calls directly inside a component; use a separate service file instead. 
Always ask which API file you should add a call to, or whether you need to create a new one.