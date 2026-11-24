# Policy library and attachment recovery

Employees see only Active or legacy Published policies whose explicit audience permits their account. Drafts and missing/unknown audiences remain hidden. Legacy Published is projected as Active for compatibility; reading does not change stored records or publish draft policies. List results are no longer truncated at 200 entries.

New HR uploads are scanned using the existing upload validation and stored in the private MongoDB GridFS bucket `policy_attachments`. Metadata remains in `policies`; immutable earlier attachments remain referenced in file history. Downloads require the same M13 authorization and policy audience checks as policy reads. Stored files are checked against tenant, policy identity, size and SHA-256 before download or acknowledgement. Downloads use private, no-store responses. Existing local-file attachments remain readable when present, but lost deployment files cannot be recreated from metadata alone.

The supplied Employee Handbook v2 is an internal document for full-time employees. It must be restored through an authenticated HR upload with the Employees, managers and HR audience; its PDF is not committed into this public source repository. No source documents are uploaded, automatically published or emailed by this code change. HR publishes a readable file or full policy text through Policies → Publish Document.

The employee page distinguishes failed loading from an empty library, offers retry, and clears policy details and drafts when the signed-in account changes. HR can choose the audience before publication.
