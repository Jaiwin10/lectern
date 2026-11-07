# Fact verification

The brief asks us to verify the factual accuracy of the generated lessons ourselves, not only through the tool. This page lists the facts each lesson relies on and the authoritative source that settles each one, followed by examples of what the two QC layers caught in test runs.

A regenerated lesson may word things differently. Re-check its key claims against this table.

## Lesson 1: HTTP Requests and Responses

Authoritative reference: **RFC 9110, *HTTP Semantics*** (IETF, 2022), <https://www.rfc-editor.org/rfc/rfc9110>

| Fact the lesson should state | Correct? | Where to check |
|---|---|---|
| GET asks for a representation of a resource | Yes | RFC 9110 §9.3.1 |
| GET is *safe* (read-only by intent) and *idempotent* | Yes | §9.2.1, §9.2.2 |
| A body in a GET request has no defined meaning; don't send one | Yes | §9.3.1 |
| POST sends data for the server to process; it is neither safe nor idempotent | Yes | §9.3.3 |
| Repeating a POST can repeat its effect (e.g. a duplicate order) | Yes | §9.2.2, §9.3.3 |
| A successful POST that creates a resource should return **201 Created** | Yes | §9.3.3, §15.3.2 |
| Status codes are grouped by first digit: 1xx informational, 2xx success, 3xx redirection, 4xx client error, 5xx server error | Yes | §15 |
| 4xx means the client made an error (e.g. 404 Not Found, 400 Bad Request) | Yes | §15.5 |
| 5xx means the server failed to handle a valid request (e.g. 500, 503) | Yes | §15.6 |
| 401 = not authenticated, 403 = authenticated but not allowed | Yes | §15.5.2, §15.5.4 |
| Data in a GET query string can end up in logs and browser history | Yes | §17.9 (sensitive information in URIs) |
| POST data is "hidden" or "secure" | **No.** It is only kept out of the URL. It is plain text unless HTTPS is used | §4.2.2, §17.9 |

### What the QC layers caught in testing (HTTP)

- **QC 1 (incorrect):** an answer key said POST is better for payments *because* it is not idempotent and so prevents duplicate charges. That reverses the logic: non-idempotent POST is exactly what *can* cause duplicates. A ready-made fix was offered and applied.
- **QC 1 (misleading):** "POST is more appropriate for sensitive data because the information is hidden within the request body". This wrongly implies encryption.
- **QC 1 (citation):** status codes cited to a source excerpt that does not mention them.
- **QC 2 (timing):** the first draft measured about 29–35 minutes, not 45. Both the automated timing check and the reviewer flagged it, and the reviewer proposed a hands-on browser DevTools exercise.
- **QC 2 (clarity):** the jargon "nullipotent", and "user agent" used without a definition.

## Lesson 2: Git Branching and Merging

Authoritative references: ***Pro Git*** (2nd ed.), Scott Chacon & Ben Straub, <https://git-scm.com/book>, chapter 3, and the Git documentation and release notes at <https://git-scm.com/docs>

| Fact the lesson should state | Correct? | Where to check |
|---|---|---|
| A branch is a lightweight, movable pointer to a commit | Yes | Pro Git §3.1 |
| `git branch <name>` creates a branch; it does not switch to it | Yes | Pro Git §3.1 |
| `git checkout -b <name>` / `git switch -c <name>` create a branch and switch to it | Yes | `git-checkout`, `git-switch` docs |
| `git switch` was added in Git 2.23 (2019) as a clearer alternative to `checkout` for branches | Yes | Git 2.23 release notes |
| The default branch name is set by `init.defaultBranch` (Git 2.28+); `main` and `master` are both common | Yes | `git-init` docs, Git 2.28 release notes |
| To merge `feature` into `main`, switch to `main`, then run `git merge feature` | Yes | Pro Git §3.2 |
| Fast-forward: if `main` has no new commits, its pointer just moves ahead | Yes | Pro Git §3.2 |
| Otherwise Git makes a three-way merge (both tips plus their common ancestor) and a merge commit with two parents | Yes | Pro Git §3.2 |
| Conflicts happen when both branches change the same part of a file; Git marks them with `<<<<<<<`, `=======`, `>>>>>>>` | Yes | Pro Git §3.2, "Basic Merge Conflicts" |
| To resolve: edit the file, remove **all** markers, `git add` the file, then `git commit` | Yes | Pro Git §3.2 |

### What the QC layers caught in testing (Git)

- **QC 1 (citation mismatches):** without a Tavily key, research only reached general pages such as Wikipedia and an MDN glossary entry. QC 1 flagged each claim cited to a source that doesn't contain it ("pointer", default branch names, `git checkout` behaviour). This is the expected behaviour, and the reason to add a Tavily key so git-scm.com is found.
- **QC 1 (source error):** noticed that one *source excerpt* (Wikipedia on GitHub) contained an inaccuracy that the lesson had correctly avoided.
- **QC 2 (high):** beginners often leave the `=======` line or a marker in the file. The instructions needed to say explicitly to delete all three marker lines.
- **QC 2 (consistency):** the lesson recommended `git switch` but the answer key used `git checkout -b`.
- **Length pass:** the first draft measured 35 minutes; after the thin sections were expanded it measured 43 minutes.
