# 4. Changes in Odoo

[← Data and security](3-data-and-security.md) · next: [Roadmap →](5-roadmap.md)

**Genie never changes Odoo on its own. The AI can only prepare a draft; a person presses Confirm, and only then
does Genie write.** Off by default; web (Ask) only.

## The flow

```mermaid
sequenceDiagram
    autonumber
    actor M as Member
    participant ASK as Ask
    participant AG as Agent + AI
    participant DB as Supabase (odoo_actions)
    participant OD as Customer's Odoo

    M->>ASK: "Log a lead for Mr Chan, 2-bed in Taikoo, budget 35k"
    ASK->>AG: question
    AG->>DB: create_lead → draft row (status: proposed)
    AG-->>ASK: "Check the draft below and press Confirm"
    ASK-->>M: draft card: Confirm / Cancel
    M->>ASK: Confirm
    ASK->>DB: re-check switches + daily limit · claim the draft
    ASK->>OD: write with the Genie Odoo user's key
    ASK->>OD: note on the record: "Done by Genie at the request of …"
    ASK->>DB: status: done · record id · draft values cleared
    ASK-->>M: ✓ link to the record in Odoo
```

## A draft's life

```mermaid
stateDiagram-v2
    [*] --> proposed: AI prepares a draft
    proposed --> cancelled: Cancel
    proposed --> expired: no decision in 24 h
    proposed --> writing: Confirm (draft claimed)
    writing --> done: Odoo saved it
    writing --> failed: error or timeout
    done --> [*]
    cancelled --> [*]
    expired --> [*]
    failed --> [*]
    note right of writing
        stored as status "failed",
        error "in progress"
        until the write finishes
    end note
```

Every row's draft values are cleared once it's decided. Who / what / which record stays for one year, shown in
**Settings → Activity**.

## What an owner can switch

Settings → Data sources → **Changes in Odoo** (stored in `tenants.settings.odoo_changes`):

| Setting | Choices |
|---|---|
| Master switch | Off (default) / on |
| Write key | API key of a dedicated Genie Odoo user (Vault `odoo_write_key`), separate from the reading key |
| Actions | `create_lead`, `create_contact`, `add_note`, `schedule_follow_up`, `update_record`, each on/off plus who may ask |
| Fields allowed for updates | `model:field` pairs, picked from Odoo's own field list |
| Daily limit | Default 50 changes |

## Safeguards

| Safeguard | Why |
|---|---|
| Draft first, person confirms | The AI can misread a request; nothing reaches Odoo unseen |
| Only the requester or an owner/admin can confirm | A member can't confirm someone else's change |
| Switches and limit checked again at Confirm | Turning a switch off also stops drafts already waiting |
| Draft claimed before writing | A double click can't write twice |
| Salesperson / to-do owner = the Odoo user with the member's email | The record shows who it belongs to |
| "Done by Genie at the request of …" note on the record | Odoo's own history shows where the change came from |
| Separate write key | A dedicated Odoo user with only the rights Genie needs |

## Known weakness

If Odoo saves the change but its reply times out, Genie marks the draft **failed** and drops it. Asking again
then creates a **duplicate**. The fix (an operation key written with the change and checked before marking failed) is
item 1 of [platform hardening](5-roadmap.md#platform-hardening).

C21 has only one Odoo user, so the same key is pasted into both reading and writing for now.
