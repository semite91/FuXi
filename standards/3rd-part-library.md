--
name: 3rd-party-libraries
description: This file for 3rd party libraries. While adding or using 3rd party libraries, you must follow the instructions below
--

- Check the security risks of the library, whether it is the harness used or the 3rd party library that the user wants to add, according to the list below 
Is it installed from the official registry, not an arbitrary Git URL, tarball, or mirror? 
Last release and last commit dates: Abandoned libraries don't get security fixes. 
Regular releases suggest active upkeep. 
Open issues and PRs: Are security issues or vulnerability reports sitting unanswered? 
Is it marked deprecated, archived, or superseded? 
Is the version you'd install affected? Is a patched version available? 
Does installation fetch binaries or scripts from elsewhere? From where, and are they verified by checksum? 
Native code: Compiled extensions or prebuilt binaries are harder to audit. 
Does a library with no reason to talk to the network make outbound requests? 
Filesystem access: Reads or writes outside expected paths, especially home directory, SSH keys, cloud credentials, browser data. 
Environment access variable: Reading secrets or tokens it has no reason to touch. 
Minified or obfuscated code: Unexplained obfuscation in the published artifact is a serious red flag. 
Input handling: Does it validate and sanitize inputs? Is it prone to injection, path traversal, ReDoS, or unsafe parsing? 
Cryptography: Does it use well-vetted primitives and avoid custom crypto? Are defaults secure (modern algorithms, safe key sizes)? 
Secure defaults: Is the safe configuration the default, or must users opt in? 
Tests and CI: Is there meaningful test coverage and automated CI? 
Security tooling in the project: Dependabot/Renovate, CodeQL, fuzzing, OpenSSF Scorecard. 
Signed commitments and releases: Evidence of release integrity. 
Memory safety: For native or C/C++ code, how is memory safety addressed?
- Add third-party libraries to the `outsource` directory.
- If a library consists of multiple files, place them inside a folder with the same name as the library.
- When considering the addition of a third-party library, evaluate it based on the following criteria:
It does not increase the code's complexity (in terms of Big O notation).
It does not slow down the code compared to an implementation without the library—ideally, it should improve performance.
It does not introduce any security vulnerabilities.
- If you decide to use a third-party library, ensure its implementation aligns with the documentation for the installed version and follows industry best practices. 
When implementing the code, keep the following points in mind and explicitly state the best practices you have followed:
Use sources in this priority order:
1. A documentation tool (e.g., Context7 MCP) specific to the library and its version, if available. 
2. Official documentation websites, official README files, and any `docs/` or `examples/` directories within the repository. 
3. Official changelogs, release notes, and migration guides. 
4. Type definitions or the source code within the installed package (e.g., `node_modules/<pkg>`, `site-packages`) as the definitive reference for function signatures. 
5. Web searches, prioritizing official sources or those authored by the maintainers over blog posts or Q&A-style answers, which may be outdated. 
Check for breaking changes and deprecations:
- Review the changelog for the interval between the version you are familiar with and the target version. 
- Avoid deprecated or legacy APIs; use the replacements recommended by the maintainers. 
- When upgrading across a major version, follow the official migration guide. 
Identify the recommended patterns:
- Look for sections labeled "getting started," "recommended," or "best practices." 
- Favor the library's idiomatic approach over custom workarounds. 
- Prefer built-in features over writing your own solutions or adding another library that duplicates existing functionality. - Use secure and production-ready defaults (timeouts, error handling, validation, resource cleanup, connection reuse) as documented. 
- Match the conventions already used in this codebase when they don't conflict 
with the library's guidance. 
verify 
- Run type checks, linting, and tests after changes. 
- Run a minimal example if feasible to confirm the API behaves as documented. 
- Watch for depression warnings in the output and fix them. 
- Confirm the lockfile was updated and committed consistently. 

Do not rely on a tutorial unless it matches the installed major version.