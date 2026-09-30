# The Surface You Test Is Not the Surface That Breaks: project page

Project page for *The Surface You Test Is Not the Surface That Breaks*
(NeurIPS 2026 Workshop on Agents in the Wild: Safety, Security, and Beyond, poster).
Plain static HTML/CSS, served by GitHub Pages. No build step is needed to serve it.

## Layout
- `index.html`: the page. Blocks between `<!-- @build:NAME -->` markers are generated; edit everything else by hand.
- `static/css/style.css`: styles.
- `static/img/figures/`: paper figures (WebP).
- `scripts/build.py`: regenerates the marked blocks and the figures.

## Regenerating
```
python3 scripts/build.py
```
It reads the tables straight from `../Prompt-Injection-NeurIPS-Workshop-final/neurips_2026.tex`
and `appendix.tex` (inversion, decomposition, LOSO, defenses, native replication, payload
ablation, surface selection, and the per-cell results used for the per-model table), and converts
the PNG figures in that folder's `figures/` to WebP.

## Preview
```
python3 -m http.server 8000   # then open http://localhost:8000
```
