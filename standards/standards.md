--
name: standards
description: This file is for define my coding process standards. Develop the code according to the following commands. Ask questions if you need anything.
--


#DO
- Before doing anything, create separate agents for the backend, frontend, test, code review processes.
- These agents should be communicate if there is an event that effect each other.
- Show result of sub agents' communications as an summary  from terminal and ask sub agents' decision to user which means me.
- Shred requests, code review results, test results to atomic processes. Atomic means action that has one purpose. Example: toggle enable submit button is request, chainging of button's visual and activating clickability of button are atomic processes. 
- Before coding process, plan with Matt Pocock's grill-with-docs skill. If this skill is not loaded, load first.
- Regarding code quality, prioritize /coding-standards skill, alongside your own knowledge. 
- If there are any discrepancies between your knowledge and /coding-standards skill follow the instructions in /coding-standards.
- Final responses should become from full and complete sentences.
- If you need to add or use 3th party libraries, please refer to the /3rd-party-libraries skill. If this skill does not exist, ask me first.

#DONT
- If you need to change or add codes to multiple files, ask before.