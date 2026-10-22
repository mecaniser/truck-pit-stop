# DB-INFRA-004: repeatable Mac-only branch deployment

Release & Reliability owns this high-risk infrastructure item. User confirmed
DieselBridge `codex/fix-part-catalog-activity`, source
`04f0517593ef7cd937ec37d5fb6cfc5e84bf8e77`, for immediate test deployment.
TPH receives a deploy command but its running version remains unchanged.

## Contract and implementation

Worktree `mac-test-deploy`, branch `codex/mac-test-deploy`, based on PR621.
Dirty original DieselBridge and TPH checkouts are preserved. Archive explicit
local branch Git objects only. Fixed source-path allowlists, bounded object/tar
sizes, exclusive extraction, link/traversal/environment/key rejection and trusted
Docker recipes prevent host checkout hooks/workflows from running. Runtime
credentials are never passed to builds. ARM64 immutable images bind app, source,
adapter version and bundle hashes. Exact-source/adapter completed image cache
requires live labels and a fresh artifact check, including the DieselBridge
frontend build stamp. Existing public access gate, HTTPS and CSP remain.

Installed workstation commands are `~/.local/bin/deploy-dieselbridge`,
`~/.local/bin/deploy-tph`, and `~/.local/bin/mac-test`, backed by a private owned
local bundle in `~/.local/share/mac-test-deploy/v1`. Sources and instructions live
in `deploy/mac-test-deploy/`. No Git push, merge, Railway invocation, DNS update,
provider enablement, automatic migration, downgrade, reseed or job enqueue occurs
inside these commands.

Remote controller root `~/mac-hosting/test-deploy` records accepted legacy images,
complete configuration hashes, all fourteen container identities and original
staging baseline at exclusive initialization. Shared stack-operator locking and
preflight drift checks protect existing operations. Only selected web/gateway
change; readiness/served SHA are checked. Previous image and full configuration
are retained. Failed candidates attempt scoped restoration without clearing prior
rollback history. Uncertain transactions retain their active journal and refuse
further changes. Rollback is application/configuration rollback, not data rewind.

Candidate migration/artifact probes use bounded resources, network none, no
privileged mounts, read-only filesystems and exact owned CID/name/label/image
cleanup on timeout. Tests include missing CID, wrong image/ownership and exited
probe behavior. Nineteen focused tests pass; independent QA/Security reviewed
source and required runtime gates.

## Older branch and isolated database

The selected October1 branch predates synthetic database revision187. A generic
shape check was rejected as insufficient because later triggers/constraints have
semantic effects. A private pg_dump of the existing synthetic database was
restored into `dbtest_8760eb646c924ba8`, owned by a unique restricted role. Existing
original data/schema/ACLs remain unchanged. Candidate web uses this clone and
Redis14; existing workers retain original database and Redis13. No worker code
was updated or job retriggered.

Independent role checks show NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/
NOBYPASSRLS, no inherited memberships, no original relation privileges, no
original schema/database CREATE, and no executable non-system security-definer
escape. Original users read returns permission denial42501. Redis14 was unused
and contains no worker queues.

Candidate acceptance checks133 mapped tables/2226 columns, type affinity,
expected enum labels, existing enum/null data and unmapped mandatory insert
columns. Native alpha/beta login, own-customer reads and bidirectional foreign
customer denial pass. Actual catalog cost/price/core/supplier update creates five
expected activity rows with exact before/after values. Four retained fixture
parts/twenty events reflect successive image-identity acceptance checks; they
are not worker jobs. Original inventory/activity remain zero. This proves these
synthetic journeys, not all old-code/new-schema write semantics.

Final image `sha256:9e92ec14d1641dc5996b47f2799bd5080526e695ea85e2e89f7e7f0cbd5755eb`
is bound to source04f05175 and the independently approved clone manifest. Both
frontend artifact stamp and later runtime source must match. Ordinary future
schema mismatches refuse before mutation; a separate reviewed database release
is required. Clone approval is image/source/revision-specific, not a reusable
migration bypass. Existing data backups/clones and old images remain retained.

