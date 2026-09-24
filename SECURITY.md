# Security policy

RetrieVel is a local repository-navigation tool. Treat repository content,
generated artifacts, prompts, and benchmark traces as potentially sensitive.

## Report a vulnerability

Use GitHub's private Security Advisory flow for
`Vel-Labs/velGraphing`: open the repository's **Security** tab, select
**Advisories**, then choose **Report a vulnerability**. Do not disclose
secrets, private source, credentials, or an exploitable reproduction in a
public issue.

Include the affected version or commit, a minimal reproduction, impact, and
any safe mitigation. If private advisories are not enabled, do not post
sensitive details publicly; ask a maintainer to enable the private advisory
channel through the repository's normal public contact path.

## Data boundaries

`/graph-find` limits reads to Git-tracked regular UTF-8 files under the
explicit repository root. It excludes secret-like paths before reading them,
does not send repository content to a provider or network service, and does
not write a persistent index. Exported graph records contain pointers and
provenance metadata, not complete source bodies. A `defer` result means direct
source review remains required.
