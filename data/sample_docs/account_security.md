# Account & Security Help

*Effective: 2026-06-01 · Owner: Identity Team · Doc ID: POL-ACC-003*

## Sign-in Troubleshooting

**Forgot password**: Use "Forgot password" on the sign-in page. Reset
links expire after 30 minutes and can only be used once. If the email
doesn't arrive within 10 minutes, check spam and confirm you're using
the address tied to the account.

**Locked out after failed attempts**: Accounts lock for 15 minutes after
5 consecutive failed sign-ins. The lock clears automatically - there is
no way (and no need) for support to unlock it early. This is a security
control against credential stuffing.

**No access to the old email address**: Account recovery requires proof
of ownership: order number + billing address + last-4 of the payment
method on the most recent order. VIP-tier customers may verify by the
phone number on file instead.

## Two-Factor Authentication

- We support authenticator apps (TOTP) and SMS.
- Losing your 2FA device: use a saved recovery code (generated at
  enrollment - each works once), or verified account recovery above.
- We never ask for 2FA codes over chat or email. Anyone who does is
  impersonating us - report it.

## Managing Your Data

- **Export**: Account → Privacy → Download my data (arrives as a zip
  within 24 hours; contains orders, profile, and support history).
- **Deletion**: Account → Privacy → Delete account. Orders must be
  settled (no open returns/charges) first. Deletion is irreversible
  after a 14-day grace window during which signing back in cancels it.
- Legal hold: accounts under active dispute or fraud investigation
  cannot self-delete until resolved (we notify you if this applies).

## Payment Methods

Cards are tokenized - we store only the last four digits and expiry.
Full card numbers never touch our servers after the initial
authorization (processed by our PCI-DSS Level 1 payment provider).

## Recognizing Phishing

Real AcmeCorp messages:
- Come from @acmecorp.com domains only
- Never ask for passwords, full card numbers, or 2FA codes
- Link to acmecorp.com or our official short-link domain acme.co
- Reference an order number you can find in your account

Report suspicious messages via **Account → Security → Report phishing**
(attaching the message); our security team reviews every report.
