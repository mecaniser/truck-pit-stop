---
name: DieselBridge Communications Prototype
description: Compact staff inbox extending the established DieselBridge presentation.
colors:
  navy: "#0b1728"
  road-white: "#f6f8fb"
  surface: "#ffffff"
  ink: "#17283b"
  muted: "#617084"
  line: "#e2e7ec"
  green: "#126b59"
  selected: "#eaf3ef"
  inbound: "#f0f3f6"
  outbound: "#e7f2ec"
  focus: "#bd4910"
typography:
  body:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "14px"
  title:
    fontSize: "27px"
    fontWeight: 650
    letterSpacing: "-0.8px"
  message:
    fontSize: "12px"
    lineHeight: 1.65
rounded:
  control: "7px"
  composer: "9px"
  workspace: "16px"
components:
  button-primary:
    backgroundColor: "{colors.green}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "10px 14px"
---

# Communications prototype design

## Overview

This is an extension of the established DieselBridge staff app: navy rail, road-white workspace, green actions, and compact operational content. Desktop staff work is the primary posture. The fixed direction introduces no newly approved visual world or alternative composition; root `PRODUCT.md` and `DESIGN.md` remain the product-wide references.

Scope is the standalone prototype in `frontend/src/features/communications/` and `frontend/prototypes/communications/`, served in isolation at `http://127.0.0.1:5186`. The independent [prototype review](PROTOTYPE_REVIEW.md) returned **SHIP for prototype presentation only** from screenshots and source. This document records that scope, not production acceptance.

## Colors

Navy frames the light work surface. Green identifies primary actions, selection, and outgoing conversation bubbles; pale gray distinguishes incoming messages. Fine neutral lines separate functional panes. Amber delivery alerts and restriction copy carry caution; copper provides visible keyboard focus. Keep status text and icons alongside color.

## Typography

Use the native sans-serif stack. The page title is 27px on desktop and 23px on phones. Messages are 12px with generous line height, rising to 14px at 1600px; compact metadata ranges from 9–11px. This describes the prototype's observed density, not a new app-wide minimum-size rule.

## Layout

The desktop shell uses a 68px rail and a viewport-height rounded workspace. Its inbox grid is `330px minmax(330px, 1fr) 258px`: queue, conversation, and contact/repair context. At 1600px it expands to `360px minmax(400px, 1fr) 280px`. Each long pane scrolls internally; the composer stays outside message scrolling.

At 1200px and below, context becomes an explicitly opened 280px overlay and the remaining grid is `300px minmax(320px, 1fr)`. At 700px and below, the rail disappears and list/thread become separate full-width panes. Selecting a row opens the thread; Back returns to the list. Contact details open over the current pane and close explicitly. Do not squeeze all desktop columns onto a phone.

## Elevation & Depth

Pane borders and quiet surface changes provide most separation. Shadows are limited to contact context, channel setup, and feedback. The selected row has a 2px green inset edge. The service-update switch has a 150ms ease-out transition; reduced-motion CSS removes transitions. There is no ambient motion.

## Shapes

Controls use restrained 5–9px corners, the workspace uses 16px, and avatars are circular. Message bubbles use 11px corners with a 3px sender-side bottom corner. Lucide icons and chevrons support controls; action labels stay on one line.

## Components

- **Queue:** Open, Unread, Mine, and Resolved views combine with channel filters and case-insensitive search across contact, company, identity, vehicle, repair order, and message text. Results sort newest first. Selecting a conversation clears its preview unread count. Filtering the list does not automatically replace the selected conversation.
- **Thread:** Incoming and outgoing bubbles remain distinct from centered service-update events. Service updates toggles event visibility only; it does not enable or disable an automation. Assignment and Resolve/Reopen change local preview state. Failed, undelivered, and unknown samples expose delivery details without a retry action.
- **Context:** Contact identity, current repair, vehicle, assignment, and conversation status support the thread. A chat reply does not approve repair work. The rail is presentation context, not implemented application routing.
- **Composer:** Saved replies append to the current draft and restore composer focus. Enter inserts a newline; Cmd/Ctrl+Enter invokes the same guarded preview action as the button. Nonempty trimmed text up to 1600 characters is eligible only when `canSend` is true and the restriction reason is null.
- **Draft identity:** The key includes tenant, user, conversation, channel, channel account, and contact identity. Changing thread or reply channel retains separate drafts within the mounted preview. Drafts, messages, assignment, and resolution live only in React memory and reset on reload; there is no persistent browser storage.
- **Preview send:** Adds a local queued message displayed as “Preview only,” reopens the conversation, updates its preview/order, and clears only the active draft. It never claims new provider acceptance or delivery.
- **Restrictions:** Opt-out, unverified identity, uncertain outcome, missing connection, WhatsApp template requirement, and Telegram customer-start requirement are represented by the model. Unsupported channel changes block sending while allowing draft writing. Fixture states and copy illustrate rules; they are not provider enforcement.
- **Channel setup:** The modal sheet labels SMS “Preview active” and WhatsApp/Telegram “Planned.” It closes through its button, Escape, or backdrop; source contains focus containment and return to Channels. New message selects from sample contacts. Neither control provisions an account or creates a real customer conversation.

## Do's and Don'ts

- Do preserve the compact staff hierarchy, explicit pane navigation, separate draft identities, restriction messages, and visible sample/no-send boundary.
- Do treat `communications.css` and the React/model source as implementation truth. Review captures are `.impeccable/review/desktop.jpg` (1280×720), `mobile.jpg`, and `mobile-list.jpg` (390×844); they do not establish every responsive or keyboard state.
- Don't infer authentication or server-enforced tenant isolation from fixture filtering. This standalone preview has no API/auth integration, application network transport, or provider calls.
- Don't describe planned backend migrations, durable outbox, callbacks, delivery reconciliation, persistent drafts, or WhatsApp/Telegram integration as implemented by this prototype. The [shared inbox contract](SHARED_INBOX_CONTRACT.md) is separate planning evidence.
- Don't apply these prototype-specific tokens globally or replace root design guidance without a separate product decision.
