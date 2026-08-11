# Paper Triage

Local, deterministic support for selecting and classifying Zotero papers.

## Zotero credentials

Create the local secret file from the template and restrict it to your account:

```bash
cp .env.example .env
chmod 600 .env
```

Fill only these fields in `.env`:

```dotenv
ZOTERO_LIBRARY_TYPE=users
ZOTERO_LIBRARY_ID=YOUR_ZOTERO_LIBRARY_ID
ZOTERO_API_KEY=YOUR_ZOTERO_API_KEY
```

The application loads this file directly; it does **not** copy values into the process environment, logs, plans, reports, or SQLite audit ledger. The loader rejects symlinks, non-regular files, files owned by another user, permissions broader than `0600`, oversized files, duplicate keys, unknown keys, interpolation and quoted values.

`.env` is ignored by Git. Never commit it or send its contents. The current CLI only renders local reports; live Zotero operations remain protected by an immutable preview, a durable audit ledger and explicit human approval.
