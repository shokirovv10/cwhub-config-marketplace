# CwHUB V31.2 — Admin Scope & Temporary Password Hardening

- Helper admins only see routes assigned to their scope.
- Direct access outside scope returns 403 with an Uzbek permission message.
- Super Admin retains full access.
- User/role/ban/delete/password-reset management is Super Admin only.
- Finance helper can review/approve withdrawals but cannot mark them paid.
- Temporary admin reset passwords expire after 2 minutes and are shown only on the reset-result screen with a countdown.
- Register/login/logout security events are recorded.
- Administrator application approval automatically assigns the requested helper scope.
