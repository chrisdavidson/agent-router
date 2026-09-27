# demo_workspace

Working directory for the inner Claude Agent SDK agent in the agent-router demo. It is a small
fictional project, "demo-shop", with files that the catalog tools can act on:

| Path | Used by |
|---|---|
| `data/orders.json` | `json_query`: 15 orders with `id`, `customer`, `status` (`paid`, `failed` or `refunded`), `total` and `items` |
| `docs/release.html` | `html_to_markdown`: release notes with headings, lists, a table, a link, and `<script>`/`<style>` blocks to strip |
| `src/` | `repo_stats`: a few small Python and JavaScript files |
| `.claude/skills/commit-writer/` | the MIT `commit-writer` skill (Conventional Commits messages) |

All content here is sample data made up for the demo.
