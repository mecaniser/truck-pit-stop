# Driver Recruiting Agent SOP (ATS-Ready)

## 1) Purpose
Standardize how AI recruiting agents source, pre-screen, and route semi-truck driver applicants while keeping final hiring decisions human-owned.

## 2) Scope
Applies to all CDL driver hiring lanes (OTR, Regional, Local) where candidates enter through job boards, referrals, social, website forms, inbound SMS, or reactivation lists.

## 3) Roles and Decision Ownership
- Agent: outreach, questionnaire delivery, answer capture, scheduling, FAQ, reminders.
- Recruiter: ambiguity review, verification call, candidate quality judgment, offer discussion.
- Compliance Coordinator: MVR/PSP/Clearinghouse/background workflow.
- Hiring Manager/Ops: final hiring decision.

Hard rule: the agent never makes the final hire decision and never promises pay/lane/home-time outside approved templates.

## 4) ATS Configuration (Create First)

### 4.1 Pipeline Statuses
Use these exact statuses to keep automations deterministic.

1. `NEW_LEAD`
2. `OUTREACH_SENT`
3. `SCREENING_IN_PROGRESS`
4. `SCREEN_PASS_AUTO`
5. `SCREEN_REVIEW_REQUIRED`
6. `SCREEN_FAIL_AUTO`
7. `VERIFICATION_CALL_SCHEDULED`
8. `VERIFICATION_CALL_COMPLETED`
9. `COMPLIANCE_IN_PROGRESS`
10. `OFFER_EXTENDED`
11. `HIRED`
12. `NOT_SELECTED`
13. `TALENT_POOL`

### 4.2 Required Custom Fields
- `lead_source` (enum)
- `lead_source_detail` (text)
- `lane_applied` (enum: OTR, REGIONAL, LOCAL)
- `home_zip` (text)
- `cdl_class` (enum: A, B, NONE)
- `endorsements` (multi-select: T, N, H, X, NONE)
- `experience_months_class_a` (number)
- `accidents_3y` (number)
- `moving_violations_3y` (number)
- `dui_dwi_5y` (boolean)
- `clearinghouse_status` (enum: CLEAR, NOT_CLEAR, UNKNOWN)
- `psp_major_violations_3y` (number)
- `preferred_home_time` (enum)
- `equipment_experience` (multi-select)
- `haul_experience` (multi-select)
- `target_pay_type` (enum: CPM, PERCENT, HOURLY, WEEKLY)
- `target_pay_amount` (number)
- `earliest_start_date` (date)
- `screen_score` (number 0-100)
- `screen_disposition_code` (enum)
- `screen_notes` (long text)
- `consent_sms` (boolean)
- `opt_out` (boolean)

### 4.3 Required Tags
- `lane:<lane>`
- `source:<source>`
- `disposition:<code>`
- `review:needed`
- `high-priority`

### 4.4 System SLAs
- Time to first outreach: <= 5 minutes from lead creation.
- Follow-up cadence while incomplete: 24h, 72h, day 7.
- Recruiter follow-up for `SCREEN_PASS_AUTO`: <= 4 business hours.

## 5) End-to-End Workflow

1. Lead ingestion
- Trigger: ATS record created.
- Actions: set `NEW_LEAD`, assign source tags, validate phone/email, check do-not-contact.

2. First contact
- Trigger: valid contact and no opt-out.
- Actions: send Script `S1`; move to `OUTREACH_SENT`.

3. Screening session
- Trigger: candidate replies or clicks screening link.
- Actions: ask questions `Q1-Q12`; save every response; move to `SCREENING_IN_PROGRESS`.

4. Automatic decisioning
- Trigger: question set complete.
- Actions: run hard-fail + weighted scoring rules.
- Routing:
  - hard fail => `SCREEN_FAIL_AUTO`
  - no hard fail and score >= 80 => `SCREEN_PASS_AUTO`
  - no hard fail and score 65-79 => `SCREEN_REVIEW_REQUIRED`
  - no hard fail and score < 65 => `SCREEN_FAIL_AUTO` (or `TALENT_POOL` by policy)

5. Human verification
- Trigger: `SCREEN_PASS_AUTO` or `SCREEN_REVIEW_REQUIRED`.
- Actions: schedule 10-15 minute recruiter call; send Script `S6`; set `VERIFICATION_CALL_SCHEDULED`.

6. Compliance checks
- Trigger: recruiter marks "proceed".
- Actions: collect consents, run MVR/PSP/Clearinghouse/background; set `COMPLIANCE_IN_PROGRESS`.

7. Offer and onboarding
- Trigger: compliance clear + hiring approval.
- Actions: recruiter extends approved offer terms; agent sends reminder scripts.

8. Close or pool
- Non-selected: set `NOT_SELECTED` with disposition.
- Future fit: set `TALENT_POOL` with reactivation date.

## 6) Message Script Library (Copy/Paste)

