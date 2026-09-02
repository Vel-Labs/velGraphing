# Source Ownership And Portability

## Ownership

Canonical source has one owner for each surface:

| Canonical source | Portable target | Ownership rule |
| --- | --- | --- |
| `packages/core/**` | `plugins/graph-engineering/runtime/core/**` | Core source is canonical. Runtime content is generated. |
| `contracts/core/**` | `plugins/graph-engineering/runtime/contracts/core/**` | Contract source is canonical. Runtime content is generated. |
| `adapters/knowledge-compiler/**` | `plugins/graph-engineering/runtime/adapters/knowledge-compiler/**` | Adapter source is canonical. Runtime content is generated. |

The projection contract stores relative POSIX paths. It stores no machine path.
The projector sorts every output path. It copies file bytes without changing
them. It records a canonical JSON state file under the generated runtime root.

The projector rejects an absolute path, a traversal segment, an overlapping
mapping, a source symlink, a target symlink, a non-regular file, and a path
outside the declared project root. It also rejects content that is not covered
by a valid prior projection state. A managed update is allowed only after the
projector verifies every prior file digest and the exact managed directory set.
All safety checks finish before the projector replaces the managed runtime
tree.

## Proof Surfaces

- **Source proof:** Product tests cover current canonical source behavior.
- **Package proof:** Parity validation binds canonical source to the generated
  plugin runtime and release manifest.
- **Installed proof:** Installation must be checked separately from source and
  package validation.
- **Publication proof:** A local Git repository is not a GitHub release.
- **Consumer proof:** One repository result does not prove general value.

A graph remains a derived view. It does not replace canonical repository truth.
