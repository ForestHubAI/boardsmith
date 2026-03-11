# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Instead, send an email to: **root@foresthub.ai**

Please include:

1. **Type of vulnerability** (e.g. code injection, path traversal, key exposure)
2. **Affected files/modules** with full path
3. **Steps to reproduce**
4. **Potential impact** of the vulnerability
5. **Suggested fix** (if any)

## Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 7 days
- **Fix/Patch:** Depending on severity, target: 30 days

## API Key Handling

Boardsmith uses external LLM APIs (Anthropic, OpenAI). Please note:

- API keys must **never** be committed to source code or git history
- Use environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) or `~/.boardsmith/llm.toml`
- See `.env.example` for the correct configuration
- If a key is accidentally committed: rotate the key with the provider immediately

## Scope

This policy covers the Boardsmith repository and its dependencies. Vulnerabilities
in third-party libraries should be reported directly to their maintainers.
