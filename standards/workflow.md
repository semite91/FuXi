-- 
name: workflow
description: This file is for define my coding workflow. 
--

Some steps are manual to don't skip anything and make sure everything continues correct. Please, follow my workflow as shown below and make sure it's proceeding correctly. Ask questions if you need anything.

# PLAN AND CODE
1. My workflow will be using Test Driven Development.
2. First, i will give you requirements and you will create test scenarios shredding to atomic processes.
3. Every test scenarios should be created at related Github issue. There will not be individual test scenario issue.
4. Save test scenarios at infrastructure/test folder with test_scenarios_YYYY_MM_DD_hh_mm name and txt format.
5. I will confirm scenarios manually.
6. Create the technical documentation of request and code according to the standards.md file located in the same folder as this file.
 
Constraints
7. If model need to do same thing, limit count is 3.


# TOKEN USAGE
When model's session's token is running out, i will implement this prompts to continue my work. If the model can warn about its own slowdown, let it do so.
This prompt will be past to new session:
Continue my work from the previous session; its token ran out. Start read-only: orient first, change nothing until I approve a plan. I will paste the handoff in numbered parts — acknowledge each part by number, and start no work until I say complete. Build two lists from my handoff: files READ (content known) and files CITED-BUT-UNREAD (name only). Output both lists back to me, then ask me for every unread file's content; never state, quote, or assume contents of a file you have not read. Read  instruction/standards.md and instruction/coding_standards.md first and obey them, especially asking before multi-file changes. Re- verify git status, diffs, and issue state yourself with read-only commands; inherited claims are leads, not facts. Where your fresh evidence contradicts the handoff, trust the evidence and report the mismatch. Ask about anything missing or ambiguous: uncommitted work and its disposition, open todos with exact status, whether I am editing files alongside you right now, and environment blockers. Do not commit, push, close issues, or start work until I confirm the transfer is complete. Keep every answer short, simple, and in complete sentences.

Say to the OLD session before leaving:
Summarize this session for transfer in numbered parts, one topic each: goal, current state with evidence, files read versus files merely cited, open todos with exact status and blockers, full git status plus git diff --stat, untracked files and their purpose, environment facts (venv, weights, branches, tool quirks, known flakes with workarounds), decisions with rationale, what was deliberately left undone, and open questions. Include no secrets, keys, or credentials. Keep it compact enough to paste in parts.

# REVIEW AND TEST
8. Verify the correctness of the code by checking the requests in the `test_scenarios` file within the modified folder. Alert me if you cannot find it.
9. Save test results at test_scenarios folder with name and date as a txt file separately.
10. List required changes to terminal as SRS.
11. Implement changes to code.
12. Verify correctness like 6th step.
13. Repeat between 7th and 10th step until there is no error.
14. Test code quality using alibaba's OpenCodeReview tool.
15. Repeat 11th step.

# PR
16. Add last accepted documentation as an SRS to PR's description.
17. When user finishes coding, all diffences should be commited. User will track improvements.

# RESPONSE FORMATS
- If there is code changes, template should be like this:
    - <File Name>:
    <Change>:
    <Cause>:
    - <File Name>:
    <Change>:
    <Cause>:
    - <Change skeleton> (change map via visualization)
- If there are changing at specific location:
    - <Change>:
      <Cause>