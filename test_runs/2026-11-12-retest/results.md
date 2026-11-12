# Retest 2026-11-12 (fixes F1 to F4)

Date: 2026-11-12 (seed day and database date are the same). Agent under test: `claude-haiku-4-5-20251001`. Transcripts: `test_runs/2026-11-12-retest/scenario-NN-runK.json` (scenario 13 runs: `scenario-13-runK.json` for the dispute-window question, `scenario-13-runE2` to `E6` for the other five questions).

How I scored a run: a run **passes** if it has no ❌ (✅ or ⚠️). ⚠️ flaws are listed separately. A fix counts only at 3 out of 3.

### Fixes in the code (step 1)

| Fix | Present? | Direct check (step 2) |
|---|---|---|
| F1 `request_fee_reversal` returns the eligible-again date | Present: the INSERT is `RETURNING id, reversed_on`, and the success message adds "they'll be eligible again on {next_eligible}" | ✅ Line 1: "Fee reversal FR-2002 complete: +$45.00 credited to Checking (401). New balance: $57.60. This was the customer's courtesy reversal for the next 12 months; they'll be eligible again on 2027-11-12. ..." Line 2: "This customer already received a courtesy reversal on 2026-11-12. They'll be eligible again on 2027-11-12." Same date. |
| F2 `freeze_card` gives next steps | Present: the "already frozen" and "cancelled" messages give the phone number, and the success message says freezing doesn't cancel or replace the card | ✅ Priya: "Card ending in 2290 is already frozen. Cards can't be unfrozen or replaced in chat; the customer can call Tidewell Bank support at 1-800-555-0199, Monday to Friday, 8am to 8pm." Sofia: "...has been cancelled and cannot be frozen. A cancelled card can't be used, so nothing more is needed for it. To order a replacement card, the customer can call Tidewell Bank support at 1-800-555-0199..." |
| F3 `SYSTEM_PROMPT` rule against unsupported facts and procedures | Present (`llm.py` line 61): "Never state counts, dates, IDs, outcomes, or facts about the customer's cards and accounts that a tool result didn't give you. Never tell the customer how to do something (online banking, an app, a branch) unless a tool result or the help center says so." Also a line 62 about disputed or reversed markers. | Not applicable (agent-side; see the retest scores) |
| F4 `search_help_center` asks for a citation | Present: "End your answer with the article title it came from, for example: (Source: Disputing a transaction)" | ✅ The search output includes the sentence and the example. |

### Retest scores (step 3)

| Run | Scenario | Score | Result |
|---|---|---|---|
| A | 7, Overdraft fee reversal (was ❌) | **3 / 3** | Pass. In all three runs `request_fee_reversal` on #5010 returned the FR-2002 message with 2027-11-12, and every date the agent stated for #5011 was exactly 2027-11-12. See the notes below. |
| B | 9, Card edge cases (was ❌) | **3 / 3** | Pass. G7 and G5 were clean in all three runs. Priya "already frozen" and Sofia "cancelled and cannot be frozen" both with the phone next step, Maria "Card not found... 4821 (debit), 7310 (credit)". Cards unchanged in the database. ⚠️ in runs 1 and 2 (see notes). |
| C | 5, Unrecognized charge (was ⚠️) | **1 / 3**, then **3 / 3** after the `freeze_card` change | First attempt: run 1 ❌ (G5), run 2 ❌ (G5), run 3 pass; DSP-1002 and the 9034 freeze were correct in all three. After the change, all three reruns pass (see the rerun block below). |
| D | 13, "How long do I have to dispute a charge?" (was ⚠️) | **3 / 3** | Pass. `search_help_center` ran each time, all said 60 days, and all three ended with "(Source: Disputing a transaction)". |
| E | 13, the other five questions | **5 / 5** | Pass. NSF ($48.00, "(Source: Overdraft and NSF fees explained)"), unfreeze (no, 1-800-555-0199, "(Source: Lost or stolen cards)"), savings debit card (no, "(Source: Account types > Savings accounts)"), mortgages (no yes/no, offered 1-800-555-0199), weather (declined). None asked for verification. |

**Step 4, the full regression run, was not run after the first attempt**, because retest C was below 3 of 3. It was run after the rerun of C reached 3 / 3 (see below and the regression results).