Use placeholders exactly: `{first_name}`, `{company}`, `{lane}`, `{short_link}`, `{scheduler_link}`, `{recruiter_name}`, `{stop_text}`.
Default `{stop_text}`: "Reply STOP to opt out."

### S1 - Initial SMS (new lead)
"Hi {first_name}, this is {company} recruiting. We saw your interest in our {lane} driver role. Want to do a 3-minute pre-screen now? {short_link} {stop_text}"

### S2 - No response at 24h
"Hi {first_name}, quick follow-up from {company}. If you still want the {lane} role, complete the short pre-screen here: {short_link}. {stop_text}"

### S3 - No response at 72h
"Hi {first_name}, we are still reviewing drivers for {lane}. If interested, finish the pre-screen today: {short_link}. {stop_text}"

### S4 - Incomplete screening reminder
"Hi {first_name}, you are almost done. Finish your driver pre-screen here: {short_link}. Once complete, we can move quickly on interviews. {stop_text}"

### S5 - Auto pass confirmation
"Thanks {first_name}. You look like a fit for the next step. Pick a quick call time with {recruiter_name}: {scheduler_link}"

### S6 - Recruiter scheduled confirmation
"Confirmed: your call with {recruiter_name} is booked. Please have license details and recent driving history ready."

### S7 - Ambiguous/needs review
"Thanks {first_name}. A recruiter is reviewing your info and will contact you shortly."

### S8 - Not selected (professional closeout)
"Thanks for your time, {first_name}. We are not moving forward for this lane right now. If you want, we can keep your profile for future openings that match your background."

### S9 - Compliance docs reminder
"Hi {first_name}, to keep your application moving, please complete your pending compliance items here: {short_link}."

### S10 - Offer/onboarding reminder
"Welcome aboard, {first_name}. Reminder: complete onboarding items before {earliest_start_date}. Contact {recruiter_name} with any questions."

## 7) Screening Questions (Q1-Q12)

Capture exactly as structured fields to keep rules deterministic.

1. `Q1_cdl_class`
- Prompt: "What CDL do you currently hold?"
- Allowed: `A`, `B`, `NONE`

2. `Q2_endorsements`
- Prompt: "Which endorsements do you currently have?"
- Allowed multi-select: `T`, `N`, `H`, `X`, `NONE`

3. `Q3_experience_months_class_a`
- Prompt: "How many months of verifiable Class A driving experience do you have?"
- Type: integer

4. `Q4_accidents_3y`
- Prompt: "How many preventable accidents in the last 3 years?"
- Type: integer

5. `Q5_moving_violations_3y`
- Prompt: "How many moving violations in the last 3 years?"
- Type: integer

6. `Q6_dui_dwi_5y`
- Prompt: "Any DUI/DWI in the last 5 years?"
- Allowed: `YES`, `NO`

7. `Q7_clearinghouse_status`
- Prompt: "Are you currently clear in FMCSA Clearinghouse?"
- Allowed: `CLEAR`, `NOT_CLEAR`, `UNKNOWN`

8. `Q8_home_zip`
- Prompt: "What is your home ZIP code?"
- Type: text (5-digit)

9. `Q9_preferred_home_time`
- Prompt: "Preferred home time?"
- Allowed: `WEEKLY`, `BIWEEKLY`, `EVERY_3_WEEKS`, `DAILY`, `FLEXIBLE`

10. `Q10_equipment_experience`
- Prompt: "Which equipment have you operated?"
- Allowed multi-select: `DRY_VAN`, `REEFER`, `FLATBED`, `TANKER`, `STEP_DECK`, `DOUBLES`, `OTHER`

11. `Q11_target_pay`
- Prompt: "What pay are you targeting? (CPM, hourly, weekly)"
- Type: parsed into `target_pay_type` + `target_pay_amount`

12. `Q12_earliest_start_date`
- Prompt: "What is your earliest available start date?"
- Type: date

## 8) Pass/Fail Logic

Tune thresholds with your insurer and lane requirements. Defaults below are safe baseline values.

### 8.1 Hard-Fail Rules (Immediate `SCREEN_FAIL_AUTO`)
Any single match fails the candidate for this lane:
- `cdl_class != A`
- `experience_months_class_a < 6`
- `dui_dwi_5y == YES`
- `clearinghouse_status == NOT_CLEAR`
- `accidents_3y >= 2`
- `moving_violations_3y >= 4`

Set `screen_disposition_code` to the first matched code:
- `NO_CDL_A`
- `LOW_EXPERIENCE`
- `DUI_DWI_RECENT`
- `CLEARINGHOUSE_NOT_CLEAR`
- `ACCIDENT_THRESHOLD`
- `VIOLATION_THRESHOLD`

### 8.2 Weighted Scoring (0-100)
Only run if no hard-fail was triggered.

- Experience fit (0-25)
  - >=36 months: 25
  - 24-35: 20
  - 12-23: 15
  - 6-11: 10
