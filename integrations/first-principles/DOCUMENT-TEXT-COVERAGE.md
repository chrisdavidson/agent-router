# document_text coverage (re-run of the agents' PDF reads)

Counts only; no URL, host, prompt or text. Regenerate with
`python3 integrations/first-principles/measure_document_text.py --fetch --write`
(measured 2026-10-18; `--fetch` sends one request per
distinct link, as the agent did). The population comes from this checkout's local
traces and captures, so the figures are a snapshot, not reproducible from a clone.

## WebFetch on a PDF link, then document_text on the same link

| Measure | Calls |
|---|---|
| WebFetch calls on a PDF link | 29 |
| distinct links | 24 |
| webfetch said: failed | 6 |
| webfetch said: ok | 1 |
| webfetch said: reported_missing | 22 |
| with the agent's ask (prompt or stated purpose) | 29 |
| document_text: HTTP 404 | 1 |
| document_text: host unreachable | 6 |
| document_text: returned the text | 22 |
| pages returned (all calls) | 1428 |
| answered: half or more of the asked terms in the text | 20 |
| asked terms found / looked up | 109 / 150 |

| What WebFetch said | What document_text gave | Calls |
|---|---|---|
| failed | host unreachable | 6 |
| ok | text, answered | 1 |
| reported_missing | HTTP 404 | 1 |
| reported_missing | text, answered | 19 |
| reported_missing | text, not answered | 2 |

## pdftotext, then document_text on the same file

| Measure | Calls |
|---|---|
| pdf shell calls | 16 |
| pdf gone | 9 |
| no pdftotext output recorded | 4 |
| full text gone | 1 |
| pdf still on disk | 2 |
| compared with pdftotext | 2 |
| agree (90%+ of pdftotext's words returned) | 2 |
| mean share of pdftotext's words returned | 98.8% |

## Reading it

*Answered* is a proxy, not a reading: it says the specific numbers and names the agent
asked about are in the document's text, which WebFetch's summary had said they were not.
A link that is gone, blocked or an HTML page fails here as it did for WebFetch; that is
a sources problem, not a PDF one. pdftotext agreement is word overlap, so layout
differences (columns, hyphenation) lower it without losing content.
