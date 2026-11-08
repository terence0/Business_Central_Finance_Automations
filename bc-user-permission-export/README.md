# User Permission Export

A small Business Central extension that lists **which user holds which permission set in which company** (the Access Control table), so licence reviews and access audits can be exported across all companies at once instead of being read user by user.

- `al/UserPermissionSets.Page.al`: a read-only list page over Access Control (user, user security ID, permission set, company, app), read in the client and exported with *Open in Excel* (or published as a web service for OData).
- `al/UserPermissionExport.PermissionSet.al`: the permission set needed to read it.

Build with the AL Language extension for VS Code and publish to a sandbox first.