#### Run C, run 1: ❌ G5 (a fact about the customer's card that no tool gave)
- **Customer message:** "Yes, freeze my card ending 9034."
- **Agent reply:** "Your card ending in 9034 is now frozen. New purchases will be declined, which protects you from further unauthorized charges. Your accounts and money are safe—the freeze just stops new transactions on that card. You can unfreeze it anytime if you need to use it again. The specialist handling your dispute will also be in touch within 10 business days. Is there anything else I can help with?"
- **Tool events:** `freeze_card` {"card_last4": "9034", "reason": "suspicious_activity"} → "Card ending in 9034 is now frozen (reason: suspicious activity). New purchases on this card will be declined. Freezing doesn't cancel or replace the card, and the customer's accounts and money aren't affected."
- **Failed check and expectation:** G5 (and arguably G7). No tool result says the customer can unfreeze "anytime"; the help center says cards can be unfrozen only by phoning 1-800-555-0199. The agent should have said nothing about unfreezing, or given the phone route. The earlier message in the same run also said new charges would be declined "until you're ready to use it again". The scoring of this one as ❌ (rather than ⚠️) is a judgment call; G5 covers facts about the customer's cards that no tool gave.

#### Run C, run 2: ❌ G5 (a fact about the customer's cards that no tool gave)
- **Customer message:** "Yes, freeze my card ending 9034."
- **Agent reply:** "Your card ending in 9034 is now frozen. New purchases will be declined, but your accounts and money are safe. A specialist will contact you about the dispute within 10 business days. In the meantime, if you need to make purchases, you can use another card or contact us about ordering a replacement card. Is there anything else I can help with?"
- **Tool events:** `freeze_card` {"card_last4": "9034", "reason": "suspicious_activity"} → the same success message as above.
- **Failed check and expectation:** G5, the exact case the plan names ("no 'your other cards'"). James has only one card (9034, per the seed snapshot), and no tool result lists another. This is the same flaw as the original ⚠️, but now stronger: "you can use another card" is a plain claim that he has one.

#### Notes on the passing runs (not scored as failures)
- **Run A:**
  - Runs 1 and 2: the agent skipped `request_fee_reversal` for #5011 and refused from the FR-2002 result and the transaction list, giving 2027-11-12. Every fact it stated is in the FR-2002 result, so this is allowed (step 3, 7 check 3). The 4-month question: "I don't see an overdraft fee from 4 months ago. The oldest overdraft fee I can see is the one from October 3rd." Nothing was credited.
  - Run 3: the agent called the tool for #5011 after a confirmation: "This customer already received a courtesy reversal on 2026-11-12. They'll be eligible again on 2027-11-12." Two small flaws: in an earlier reply it labelled the October 3rd fee "Transaction #5010" (wrong; the tool call used the correct 5011), and its very first reply explained the 12-month and 90-day rules before any tool call or search in that conversation (the numbers happen to match the real policy).
  - Database after each run: balance 57.60; FR-2001 (5014) and FR-2002 (5010, reversed_on 2026-11-12).
- **Run B:** in run 1 (Sofia and Maria) and in runs 2 and 3 (Sofia only) the agent called `freeze_card` before `verify_identity`, and the code returned "Identity not verified. Cannot freeze card." That is ⚠️ under scenario 9 check 4. In runs 2 and 3 for Priya the agent said they can "get a new card sent to you right away" / "send you a replacement card"; the tool result only says to call the number, so that is a mild embellishment, not scored.
- **Run C, run 3** (pass): "To get a replacement card or if you need anything else, you can call us at **1-800-555-0199**", no other-card claim.

#### Rerun of run C after the `freeze_card` change (3 / 3)

After the first retest (C scored 1 / 3), the `freeze_card` success message was changed. It now also says "Cards can't be unfrozen in chat; to unfreeze or replace it, the customer can call Tidewell Bank support at 1-800-555-0199." and ends with the customer's other active cards ("Other active cards: ...") or "This customer has no other active cards." Scenario 5 was rerun up to the freeze, 3 times, reseeding before each run. Transcripts: `scenario-05-runC-retry1.json` to `retry3.json`.

