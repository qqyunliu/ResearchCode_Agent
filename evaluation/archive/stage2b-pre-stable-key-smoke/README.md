# Superseded Stage 2B smoke output

This directory preserves the first three retrieval smoke records for auditability.
They were generated before the runtime-to-canonical stable entity key mapping was
fixed, so their human-readable `stable_entity_key` values are invalid for formal
metrics. They must not be copied back into `evaluation/results/raw/` or included
in any Stage 2B report.

The associated Qdrant build and provider-call ledgers remain valid and are reused;
only these result records are superseded.
