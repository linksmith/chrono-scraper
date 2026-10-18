# Gold annotations

One YAML file per gold sample, produced by `python -m evals.runner draft-gold`
and then **reviewed by a human**:

1. Open the file, open the archived page (`url` + `timestamp` on
   web.archive.org), and correct `title`, `body`, `author`, `date_published`.
   The body should contain the canonical content only — no navigation,
   related-links boxes, cookie banners, or comment-form boilerplate.
   Keep genuine content the extractor missed; delete boilerplate it leaked.
2. Set `review_status: approved` (drafts are never scored — they carry the
   drafting extractor's bias).

These files are curated artifacts and belong in git, unlike `corpus_data/`.
`python -m evals.runner validate-gold` checks structural validity.
