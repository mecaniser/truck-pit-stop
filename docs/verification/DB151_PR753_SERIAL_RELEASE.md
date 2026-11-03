# Shop Work and Settings serial release verification

## PR751: deployed 2026-11-03

Reviewed source a2a4a5e072a74ef1439cb50dc802cc7df61a10b0 matches squash merge8252d093f7891bb8f4acebacdb27506b09a488a3 byte for byte. Exact-source Quality gates41585025377 passed all seven jobs. Hosted remaining frontend2262 passed, remaining backend4732 passed/455 skipped; critical partitions passed separately. Local all-frontend2478 tests/224 files, affected backend58, build, shared-controls and changed-source lint passed. Scoped independent UI/navigation GO includes the inventory-origin correction and adversarial URL-context checks. No formal GitHub review approval was submitted.

Railway production web deployment0b8b9689-1e0c-439c-9bc5-7fcd1588b2f5 succeeded. Public build-version serves exact8252d093, built2026-11-03T05:49:25.555Z; readiness database and Redis OK. The normal production browser session was expired; signed-in production acceptance is not claimed. No credentials were inspected and no production financial/stock records were created or modified.

## PR753: refreshed release candidate

Merged actual main8252d093 into serial candidate6fbb58c4c1d613d578c7f83b60ed5df6bd3f7916. Only documentation history conflicted; both histories retained. Entire tree matches previously reviewed7a9c0ca8. Product delta against actual main is the scoped five-line Settings alignment rule; related Playwright regression and screenshot are preserved.

Fresh exact-tree frontend2478/2478 across224 files (183.19s), production build10.49s, shared-controls and changed-source lint passed. No changed TypeScript files against actual main. Independent reviewer confirmed identical-tree GO applies. Backend tree unchanged; no new backend suite needed beyond recorded58 affected checks and green hosted partitions.

Fresh isolated real-backend acceptance used a new tmpfs PostgreSQL15/Redis7 environment and fictional accounts only. Classic desktop nine icons allx148; keyboard Security selection passed. Classic phone section selection passed with390px document/scroll width. Modern desktop nine icons allx268; Modern390px picker switched Appearance to Security and collapsed correctly with no document overflow. Earlier signed-in Modern Profile/Security/Shop Profile geometry and phone checks retained. Actual user-visible source stamp6fbb58c4 confirmed. Only the fictional shop workspace preference changed during this acceptance; no financial/stock action submitted.

Fresh exact-head hosted CI, PR merge and production verification remain required. Do not mark PR753 released from this candidate receipt alone.

## Coverage limits

Independent GO covers changed UI/navigation; it is not a full security certification. The retained-actor pending-logout/inactive DashboardHome limitation was reproduced identically on prior main and candidate; this release does not fix it. Some broad older owner/admin, vehicle-history and error permutations were not repeated through a browser on the latest revision. Live provider payments and production financial writes were deliberately not exercised. Held PR619/622/623/638/748 remain untouched.
