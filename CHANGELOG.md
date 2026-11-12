# Changelog

## v0.2.0 — 2026-11-12

### What's new

**Account status in the Existing Users tab**
- The Existing Users table has two new columns, **is_active** and **email_verified**, shown as `yes` / `no`.
- **⬇ Download CSV** includes both columns, after the usual load columns:
  `auth_type;email;first_name;last_name;username;oidc_id;role;queue_ids;can_approve;is_active;email_verified`
- The new columns are for information only. You can still load an exported file through **Load from CSV file** or the CLI as before. The two columns are ignored on load and never sent to Rossum, so editing them doesn't change a user's status.

**User counters**
- **Load Users** shows how many users are in the load list, e.g. *Users to process (12 users)*. This is the number that **▶ Start Load** will process.
- **Existing Users** shows how many users are listed, e.g. *Existing users (37 users)*, or *(showing 34 of 37 users)* when a filter is hiding some.
- Both counters update as you add, delete, clear, import, copy or refresh.

**"Active users only" filter**
- A new checkbox on the Existing Users toolbar hides inactive users (`is_active = no`). It's **on by default**.
- **Select all**, **Copy selected**, **Copy all** and **⬇ Download CSV** use only the users shown. A user hidden by the filter is unticked automatically, so it can't be copied by mistake.
- Untick the checkbox to see and export everyone.
- The filter only changes what you see. Hidden users are still checked for duplicates, so creating a user whose username belongs to an inactive user is still reported as *User Exists*.

### Things to know
- **Deleted users are still not listed.** Rossum marks deleted users inactive too, so the filter is for users who were deactivated without being deleted.
- **If you load an exported file into a different organization:** queue IDs belong to the organization they came from. Queues that don't exist in the target organization are dropped without a warning, so update `queue_ids` before loading.

### How to update
If you installed with pipx:

```
pipx reinstall rossum-user-loader
```

Use `reinstall`, not `upgrade`. Earlier releases all report version `0.1.0`, so `pipx upgrade` may decide there is nothing to do. Afterwards, `rossum-user-loader --version` should print `0.2.0`.
