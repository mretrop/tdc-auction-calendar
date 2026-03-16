---
name: wrap-up
description: End-of-session cleanup and handoff. Use this skill when the user says "wrap up", "let's wrap up", "end of session", "before I clear context", "session cleanup", or any indication they're done working and want to close out. Also use proactively when you notice the user is about to clear context or end a conversation. This skill ensures nothing is left dangling — CLAUDE.md stays lean and accurate, issues are closed or updated, worktrees are cleaned, and the next session has everything it needs to pick up where this one left off.
---

# Session Wrap-Up

Clean up, close out, and hand off at the end of every working session. The goal is to leave the project in a state where a fresh session (or a different person) can pick up immediately with zero lost context.

## Why This Matters

Without a deliberate wrap-up, sessions accumulate drift: CLAUDE.md gets stale, issues stay open when work is done, worktrees pile up, and the next session starts confused. This skill prevents that by making wrap-up a consistent, thorough habit.

## Process

Work through these areas in order. Skip any that don't apply to the current session.

### 1. CLAUDE.md Audit

Read the project's CLAUDE.md and check for:

**Accuracy:**
- Does it reflect the current state of the codebase? (e.g., if a new collector was added, is it mentioned in architecture notes?)
- Are there references to things that no longer exist? (removed files, renamed functions, old patterns)
- Are there contradictions? (e.g., says "uses LLM extraction" but the code was rewritten to use regex)

**Bloat prevention:**
- Remove anything that duplicates what's already obvious from the code or git history
- Remove implementation details that belong in code comments, not project-level docs
- Remove completed TODO items or progress notes that are now just noise
- Consolidate overlapping sections
- Keep it under ~150 lines. If it's longer, something probably doesn't belong there

**What belongs in CLAUDE.md vs elsewhere:**
- CLAUDE.md: build commands, architecture overview, conventions, key dependencies, domain notes
- NOT CLAUDE.md: step-by-step implementation details, debugging notes, per-issue progress, things derivable from `git log`

If changes are needed, make them and commit with message: `docs: update CLAUDE.md during session wrap-up`

### 2. Git Worktree & Branch Cleanup

Check for stale worktrees and branches:

```bash
git worktree list
git branch --list
```

**Clean up if:**
- A worktree's work has been merged — remove the worktree and delete the branch
- A branch has no corresponding worktree and its work is merged — delete the branch
- A worktree exists in `.worktrees/` but the branch is gone on remote — remove it

**Don't clean up if:**
- Work is in progress and not yet merged
- The user hasn't confirmed the work is complete

Run `git worktree prune` after removing any worktrees.

Also check for branches marked as gone on the remote:
```bash
git branch -vv | grep ': gone]'
```

### 3. GitHub Issues

For each issue that was worked on this session:

**If fully complete** (all acceptance criteria met, code merged, tests passing):
- Close the issue with `gh issue close <number> --comment "Completed in this session. <brief summary of what was done>"`

**If partially complete or blocked:**
- Add a comment with: what was done, what remains, any blockers or decisions needed
- `gh issue comment <number> --body "<status update>"`

**If new issues were discovered** during the session (bugs found, follow-up work identified, scope that was deferred):
- Create them: `gh issue create --title "<title>" --body "<description with context>"`
- Reference the parent issue if relevant

### 4. Next Steps & Context Handoff

Think about what the next session needs to know. This goes beyond just issues — it's about transferring your understanding.

**Check:**
- Is there a "next up" issue referenced in CLAUDE.md or the issue tracker? Verify it's still the right next step.
- Were any decisions made during this session that affect future work? (e.g., "we decided to use regex instead of LLM extraction for structured pages" — this might inform how the next collector is built)
- Are there any environment setup steps the next session will need? (new dependencies, env vars, etc.)

**If context needs to be passed forward:**
- Add a comment on the relevant GitHub issue
- Or update CLAUDE.md's progress section if it's project-wide context

### 5. Memory Update

Check if anything learned this session should be saved to the memory system:

- **User preferences** discovered (how they like to work, review style, communication preferences)
- **Project context** that isn't derivable from code (why a decision was made, external constraints, deadlines)
- **Feedback** the user gave about your approach (corrections, preferences for future sessions)
- **References** to external systems mentioned (tracking tools, dashboards, docs)

Don't duplicate what's already in CLAUDE.md or git history. Memory is for things that aren't captured elsewhere.

### 6. Skill Opportunities

Review what happened this session. Were there any multi-step workflows that:
- You repeated more than once?
- Required specific domain knowledge that would be useful to codify?
- Involved a pattern that would apply to other projects?

If so, suggest creating a skill to the user. Don't create it automatically — just flag it:
> "During this session, I noticed we [did X pattern] multiple times. This might be worth turning into a reusable skill. Want me to create one?"

## Completion

After working through all applicable sections, give the user a brief summary:
- What was cleaned up
- What issues were closed/updated
- What was passed forward to the next session
- Any suggested follow-ups

Keep the summary concise — a few bullet points, not paragraphs.
