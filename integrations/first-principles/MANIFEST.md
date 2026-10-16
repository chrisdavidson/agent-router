# The integration manifest (MANIFEST-01)

agent-router reads a first-principles plugin's identity from one small data file, the
**integration manifest**, instead of typing it into its hooks and catalog. The plugin publishes
it at `<plugin root>/references/integration.json`. It need not exist: every router feature works
from the pinned copy in this directory, [`manifest.fallback.json`](manifest.fallback.json)
(decision D-05). The reader is `src/agent_router/contracts/manifest.py`; it names no plugin.

## Format (`manifest_version` 1)

```json
{"manifest_version": 1,
 "plugin_name": "first-principles",
 "agent_type": "first-principles:first-principles",
 "command_prefix": "/first-principles:",
 "launcher": "/first-principles:first-principles-analysis",
 "output": {"dir": ".first-principles", "glob": ".first-principles/analysis-*.md"},
 "summary": {"schema": "references/summary-schema.json",
             "heading": "## Structured summary (process output)",
             "schema_version": 1},
 "examples_dir": "references/examples",
 "capabilities_used": ["exact-arithmetic"]}
```

| key | type | meaning |
|---|---|---|
| `manifest_version` | integer | this format's version; the reader knows `1` |
| `plugin_name` | string | the plugin's name; must equal the name the router looked it up under |
| `agent_type` | string | the agent's subagent type (`<plugin>:<agent>`): the catalog's delegation target and the one agent the trace follows |
| `command_prefix` | string | the plugin's slash-command namespace; a prompt starting with it already delegates |
| `launcher` | string | the command that runs the whole analysis |
| `output.dir` | string | the directory, relative to the agent's cwd, that holds the agent's report files; commands naming it are never routed |
| `output.glob` | string | the report files, relative to the agent's cwd; `*` matches one or more path characters |
| `summary.schema` | string | the summary-block field table, relative to the plugin root |
| `summary.heading` | string | the heading that opens the summary block |
| `summary.schema_version` | integer | the schema version the publisher emits. The set the router **accepts** is the router's, `accepted_schema_versions` in `descriptor.json`; it is deliberately not in the manifest |
| `examples_dir` | string | the worked examples, relative to the plugin root |
| `capabilities_used` | list of strings, optional | router capabilities the plugin makes use of (e.g. `exact-arithmetic`) |

Paths with `summary.schema` and `examples_dir` are relative to the plugin root and may not be
absolute or contain `..`.

### Evolution

Add-only. A reader ignores keys it does not know. Removing or renaming a key, or changing what
one means, bumps `manifest_version`; a reader that does not know the version refuses the file
(see Degradation) and uses its pinned fallback.

## Finding the plugin root (MANIFEST-02)

`resolve_manifest` looks, in this order, and stops at the first plugin root it finds:

| # | source | `Resolved.source` |
|---|---|---|
| 1 | the environment variable named by the descriptor (`FP_PLUGIN_ROOT`) | `env` |
| 2 | the root file the conductor records, `<state dir>/integration/<plugin>.root` | `recorded` |
| 3 | the Claude plugin cache, `~/.claude/plugins/cache/*/<plugin>/*/`, newest manifest (else newest directory) first. The cache can hold a stale copy and a session started with `--plugin-dir` uses another root, so this source carries a warning. `AGENT_ROUTER_PLUGIN_CACHE` replaces the cache directories (`os.pathsep`-separated; used by the tests) | `cache` |
| 4 | the pinned fallback manifest, no root | `fallback` |

