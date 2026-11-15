---
name: firestore-groups-expert
description: Domain rules for Firebase Auth, Firestore security rules, Pick'em game collections, and Group management.
---

## Firestore & Groups Architecture Rules

### 1. Firestore Collections & Security Rules ([firestore.rules](file:///d:/Git/College-Basketball-Stats/firestore.rules))
- `/user_settings/{userId}`: Authenticated users can read; only `isOwner(userId)` can write, strictly limited to `['displayName', 'favoriteTeamId']` (both strings).
- `/groups/{groupId}`:
  - Create requires `['name', 'teamId', 'league', 'members', 'isPrivate']`, `members == [request.auth.uid]`, and forbids plaintext `'password'`.
  - Updates allow either (Case 1) a user joining by appending strictly `[request.auth.uid]` to `members`, or (Case 2) the group owner updating `['isPrivate', 'passwordHash', 'salt', 'ownerId']` (never `'password'`).
- `/{collectionName}/{gameId}` (Pick'em picks):
  - `collectionName` matches `^[0-9]+[mw]$` (e.g., `152m`, `152w` via `getCollectionName(teamId, league)`).
  - Create/Update allows a user to modify strictly `[request.auth.uid, request.auth.uid + '_time']` where pick value is a string (athlete ID) and `_time` is a number (epoch ms).

### 2. Group Password Hashing
- Private groups use PBKDF2-SHA256 (`100,000` iterations, 16-byte random hex salt, prefixed with `pbkdf2:`) via `generateSalt()`, `hashPassword(password, salt)`, and `verifyPassword(enteredPassword, salt, storedHash)` in [helpers.js](file:///d:/Git/College-Basketball-Stats/site_ui/helpers.js), with backward-compatible verification for legacy SHA-256 hashes.
