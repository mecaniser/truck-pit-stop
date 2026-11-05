# Customer and guest invoice payment focus

Owner: Frontend & UX. Item: DB-149MOB. Preview only; no deployment authorized for this refinement.

The user requests less repeated balance information and a compact mobile header, while preserving the implemented payment flow. Two independent assessments agree that hierarchy is the main issue; three payment methods and two amount choices are manageable. No additional wizard or mandatory step is proposed.

| Before | Proposed presentation | Reason |
| --- | --- | --- |
| Balance, invoice total, available amount, upper limit and amount input repeat figures | One dominant balance; retain distinct pending and draft payment amounts only where needed | Reduce arithmetic and scanning without hiding reservations |
| Large centered logo and tall header | Compact tenant identity and invoice heading | Put payment controls earlier on mobile |
| Mobile PDF, print and share text buttons | 44px icon buttons with accessible names | Preserve familiar utilities with less visual weight |
| Several equally weighted blocks and helpers | One coherent amount/method/action area, with secondary history and help | Make the next action apparent |
| Full selection can refer to168.44 while debt is268.44 | Keep pending100 and available168.44 clearly distinguished | Avoid implying a partial available amount settles the debt |

The intended model follows familiar checkout conventions and progressive disclosure, as described by [Nielsen Norman Group](https://www.nngroup.com/articles/progressive-disclosure/). Existing Card/Zelle/EFS selection, full/partial payment, draft preservation, explicit Zelle transfer reporting, EFS review and shop verification, cancellation/retry and financial contracts remain intact.

Independent evidence review: source detector found one existing gray-on-amber warning in the unavailable-link contact branch (InvoiceAccessPage line467); no detector finding explained the active payment hierarchy. Payment-panel scan returned no findings. No browser injection was performed. Source and live DOM establish redundant amounts and utility ordering. Screenshot scaling was unreliable during the initial review; visual proof must be checked alongside geometry and the actual browser surface before claiming preview acceptance.

Questions skipped: the user specified the desired refinement and explicitly required preserving the flow.

## Acceptance and runtime evidence

Implemented on `codex/payment-mobile-refinement` based on released `e2e8f720`. Guest header includes tenant logo and shop name; 44px mobile icon utilities retain accessible names. Full/partial selected pills are replaced by a quiet Partial payment action next to the amount, with Pay full balance or Use available to reset. The controlled customer/guest currency field rejects letters, signs, exponents, repeated decimal separators and more than two fractional digits before updating the draft; normal digits/cents, selection/copy/paste/navigation and empty transitional drafts remain supported. Staff amount entry is unchanged.

Payable guest invoice details collapse below payment; paid/history/read-only details remain expanded. The selected method has one truthful fee note: Card shows any fee before payment, Zelle has no card processing fee, and EFS has no card fee but account fees may apply. Architecture confirmed that invoice.service_fee_amount does not establish a current per-payment fee; no new fee policy or speculative fee inference is introduced. Zelle and EFS review actions stack at full width on mobile and remain inline on desktop.

Final checks:196/196 tests across10 focused files; changed-source ESLint across12 TSX files has no warnings/errors; shared-control generation, TypeScript and Vite production build pass; diff check passes.

Actual browser confirmation used existing fictional records through frontend5177 and the intentionally preserved API8019, environment test/database customer_efs_qa. Frontend PID38705/source `/private/tmp/tps-payment-mobile-refinement/frontend` was verified against the served feature. No old API, server, volume, tenant setting or financial record was changed. The fixture has no logo configured, so its preview uses the existing shop_logo_url query fallback with the actual observed public TPS logo; no branding record or hardcoded tenant fallback was added. Private URLs/credentials remain outside the repository.

Guest desktop1440 and mobile390/320 have no horizontal overflow. Mobile utility targets are44x44; method controls are44 high. At390 the Zelle actions are each290x44 on separate rows; at320 EFS review actions are each220x44 on separate rows. Desktop Zelle actions share one row. Actual guest typing rejects abc,1e3 and25.555 while retaining25.50, and switching Card/Zelle/EFS preserves that draft. Portal rejects -20 while preserving20.25; Use available restores168.44 with an existing100 pending request and268.44 due. No submit/cancel/provider/status/receipt action was performed; EFS review used a fictional local code, then returned and cleared it.

Initial browser wrapper/full-page captures could scale incorrectly despite correct DOM geometry. Final evidence uses CDP viewport capture after scrolling settles; malformed intermediary images were excluded. Final desktop/mobile screenshots are under the local `payment-mobile-focus` visualization directory (guest-desktop,guest-mobile,portal-desktop,portal-mobile,zelle-mobile).

Status: preview ready for user review, not deployed. Payment behavior, amount calculations, server authorization and financial records remain unchanged.

Draft [PR792](https://github.com/mecaniser/truck-pit-stop/pull/792) captures the reviewed product source `22a90a73`; subsequent documentation-only receipt changes do not change the served product. Protected PR CI remains a separate integration gate before merge/deployment.

## Authorized production release, November5

User approved PR792 merge/deploy and live customer/guest desktop/mobile verification without submitting payments or editing financial records. Preserved released fleet/Motive changes and the concurrent docs-only PR794. Invoice product bytes remain equal to the approved preview. Final head14f0fa51a097d8b1fc1c5d635b86538b22fc17c9 passed all7 checks in41982001863; backend suites were correctly scoped as unaffected, rather than claimed as executed. The initial ebf2de53 run also passed, but strict branch protection required incorporating concurrent main docs before merging. No protection bypass was used.

PR792 squash mergec7408389e668b1c1270639ef925879e01d7b7ee6 has exact tree equality with the final checked head. Automatic Web deploymentd265b1ec-4ac8-4c8e-ad7e-f63356cf8d2d succeeded on that SHA; www build-version and production DB/Redis readiness passed. No duplicate/forced deployment or worker/configuration change was performed.

Actual guest TPS1687 was verified at1440desktop and390mobile: tenant logo/name, compact utility controls, single balance hierarchy, partial/reset behavior, invalid-character rejection, preserved draft across methods, truthful fee notes, and local Zelle/EFS review/back. Both mobile confirmation actions are290x44 on separate rows; desktop Zelle actions remain inline. EFS review used an explicitly fictional transient code, then Edit details and clear; Submit for verification and transfer reporting were never clicked. Print opened the real one-page TPS1687 PDF.

Fresh guest access was one unsent1hour Redis link using the existing service and exact read-only invoice/payer/settlement guards; no notification, database write or provider action. Nontruncated browser request evidence contains only read operations (guest resolve/settlement/allocations and GET resources). After verification the normal page settlement read remained principal268.44, received0, pending100, available168.44 and version5. No payment, cancellation, receipt, provider status check or financial edit was performed. Screenshot/read-only receipts are in the local pr792-live visualization directory; private access tokens are excluded from this record.

Remaining gate: customer session expired on normal refresh and is at the production login page. In-app sign-in to the Elis Logistics customer account was requested. Customer desktop/mobile acceptance is blocked on that sign-in and is not claimed complete. Deployment and guest verification are complete; this item is not Done until customer acceptance is recorded.

## Final customer acceptance, November5

The user restored the production Elis Logistics customer session. Actual TPS1687 passed desktop1440 and mobile390x720 checks: compact hierarchy, Card/Zelle/EFS controls, partial10.25 draft preserved across methods, alphabetic input rejected without altering10.25, Use available restored168.44. Zelle instructions opened with10.25 and returned without reporting a transfer. Fictional EFS0000000000 was used only for local review, then edited and cleared; no submission. Mobile method controls are44px high; Zelle and EFS review action pairs are full-width44px controls on separate rows; document width equals390 with no horizontal overflow. Card Continue was never clicked.

Fresh normal page settlement responses before and after are identical, including version5: principal/outstanding268.44, received0, pending100, available168.44. Customer network capture truncated during full reload asset traffic; it is not represented as complete request-audit proof. Recorded UI actions performed no payment, cancellation, provider-status refresh or financial edit. Current customer-desktop.png, customer-mobile.png and customer-financial-preservation.json are in the local pr792-live evidence directory. Temporary mobile viewport override cleared. The customer sign-in blocker above is resolved; DB-149MOB acceptance is complete.
