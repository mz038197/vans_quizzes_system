# Issue tracker: GitHub Issues

Issues and specs (you may know a spec as a PRD) for this repo live in GitHub Issues on `mz038197/vans_quizzes_system`. Use the `gh` CLI.

The repository is public, so everything written in an issue is public. Do not put secrets, personal data or student names from real classes in an issue.

## Conventions

- A spec is one issue whose title starts with `Spec:`.
- Implementation tickets are one issue each, and each one links its spec issue (`Part of #N`) in the body.
- Triage state is a GitHub label (see `triage-labels.md` for the label strings).
- Comments and conversation history are issue comments.

## When a skill says "publish to the issue tracker"

`gh issue create --title "..." --body-file <file> --label <triage label>`

## When a skill says "fetch the relevant ticket"

`gh issue view <number> --comments`. The user will normally pass the issue number or URL.

## Archive

`.scratch/` holds the specs from before the move to GitHub Issues (Groups, hard delete). It is history only; do not add new specs there.
