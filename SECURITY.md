# Security Policy

## Supported Versions

| Version | Supported          | Status |
| ------- | ------------------ | ----- |
| 1.1.x   | :white_check_mark: | Active development & security fixes |
| 1.0.x   | :white_check_mark: | Security fixes only |
| < 1.0   | :x:                | Unsupported |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report them privately via [GitHub Security Advisories](https://github.com/AdilShamim8/Customer-Support-Chatbot-102/security/advisories/new).

You should receive a response within 48 hours. If for some reason you do not,
please follow up via the advisory thread.

Include the following information where possible:
- Type of issue (e.g., injection, SSRF, prompt injection, auth bypass)
- Full paths of source files related to the issue
- Location of the affected source code (tag/commit/branch)
- Step-by-step reproduction instructions or PoC
- Impact assessment, including how an attacker might exploit it

### Scope

In scope:
- The FastAPI service and its middleware stack (auth, rate limiting)
- RAG pipeline data flow (document ingestion, retrieval, generation)
- Prompt injection and retrieval poisoning scenarios
- Dependency vulnerabilities
- Infrastructure manifests (Kubernetes, Terraform, Docker)

Out of scope:
- Vulnerabilities in third-party SaaS services themselves
- Attacks requiring physical access
- Social engineering
- DoS via extremely large legitimate payloads within documented rate limits

## Handling Process

1. Acknowledgment within 48 hours
2. Triage and severity assignment (CVSS)
3. Fix development on a private branch
4. Coordinated disclosure with the reporter
5. Public release + CVE request (where applicable)

## Security Architecture Notes

- All secrets are injected via environment variables / secret managers.
  The repository is scanned by gitleaks and detect-secrets on every commit.
- The service never logs secrets or full prompts at INFO level in production.
- Rate limiting and auth are enforced at both the nginx edge and application
  layers (defense in depth).
- Container images are scanned with Trivy; runtime runs as a non-root user
  with a read-only root filesystem.
- Prompt-injection hardening: retrieved chunks are treated as untrusted data
  and delimited from system instructions; the prompt engine strips control
  characters and blocks known injection markers.
