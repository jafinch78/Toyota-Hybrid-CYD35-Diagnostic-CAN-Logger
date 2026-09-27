# Toyota Vehicle Bus Session Preprocessor

Standalone, standard-library-only preprocessor for validating TVM1 `SESSION.META` plus native raw bus streams and expanding them into legacy Evidence Builder-compatible session packages.

Native evidence is read-only. Expansion never modifies source raw files or `SESSION.META`.
