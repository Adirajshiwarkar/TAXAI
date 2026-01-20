🌐 Big Picture: What Your ITR Filing Agent Must Do

To file ITRs on behalf of users as an ERI (Electronic Return Intermediary), your product must perform these steps:

Authenticate yourself (ERI Login)

Add taxpayer as a client
(with OTP consent, unless already added)

Request & fetch Prefill

Validate ITR form

Submit ITR

Retrieve Acknowledgement (PDF)

e-Verify the return
(Aadhaar OTP or EVC)

Every one of these is a separate REST API with strict requirements:

Base64-encoded request body

Digital Signing of every request

DSC X.509 certificate

authToken from Login API

clientId & clientSecret in header

🔐 1. Login API — Establish ERI Session

Source: Login API spec 

API_Login_v1.1

Purpose

Every interaction starts with creating an authenticated session. You get an authToken, which must be sent with all subsequent APIs.

What Your Agent Must Handle

Build Base64 payload containing
serviceName = "EriLoginService",
entity (ERI user ID),
pass (encrypted password).

Digitally sign the payload.

Store authToken securely for that session.

Notes

ERI Type-2 uses single-call password login.

OTP-based login flows exist but are for ERI-3.

👤 2. Add Client API — Getting Legal Consent from Taxpayer

Source: Add Client API spec, pages 5–10 

API_AddClientFlow_v1.1

Why This Matters

You cannot access taxpayer’s prefill data or submit returns unless the taxpayer explicitly consents to adding you as their ERI.

Step A — addClient

Send PAN + DOB + OTP source flag ("E" or "A").

Taxpayer receives OTP.

Step B — validateClientOtp

User enters OTP into your app.

You call this API with:

PAN

OTP

transactionId received from Step A

otpSourceFlag

On success → taxpayer is added as your client.

Product Design Implication

Your UI/UX must guide the user through:

Entering PAN + DOB

Choosing OTP method

Entering OTP
Your backend must store transactionId temporarily until OTP verification.

📥 3. Prefill API — Fetching Taxpayer's Income Data

Source: Prefill API spec, pages 4–9 

API_Prefill_v1.1

Purpose

Fetches all prefilled information required to prepare ITR:

Personal info

Salary (16A), TDS details

Bank accounts

AIS/TIS-linked reported amounts, etc.

Step A — requestPrefillOTP

Send PAN + Assessment Year + OTP source flag.

Taxpayer receives OTP.

Step B — getPrefill

Send OTP + transactionId.

API returns full Prefill JSON, following schema from the schema ZIP you uploaded.

Product Design Implication

Your agent's core intelligence (AI assistant) will operate on this Prefill JSON and generate a filled ITR form.

🧾 4. Validate ITR — Syntax + Business Rule Check

Source: Submit API spec, pages 4–12 

API_SubmitFlow_v1.1

Purpose

Before submitting, every ITR must pass:

Schema validation

Tax calculation checks

Form-specific consistency checks

API: validateItr
Request Body Requirements

A large JSON with two major parts:

Header

formName: ITR-1/2/3/4/…

formCode: numeric

entityNum: PAN

ay: Assessment Year

filingType (Original/Revised)

incomeTaxSecCd

submittedBy (ERI or SLF)

formData

Detailed ITR JSON strictly matching schema.

Response

Validation success/failure

Detailed error messages

No ARN generated yet (only on submit)

Product Design Implication

Your agent must:

Convert AI-generated user responses + prefill into exact schema-compliant JSON.

Handle error corrections interactively.

Re-submit until all errors resolve.

🚀 5. Submit ITR — Generate ARN

Source: Submit API spec, pages 12–14 

API_SubmitFlow_v1.1

Purpose

Once validation is passed → submit the same payload to submitItr.

Response

arnNumber (core identifier for that return)

successFlag

transactionNo

Product Design Implication

Your product should store:

ARN

Form type

PAN

Assessment Year

This is required for Acknowledgement and e-Verification APIs.

📄 6. Get Acknowledgement (PDF)

Source: Acknowledgement API, pages 3–7 

API_AcknowledgementFlow

Purpose

Download the ITR-V/Acknowledgement PDF after submission or e-verification completion.

API: getAcknowledgement
Inputs

PAN

ARN

serviceName = "EriGetAcknowledgement"

Response

Returns PDF in Base64 format

Product Design Implication

Convert Base64 → PDF file

Offer download within your dashboard

Store securely for audit/history

✔️ 7. e-Verify Return — Aadhaar OTP or EVC

Source: e-Verify Return API, pages 5–15 

API_Everify_Return_v1.1

Purpose

ITR is NOT complete until verified.

There are 3 APIs:
A. updateVerMode

Sets verification mode to:

LATER

ITR-V (offline)

Useful only if user doesn’t want to verify immediately.

B. generateEVC

Send PAN, AY, Mode (Aadhaar / Bank / Demat)

OTP/EVC goes to user

C. verifyEVC

Pass OTP/EVC + ARN + PAN

On success → Return becomes verified

Product Design Implication

Your agent should offer:

“Verify with Aadhaar OTP”

“Verify with Bank EVC”

“Verify later”

🧠 Putting It All Together: End-to-End Workflow

Below is the exact sequence your backend agent must automate:

Step 1 — Login

Get authToken.

Step 2 — Add Client

If first-time user:

addClient → sends OTP

validateClientOtp → confirms consent

If user already added → skip.

Step 3 — Fetch Prefill

requestPrefillOTP

getPrefill → AI now has full taxpayer data

Step 4 — AI-Assisted Return Preparation

Ask prompts to complete missing sections

Produce accurate tax computation

Build schema-compliant JSON

Step 5 — Validate ITR

validateItr

Fix errors if needed

Step 6 — Submit ITR

submitItr

Receive ARN

Step 7 — e-Verify

generateEVC

verifyEVC

Step 8 — Download ITR-V

getAcknowledgement → Base64 PDF → deliver to user

🏗️ Architectural Recommendations for Your ITR Agent
1. Modular Microservice Structure

auth-service

client-onboarding-service

prefill-service

itr-schema-engine

itr-validation-service

itr-submission-service

verification-service

acknowledgement-service

2. DSG/DSC Digital Signing Layer

Every API request requires:

Base64 encode JSON

Sign Base64 with DSC private key

Attach signature to sign parameter

You must implement a secure DSC signing module.

3. Strict Schema Validation

Use the Prefill Schema ZIP + form schema to:

Validate JSON locally before calling validateItr

Prevent round-trip latency

Avoid repeated API failures

4. Audit Logging (Non-negotiable for ERI Compliance)

Log:

Requests / Responses (hashed)

Consent timestamps

ARN history

Verification status

5. User Communication Layer

Your AI agent should:

Guide user through required inputs

Auto-explain errors coming from validateItr

Clarify missing deductions, income sources, etc.