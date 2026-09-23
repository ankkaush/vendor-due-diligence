# Solace Data Partners — Security Questionnaire

**Date:** 2025-09-20

## Section 1 — Transport Security

**Q1. What protocols are used to protect data in transit?**
All data in transit is protected using TLS 1.2 or higher. Older protocol
versions (SSLv3, TLS 1.0, TLS 1.1) are disabled on all customer-facing
endpoints.

## Section 2 — Access Control

**Q2. How is administrative access to production systems controlled?**
Administrative access requires multi-factor authentication and is
restricted to named personnel via role-based access control. Access
grants are reviewed quarterly by the security team.
