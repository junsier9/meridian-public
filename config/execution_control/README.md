Execution control configuration belongs here when it is file-based rather than environment-driven.

Current contract:
- Trust root and permit paths are provided by environment variables documented in `.env.example`.
- Runtime sessions and lease registries default to OS-local paths unless explicitly overridden.
- The first single-agent slice reuses the existing runtime ingress path and does not add new execution-control files here.
- Do not commit live permits, signing keys, or trust-root material into this directory.

Use this folder only for checked-in templates or non-secret runtime policy files.