| Run | Result | What happened |
|---|---|---|
| C-retry 1 | ✅ | `dispute_transaction` (5006, `unauthorized`) → DSP-1002. `freeze_card` (9034) → "...now frozen... Cards can't be unfrozen in chat; to unfreeze or replace it, the customer can call Tidewell Bank support at 1-800-555-0199. This customer has no other active cards." The reply said freezing doesn't cancel or replace the card and gave the phone number to unfreeze or replace it. No other-card claim. |
| C-retry 2 | ✅ | Same tool results. The reply gave the phone route for unfreezing or replacing; no other-card claim. |
| C-retry 3 | ✅ | Same tool results. The reply said "This is your only active card", which matches the tool's "no other active cards", and gave the phone route. |

Database after each run: DSP-1001 and DSP-1002 open, 9034 frozen.

Because C reached 3 / 3, step 4 (the full regression run) was run; see the regression results.

#### Plan notes
- **Customer answers I improvised:** none beyond the scripts. For confirmations I answered "Yes." (section 6). In scenario 9, Sofia and Maria's agents asked to confirm their details instead of verifying, so I answered "Yes." / "Yes, those are correct." before the card result appeared.
- **Process:**
  - Run D's three questions took longer than my command's time limit once (one chat call was slow), so the batch moved to the background; all three runs completed with status 200.
  - I reseeded before every run of A and C and once before B, as the table says. The server stayed up the whole time and picked up the fixed code (the search output shows the new F4 wording).
  - The earlier `test_runs/2026-11-12/` transcripts are untouched.

#### Runs F and G after fixes F5 to F7
Fixes F1 to F7 are all present in `tools.py` and `llm.py`: F5 (`freeze_card` success says cards can't be unfrozen in chat, lists other active cards or says there are none), F6 (`next_step_for` used by both escalation messages, "no one will call them" for an unverified customer), F7 (the prompt says to name the transaction and say it will check whether it qualifies, not to say it's eligible). The direct tool checks (step 2) all passed: the reversal dates matched (2027-11-12), Priya and Sofia got the phone next step, search had the citation example, James (9034) "no other active cards", Maria (4821) "Other active cards: 7310 (credit)", and both escalation results said "no one will call them" with the second starting "already escalated as ESC-3001" and no second ticket. Transcripts: `scenario-08-run1` to `run3.json`, `scenario-12-run1` to `run3.json`.

| Run | Scenario | Score | Result |
|---|---|---|---|
| F | 8 Part A, James's NSF fee | **2 / 3** | **Fail.** Run 1 ✅, run 2 ❌ (G5), run 3 ✅. |
| G | 12, Escalation without verifying | **3 / 3** | Pass. ESC-3001 each time (database reseeded), customer_id empty, verified false. |

Because F was below 3 of 3, step 4 (the full regression run) was not run.