A root that has no usable manifest (today's state: the plugin is installed and publishes none)
gives the fallback manifest **with** that root: `fallback+root`. The root still locates the
schema file and the examples.

### Degradation (MANIFEST-04)

A manifest with an unknown `manifest_version`, an invalid shape, another `plugin_name`, or a
`summary.schema` that is not a file under its root is **not used**: the fallback manifest is
used, the root is kept, and a warning says why. Resolution never raises for a bad manifest.
Only an unreadable *fallback* raises: it ships with the router, so that is a build error.

How the manifest was found (`source`, `plugin_root`, `manifest_version`, `warnings`) is stored
once per session in the hook's session state (`integration`) and on each trace `run_end`.

## The integration descriptor

`descriptor.json`, next to `catalog.yaml`, is the router-side half: what to look for, not what
the plugin publishes.

```json
{"descriptor_version": 1,
 "expected_plugin": "first-principles",
 "plugin_root_env": "FP_PLUGIN_ROOT",
 "fallback_manifest": "manifest.fallback.json",
 "own_plugin_json": "plugin/.claude-plugin/plugin.json",
 "delegate_entry": "first-principles-agent",
 "calc_entry": "exact-calc",
 "calc_script_entry": "exact-calc-script"}
```

`calc_script_entry` is optional (an integration without the script form omits it).

`agent-router hook` (and every command given this catalog) finds the descriptor either through
`AGENT_ROUTER_INTEGRATION=<dir>` (which `plugin/bin/hook` sets) or because it sits beside the
`--catalog` file.

## What is derived (MANIFEST-03)

Catalog files may use `${name}` in their string fields (`examples` and `not_for` are exemplar
text and never substituted). `load_catalog(path, variables=...)` fills them; a name with no value
is a `CatalogError`.

| variable | from |
|---|---|
| `fp.plugin_name`, `fp.agent_type`, `fp.command_prefix`, `fp.launcher`, `fp.output_dir`, `fp.output_glob` | the resolved manifest |
| `self.plugin_name` | `name` in the router-side plugin's `plugin.json` |
| `self.calc_tool` | `mcp__plugin_<self.plugin_name>_agent_router__calc` |
| `self.calc_script_tool` | `mcp__plugin_<self.plugin_name>_agent_router__calc_script` |

The hook's defaults, used when `AGENT_ROUTER_SKIP_INPUT` / `AGENT_ROUTER_SKIP_PROMPT` are unset
or empty (an explicit value wins):

- skip input: `re.escape(output.dir)` + `(?!\w)` (the old `\b`, which would not match after a directory name ending in a non-word character). The agent's own report commands are never routed.
- skip prompt: `^\s*(?:<command_prefix>|/<self.plugin_name>:)`, each escaped. The second
  alternative silences the delegation note on prompts from the router's own commands, so a
  conductor launched from this plugin does not draw a second delegation note (CONDUCT-04).

`trace.py` derives `AGENT`, `CALC_TOOL`, the report-path patterns, the summary heading and the
catalog entry ids from the same manifest. Its schema file is, in order: `AGENT_ROUTER_FP_SCHEMA`,
`<plugin root>/<summary.schema>` when that file exists, else the pinned copy in `contract/`.
`run_examples.py` reads the examples from `<plugin root>/<examples_dir>`.

## Literals that remain

`plugin/hooks/hooks.json` matchers and the default in `plugin/bin/trace` cannot be derived: the
host reads the first statically, and the second must answer without starting Python. A test
holds them equal to the fallback manifest's `agent_type` (and the calculator matcher to
`self.calc_tool`). `bin/trace` takes `FP_AGENT_TYPE` to override its default.

## Verified against the installed plugin

The fallback's values were checked on 2026-10-15 against the first-principles 9.20.0 tree
(`first-principles/` of its repository; `integration.json` itself is not published yet):

| value | where it was read |
|---|---|
| `plugin_name`, and the namespace in `agent_type` and both prefixes | `.claude-plugin/plugin.json` `name`; `agents/first-principles.md` frontmatter `name` |
| `launcher` | `skills/first-principles-analysis/SKILL.md` exists (`name: first-principles-analysis`, slash-only) |
| `output.dir`, `output.glob` | the agent definition: "appended to `.first-principles/analysis-<UTC>.md`" |
| `summary.schema`, `summary.schema_version` | `references/summary-schema.json` exists, `schema_version` 1 |
| `summary.heading` | the same file, `block.heading` |
| `examples_dir` | `references/examples/` holds 14 worked examples |

`tests/test_fp_manifest.py::test_the_fallback_matches_the_installed_plugin` repeats these reads
against a plugin tree when `FP_PLUGIN_ROOT` names one (or the default checkout exists) and is
skipped otherwise.