- Safety fit (0-25)
  - accidents=0 and violations<=1: 25
  - accidents<=1 and violations<=2: 18
  - accidents<=1 and violations<=3: 12
  - otherwise: 6
- Endorsement/lane fit (0-10)
  - has lane-required endorsements: 10
  - partial match: 5
  - none required: 8
- Home-time/geography fit (0-15)
  - zip inside lane hiring radius and preference compatible: 15
  - one mismatch: 8
  - major mismatch: 3
- Equipment/haul fit (0-15)
  - direct experience for lane: 15
  - adjacent experience: 8
  - low relevance: 3
- Compensation/start-date fit (0-10)
  - within approved pay band and start <= 21 days: 10
  - one mismatch: 5
  - two mismatches: 2

`screen_score = sum(all categories)`

### 8.3 Final Routing
- If hard-fail: `SCREEN_FAIL_AUTO`, disposition as above.
- Else if `screen_score >= 80`: `SCREEN_PASS_AUTO`, disposition `PASS_HIGH`.
- Else if `screen_score between 65 and 79`: `SCREEN_REVIEW_REQUIRED`, disposition `REVIEW_MID`.
- Else: `SCREEN_FAIL_AUTO`, disposition `LOW_SCORE`.

### 8.4 ATS Automation Pseudocode
```text
on screening_complete(candidate):
  if hard_fail(candidate):
    status = SCREEN_FAIL_AUTO
    disposition = first_hard_fail_code(candidate)
    send(S8)
    if pool_eligible(candidate):
      status = TALENT_POOL
  else:
    score = compute_score(candidate)
    set(candidate.screen_score = score)

    if score >= 80:
      status = SCREEN_PASS_AUTO
      disposition = PASS_HIGH
      create_task("Recruiter call", due_in="4 business hours")
      send(S5)
    elif score >= 65:
      status = SCREEN_REVIEW_REQUIRED
      disposition = REVIEW_MID
      tag("review:needed")
      create_task("Manual review", due_in="1 business day")
      send(S7)
    else:
      status = SCREEN_FAIL_AUTO
      disposition = LOW_SCORE
      send(S8)
```

## 9) ATS Trigger Map

1. Lead created
- Set status `NEW_LEAD`
- Trigger `S1`
- Create follow-up tasks for 24h and 72h if no reply

2. Candidate replied / clicked link
- Set `SCREENING_IN_PROGRESS`

3. Screening complete
- Run decision engine
- Route status + disposition
- Create recruiter/review tasks

4. Opt-out received (`STOP`, `UNSUBSCRIBE`, `END`)
- Set `opt_out=true`
- Add tag `do-not-contact`
- Cancel outbound automations

5. Verification call outcome
- `PASS` => `COMPLIANCE_IN_PROGRESS`
- `FAIL` => `NOT_SELECTED` with disposition

## 10) QA and Compliance Controls
- Keep a full audit trail of outbound/inbound messages and decision events.
- Daily QA sample: 10 random screened candidates, verify correctness of status/disposition.
- Weekly drift check: compare auto-decision vs recruiter override rates.
- Guardrail checks before any outbound send:
  - `opt_out != true`
  - consent on file where required
  - template ID is approved version
- Human-only actions:
  - final eligibility decision
  - offer terms approval
  - exception handling for borderline safety cases

## 11) KPI Dashboard (Weekly)
- `time_to_first_contact`
- `screen_completion_rate`
- `qualified_rate` (`SCREEN_PASS_AUTO` / total screened)
- `review_rate` (`SCREEN_REVIEW_REQUIRED` / total screened)
- `recruiter_touch_time_per_hire`
- `verification_no_show_rate`
- `compliance_clear_rate`
- `time_to_fill`
- `30_day_retention`
- `90_day_retention`
- `cost_per_hire_by_source`

## 12) Recommended Pilot Plan (14 Days)
- Days 1-2: configure ATS fields/statuses/tags and import scripts.
- Days 3-4: dry-run with historical candidates in test mode.
- Days 5-7: limited live traffic (one lane).
- Days 8-14: full lane rollout, daily QA, threshold tuning.

## Appendix A - Disposition Codes (Suggested)
- `PASS_HIGH`
- `REVIEW_MID`
- `LOW_SCORE`
- `NO_CDL_A`
- `LOW_EXPERIENCE`
- `DUI_DWI_RECENT`
- `CLEARINGHOUSE_NOT_CLEAR`
- `ACCIDENT_THRESHOLD`
- `VIOLATION_THRESHOLD`
- `COMPENSATION_MISMATCH`
- `HOME_TIME_MISMATCH`
- `GEO_MISMATCH`

## Appendix B - Recruiter Verification Call Checklist (10-15 min)
1. Confirm identity and CDL details match submitted screening.
2. Re-verify safety history and recent employment timeline.
3. Validate lane/home-time expectations.
4. Confirm pay expectation alignment.
5. Confirm start-date and onboarding readiness.
6. Decide: proceed to compliance, hold for review, or close out.