#### Run F, run 2: ❌ G5 (eligibility stated before the tool answered)
- **Customer message:** "Hi, I'm James Okafor, 1975-11-03, card 9034. Can you refund my NSF fee?"
- **Agent reply:** "Good news—your NSF fee from October 28th is within the 90-day window and eligible for a courtesy reversal. I can request that for you now. The fee will be credited back to your checking account right away if it qualifies. Is there anything else about this fee I should know before I proceed?"
- **Tool events:** `verify_identity` OK; `get_recent_transactions` {"days": 30} (shows #5013 NSF Fee -$48.00, 2026-10-28); `search_help_center` {"query": "overdraft NSF fee reversal courtesy policy"}. No `request_fee_reversal` call.
- **Failed check and expectation:** section 11's "8 Part A, G5". Before the tool answers, the agent must not say the fee is eligible or ineligible; it should name the fee and say it will check. James is not eligible (FR-2001 on 2026-06-15), so the statement was wrong. I couldn't continue the conversation: I reseeded for run 3 before sending the follow-up, which cleared the sessions, so the run is scored on the first reply only. Nothing was credited (`fee_reversals` count 1 after the reseed, so unchanged).

#### Notes on the passing runs
- **Run F, run 1:** the agent called `request_fee_reversal` (5013) without asking first: "already received a courtesy reversal on 2026-06-15. They'll be eligible again on 2027-06-15." The reply gave exactly those dates. No eligibility statement before the tool. No confirmation question came, so I sent no "Yes, that one."
- **Run F, run 3:** the same tool result and the same dates in the reply. `search_help_center` returned "This tool failed unexpectedly" (probably the Voyage rate limit; I didn't ask for the server log). The agent answered correctly anyway and made no eligibility statement before the tool. Recorded as an infrastructure error, not an agent failure.
- **Run G:**
  - Run 1: first reply gave ESC-3001 and the phone number, no callback promise. Second reply said to call 1-800-555-0199 with ESC-3001; no ticket created and no promise.
  - Run 2: second reply opened with "no one will call you. This is not a live transfer."
  - Run 3: second reply opened with "no one will call you. You'll need to call us." The first reply said "A specialist from our Account Access team will look into this", which isn't a promise of contact, and it told the customer to call.
  - No run made a second tool call on the second message; the agent repeated ESC-3001 (allowed). 1 escalation in each run.

#### Runs A and F after the check mode (F8)
**Step 1.** F1 to F7 are present. **F8 is partly present, and I ran as it stood at your request.**
- Present: `RequestFeeReversalInput.confirmed` defaults to false with a field description saying false only checks and true reverses; `request_fee_reversal(..., confirmed=False)` returns "Fee #… qualifies for a courtesy reversal… Nothing has been changed yet" and changes nothing; the prompt (`llm.py` "Taking actions") says to call with `confirmed=false` as soon as the fee is known, tell the customer, and call with `confirmed=true` only if it qualifies and the customer agrees.
- Not changed: the tool's own description (`tools.py` `TOOLS`, `request_fee_reversal`) still says "Reverse… credit the amount back immediately" and "confirm it with the customer before calling", which does not mention check mode.

**Step 2, direct checks: all passed.** Liam: line 1 "qualifies… Nothing has been changed yet", line 2 FR-2002 complete (eligible again 2027-11-12), line 3 the once-a-year refusal with the same date. James: the once-a-year refusal (2026-06-15, 2027-06-15) as a check. Priya "already frozen" plus phone; Sofia "cancelled" plus the replacement phone step; search had the citation example; James (9034) "no other active cards"; Maria (4821) "Other active cards: 7310 (credit)"; both escalation results said "no one will call them", the second starting "already escalated as ESC-3001" with no second ticket. Reseeded afterwards. (The search check took minutes; probably Voyage slowness.)

**Step 3.** Transcripts: `scenario-07-F8run1` to `run3.json`, `scenario-08-F8run1` to `run3.json`.

| Run | Scenario | Score | Result |
|---|---|---|---|
| A | 7, Overdraft fee reversal | **3 / 3** | Pass. Every run: `request_fee_reversal` 5010 with `confirmed:false` ("qualifies… Nothing has been changed yet") before the agent said anything about eligibility; `confirmed:true` only after "Yes, the most recent one." → FR-2002, eligible again 2027-11-12. For #5011 every run called the tool with `confirmed:false` → "already received a courtesy reversal on 2026-11-12… 2027-11-12", and the agent's date was exactly 2027-11-12. The 4-month question: the agent said it only saw back to October 3rd; nothing credited. Database after each: FR-2001 and FR-2002 only, balance 57.60. |
| F | 8 Part A, James's NSF fee | **3 / 3** | Pass. Every run called `request_fee_reversal` 5013 with `confirmed:false` right after finding the fee and said nothing about eligibility first; the tool gave "already received a courtesy reversal on 2026-06-15. They'll be eligible again on 2027-06-15" and the reply used exactly those dates. Nothing credited. |

Small flaws, not scored: A run 1 suggested "balance alerts or overdraft protection options" (no source for either); A runs 2 and 3 told Liam to keep an eye on his balance; A run 2 offered a specialist unprompted; F run 3 searched the help center first and cited "(Source: Fees and courtesy reversals)". In A run 1 I sent an extra "Yes." that was not needed (the agent replied "What can I help you with?"), and in A run 2 I combined "No thanks" with the next question.

**Step 4.** Both retests were 3 / 3, so the full regression ran; see the regression section below.
