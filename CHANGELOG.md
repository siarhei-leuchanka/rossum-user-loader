# Changelog

## v0.2.2 — 2026-11-12

### Changed
- **The templates no longer include an example row.** Both the CSV template (**⬇ Download CSV template** in the web UI) and the xlsx template now contain only the header row. Every row in a file is loaded, so the old example row (`jane.doe@example.com`) created a real user, and sent it a password-reset email, if it was left in. **If you kept a copy of an older template, delete the Jane Doe row before loading.**

### Fixed
- **Dragging a file into the macOS Terminal now works.** Terminal pastes paths with backslash-escaped spaces (`My\ Folder/users.csv`), which the CLI did not recognise; with a space in the path, the load stopped with a Python error. Quoted paths keep working as before.
- **The CLI no longer shows a Python error when the input file's folder doesn't exist.** The run log is written to the current folder instead, and if the log can't be written at all you get a one-line warning.
- **Clearer sign-in error when `ROSSUM_API_TOKEN` is set.** A rejected sign-in can mean a wrong token *or* a wrong domain URL; the message now names both, instead of blaming only the token.
- **The web UI's load endpoint rejects a malformed request** with a clear error instead of treating it as an empty load. The page itself always sent valid requests, so nothing changes for normal use.

### Documentation
- **README updated** for pipx users: how to get the templates, the web UI, the optional `username` column, and how to update. It no longer says the first row of a file is skipped; every row has been loaded since May 2026.
- **"How to update" corrected in the v0.2.0 and v0.2.1 notes.** `pipx upgrade` works whenever the version number changes, which it does with every release; `pipx reinstall` is the fallback.

### How to update
If you installed with pipx:

```
pipx upgrade rossum-user-loader
```

Afterwards, `rossum-user-loader --version` should print `0.2.2`. If it still shows the old version, run `pipx reinstall rossum-user-loader`, which always rebuilds from the latest code.

## v0.2.1 — 2026-11-12

### Fixed
- **⬇ Download CSV template now works in every install.** In some installs the template file was left out of the package, so the button returned an error instead of downloading the template. This affected v0.2.0 and earlier when installed:
  - with pipx on **Linux or Windows**, or
  - from a **local copy of the source** on any system (e.g. `pipx install .`).

  pipx installs on **macOS** were not affected: the file happened to be included there. If the template downloads fine for you, nothing was broken, but updating is still recommended.
- **Declared `httpx` as a direct dependency.** The tool uses it directly, but it was only arriving through `rossum-api`. Nothing changes for users today; this stops a future `rossum-api` release from breaking the tool by dropping or changing it.

### How to update
If you installed with pipx:

```
pipx upgrade rossum-user-loader
```

Afterwards, `rossum-user-loader --version` should print `0.2.1`. If it still shows the old version, run `pipx reinstall rossum-user-loader`, which always rebuilds from the latest code.

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
pipx upgrade rossum-user-loader
```

Afterwards, `rossum-user-loader --version` should print `0.2.0`. If it still shows the old version, run `pipx reinstall rossum-user-loader`, which always rebuilds from the latest code.
