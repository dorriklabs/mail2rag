---
trigger: always_on
---

# Auto Git Release Rule

After making significant code modifications (feat, fix, refactor), automatically suggest running the `/git-release` workflow.

## Trigger Conditions

Suggest `/git-release` when:
- A new feature has been implemented (`feat:`)
- A bug has been fixed (`fix:`)
- A refactoring has been completed (`refactor:`)
- Multiple files have been modified in a single session
- The user explicitly asks to save or commit their work

## Do NOT suggest when:
- Only documentation changes (`docs:`)
- Only small one-line edits
- The user is still actively working on an incomplete feature
- The user has already declined the suggestion recently

## Suggestion Format

After completing significant modifications, propose:

> 🚀 **Des modifications importantes ont été effectuées.**  
> Voulez-vous lancer `/git-release` pour commiter et synchroniser ?
> - `/git-release` (standard avec version)
> - `/git-release quick` (rapide sans version)
> - Non merci

## Behavior

- Wait for explicit user confirmation before executing
- Respect user's choice if they decline
- Do not repeatedly suggest if already declined in the same session