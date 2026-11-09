--
name: coding-standards
description: This file for my clean coding standards. While coding, you must follow the instructions below
--

- Naming conventions listed below. Contents that not mentioned should be camelCase.
  camelCase: variable, parameter,frontend methods
  PascalCase: class, backend methods, DTO, event, DB object, Enum
  UPPERCASE: const, constraint
  IPascalCase: Interface
  snake_case: frontend file name, folder name
- Don't use hardcoded expressions. Keep non configurable things at constraints
- Follow clean code principles listed below:
  Rely on SOLID, DRY, YAGNI
  Use small methods and full meaningful names
  Avoid duplication,  magic number
  Keep comments simple and small
- Design the infrastructure using design patterns. But first, ask me to ensure there are no conflicts with Clean Code principles like YAGNI and SOLID.
- Implement techniques listed below for high performance
  Analyze complexity of every method and optimize according to Big O Notation
  Don't skip dispose backend methods
  Control Stream, HttpResponseMessage, DbContext lifetime
  Don't fetch all data. First use pagination, projection or streaming
  Filter data at db side not backend side. To do this, use IQueryable
  Unless otherwise specified, use AsNoTracking during LINQ processes
  Use AsSplitQuery, if LINQ query's performance is better
  Avoid creating unnecessary LINQ chains
  Fix memory issues using without GC.Collect()
  If you use cache, define expiration, size limit, eviction policy
  Use StringBuilder during long, big string processes
  Avoid creating unnecessary DTO, objects
- Implement techniques listed below for secure app and ask questions if you need anything
  Don't keep secrets at project
  Use HTTPs
  If you take generic content from user like textarea, add input sanitization and prevent SQL injection attacks
  Implement CSP to prevent XSS attacks
  Create list activated SSRF protection
  Use antiforgery tokens to implement CSRF
- Test codes should separated with config added to env files