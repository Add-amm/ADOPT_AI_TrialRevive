# Supabase public database CA

Source: https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt

Downloaded over verified HTTPS. This is a public trust anchor, with no private key.
File SHA-256: `700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7`.

Supabase requires its database CA for `sslmode=verify-full`:
https://supabase.com/docs/guides/platform/ssl-enforcement

The connector uses this CA only for Supabase hosts. Other hosts use certifi.
An explicit `sslrootcert` in DATABASE_URL or PGSSLROOTCERT takes precedence.
When Supabase rotates this CA, obtain its replacement from Database Settings,
verify its source, update the file and hash, and verify a live connection.
