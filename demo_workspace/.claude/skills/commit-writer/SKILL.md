---
name: commit-writer
description: Writes a Conventional Commits message (type(scope): subject, body, footer) from a description of a change or a diff. Use when asked to write, draft or suggest a commit message.
---

# Conventional commit writer

License: MIT. Part of agent-router (https://github.com/usathyan/agent-router).

Write one commit message for the change the user describes or the diff they provide.
Do not run `git commit`, stage files, or push; only produce the message.

## Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

1. **type**: one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`,
   `ci`, `chore`, `revert`. Pick `feat` for new user-facing behaviour, `fix` for bug fixes.
2. **scope** (optional): the area changed, in lowercase, e.g. `auth`, `api`, `checkout`.
   Omit the parentheses if there is no clear scope.
3. **subject**: imperative mood ("add", not "added"), lowercase first word, no trailing
   period, at most 72 characters including the prefix.
4. **body** (optional): wrap at 72 columns. Explain what changed and why, not how. Leave it
   out for trivial changes.
5. **footer** (optional): `BREAKING CHANGE: <description>` for incompatible changes (and add
   `!` after the type/scope, e.g. `feat(api)!:`), and issue references such as `Refs: #123`.

## Steps

1. Read the description or diff and identify the single main intent of the change.
2. Choose the type and scope from that intent. If the change mixes unrelated intents, say so
   and suggest splitting it, then still give the best single message.
3. Write the subject, then a short body only if the reason is not obvious from the subject.
4. Return the message in a fenced code block with nothing else inside it.

## Example

Input: "fixed the login page timing out after 5 minutes even with remember me checked"

```
fix(auth): honour "remember me" in login session timeout

Sessions created with "remember me" expired after the default
5-minute idle timeout. Use the extended timeout for those sessions.
```
