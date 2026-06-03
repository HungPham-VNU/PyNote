# M3 tuning log

Append a block per run. Goal: reach `avg_fidelity ≥ 0.9` on the 50-question golden set across 5 representative PDFs.

## Template

```
### YYYY-MM-DD — short label
- top_k:        8
- candidate_k:  50
- rerank:       on (voyage-rerank-2.5) | off
- model:        claude-sonnet-4-6 via GH Models
- notebook:     uuid (PDFs: ...)
- avg_fidelity: 0.xx
- notes:        what changed, what to try next
```
