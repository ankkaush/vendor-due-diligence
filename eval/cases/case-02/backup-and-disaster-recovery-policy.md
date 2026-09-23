# Solace Data Partners — Backup and Disaster Recovery Policy

**Document owner:** Infrastructure Operations
**Last reviewed:** 2025-08-11

## 2. Backup Schedule and Retention

Full backups of all production databases, including customer data, are
taken nightly and retained for **90 days** on encrypted, geographically
redundant storage. Backups are retained on this schedule for all customer
accounts, including accounts that have been offboarded, to support
disaster-recovery and business-continuity requirements.

## 3. Backup Deletion

Backups are automatically purged 90 days after creation on a rolling
basis. This policy applies uniformly and does not distinguish between
active and terminated customer accounts.
