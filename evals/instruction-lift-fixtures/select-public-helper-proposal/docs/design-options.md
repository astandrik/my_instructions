# Normalization options

Both the API and CLI require the same lowercasing and whitespace contract.

- Option A: duplicate the normalizer inside each caller.
- Option B: export the existing core normalizer through the public `core` package API and cover both callers with focused contract tests.