## Retained preparation failures

First build could not resolve Docker credential helper in SSH PATH; official
Docker binary directory was added only to the build process environment. First
schema probe falsely compared generic SQLAlchemy Enum affinity with reflected
PostgreSQL ENUM; explicit enum-label subset plus stored-value checks corrected
it. Initial frontend source argument was declared only in runtime stage; owner
caught missing static stamp before deployment and corrected frontend-stage
ARG/ENV. Earlier builds/proofs remain private. Exact-source/adapter image reuse
then stabilized image identity, with a fresh artifact probe on every reuse.
First public attempt started native APIs but failed the preserved Compose curl
health check because the new slim image lacked curl. The controller automatically
restored accepted source65afe9b8 and closed its transaction, with twelve protected
containers and the baseline unchanged. Corrected recipe installs curl and artifact
acceptance checks its presence before rollout. Independent reviews accepted a new
image-specific approval token against the same clone, retaining the failed image,
old approvals, journal and rollback receipt.
Independent review also returned missing previous-release history and missing-CID
artifact cleanup; both were fixed and covered before deployment.

## Runtime acceptance — October22, 2026

Corrected image9e92ec14 deployed through the installed chosen-branch command,
operation `e0f0e10a-d940-456b-8b2c-0025dcc9fd40`. The installed rollback command
then restored original source65afe9b8/image15b11ee6 and original database/Redis13
configuration in operation `6727a1c9-a70b-4c8c-9b99-6b466f7ead46`. The installed
deploy command restored chosen source04f05175/image9e92ec14 and the same clone/
Redis14 in `6b4bcffd-af5c-4337-b8c5-f030f2abdd0d`. All three operations preserved
the twelve protected containers and baseline. Previous accepted release65afe9b8
remains available for rollback. No uncertain operation remains.

Ordinary public DNS443/system-trusted TLS, gate/native auth, secure cookies,
Bearer, query forwarding, bidirectional tenant denials, Origin negatives, logout,
cross-host/private/readiness denials pass against final runtime. Owner browser
fresh reload reaches Staging Alpha/one customer and My Shop inventory/four
synthetic parts. Costs20.30, prices51.78 and detail core5.00/contact are visible.
Browser performed no business writes. Actual catalog writes occurred only in the
isolated acceptance fixtures. TPH image95df2640/sourceb369e9f5 remains unchanged;
its command built main6a280dbd successfully without deploying it. TPH HTTP native
PIN acceptance passes; its older browser session expires normally to the PIN
prompt. No new TPH browser manager-login claim is made.

Redacted receipts under `mac-test-deploy/` include failed automatic restoration,
first successful deploy, explicit rollback, final deploy/status, clone proof,
both builds, native public HTTP, browser screenshots/hashes, original counts and
soak report. The original report is observing299samples/zero issues at04:07:58UTC;
the accepted24-hour window remains October21 7:09:59PM to October22 7:09:59PM
America/New_York. No clock reset, staging-source change or baseline replacement.
FileVault still requires assisted unlock/login after reboot. Railway production
remains untouched; PR619 into main remains open. This implementation is a draft
review on its owned branch, not a production release or overall infrastructure
Done claim. Final independent runtime QA/Security and PR identity are recorded
below after their gates return.

### Independent final gates

QA independently verified19tests, source/archive negatives, installed commands,
exact final status, automatic recovery, explicit rollback/redeployment, all twelve
protected containers, browser screenshots/hashes and public HTTP evidence.
Original PG2tenants/2users/2customers/receipt1execution1/inventory0/activity0;
clone4parts20events; Redis13/14 worker queues zero. TPH Mongo job1attempt1,
unpublished draft1/published0/scheduled0 unchanged. QA observed301samples with
zero soak issues. Reviewers performed no app mutations, jobs or production action.

Security final runtime gate and draft PR identity follow below.
