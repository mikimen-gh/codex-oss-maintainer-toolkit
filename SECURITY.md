# Security Policy

## Reporting Security Issues

Please report security issues privately through GitHub Security Advisories when
available. If advisories are not enabled, open a minimal issue that does not
include exploit details, credentials, private logs, or sensitive data.

## Public Repository Rules

Do not commit:

- Credentials, tokens, API keys, or private keys
- Real local machine paths
- Private logs or conversation history
- Internal hostnames or runtime-only configuration
- Personal identifiers that are not meant to be public

Run the public-safety check before publishing:

```sh
./scripts/verify-public-safety.sh
```
