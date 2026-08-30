# Writing standard

Use this guide when producing or revising the local article.

## Audience and length

- Write primarily for Chinese readers with a technical background in computer science, AI, or brain-computer interfaces.
- Target 4,000-6,000 Chinese characters, excluding references and verbatim figure captions. Prefer clarity over filling the range.
- Keep the paper's English title, important English terms, figure labels, DOI, dataset names, model names, and metric names.

## Required argument

Organize the article around:

`research gap -> question/hypothesis -> design -> evidence -> conclusion -> independent evaluation`

Include:

1. Bibliographic identity and a short reader-oriented overview.
2. The prior knowledge and precise gap motivating the paper.
3. The method at the level required to judge the result.
4. A guided reading of the most important source-paper figures.
5. A separation between what the data show, what the authors infer, and what the blogger concludes.
6. Contributions, limitations, reproducibility concerns, and plausible alternative explanations.
7. Concrete research or engineering takeaways.

## Domain-specific checks

For AI/computer-science papers, cover the relevant items: task definition, datasets and splits, baselines, architecture, objective, training setup, evaluation metrics, ablations, compute, robustness, leakage, and reproducibility.

For BCI papers, cover the relevant items: participants, inclusion criteria, ethics statement, paradigm, acquisition hardware, channels, sampling rate, preprocessing, artifact rejection, feature/model pipeline, within- versus cross-subject validation, statistics, effect sizes, uncertainty, and clinical or ecological validity.

## Evidence discipline

- Do not invent missing hyperparameters, sample details, significance values, mechanisms, or causal claims.
- Mark unclear or unavailable information explicitly.
- Avoid turning correlation into causation or benchmark improvement into general capability.
- Quote sparingly. Paraphrase and cite the paper section, page, table, or figure.
- Explain effect magnitude and uncertainty where available, not only statistical significance.

## Platform adaptation

The local article is canonical. Keep WordPress and CSDN versions substantively identical. CSDN may use a shorter title and a brief opening hook, but must not strengthen claims, remove limitations, or change figure provenance.
