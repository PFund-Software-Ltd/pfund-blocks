"""DRAFT: guideline for pfund-blocks' custom errors, nothing here is implemented yet.

Why
---
A trading caller must know what to do next after a failed request, and the most important
question is: did the request take effect?
    - rejected:  the venue answered and did NOT execute it, e.g. insufficient balance
    - unknown:   no definite answer, it MAY have been executed, e.g. a timeout after sending
A timeout on create_order looks exactly like "rejected" if both are just success=False + a string,
but the caller must react oppositely: after a rejection it may resend, after an unknown outcome
it must first query the order (e.g. by client order id), otherwise it may double the position.

Lesson from CCXT (errorHierarchy.ts): its RequestTimeout sits under NetworkError/OperationFailed
next to RateLimitExceeded, and fetch2() auto-retries every OperationFailed (maxRetriesOnFailure),
so a timed-out order can be sent twice. So the top-level split here is by outcome, not by cause.

Hierarchy
---------
PFundBlocksError
├── RejectedError                       the venue did NOT execute the request (definite)
│   ├── RetryableRejectedError          not executed, resending the same request later may succeed
│   │   ├── RateLimitedError            e.g. HTTP 429, Bybit 10006/10018, back off then resend
│   │   ├── VenueUnavailableError       the venue says it is down/in maintenance (explicit, NOT a bare 502/504)
│   │   └── InvalidNonceError           timestamp outside recv window / stale nonce, resync time then resend
│   ├── AuthenticationError             bad key/signature/IP, fix the config, never resend as is
│   │   └── PermissionDeniedError       valid key without the permission, e.g. no trading permission
│   ├── InvalidRequestError             the request itself is wrong (bad params/symbol), a bug on our side
│   │   └── NotSupportedError           the venue doesn't support it, e.g. an order type on that product
│   ├── OrderRejectedError              a valid order the venue refused for trading reasons
│   │   ├── InsufficientFundsError
│   │   ├── OrderSizeError              below min qty/notional, above max, wrong lot/tick size
│   │   ├── PostOnlyRejectedError       the post-only order would have crossed
│   │   └── ReduceOnlyRejectedError     the reduce-only order would increase the position
│   ├── OrderNotFoundError              cancel/amend/query of an unknown order, e.g. already filled or cancelled
│   └── SubscriptionRejectedError       WS: the venue rejected a subscription, e.g. an unknown channel
└── UnknownOutcomeError                 no definite answer, the request MAY have taken effect
    ├── RequestTimeoutError             sent, no response in time
    ├── ConnectionLostError             the connection dropped after (possibly) sending
    └── BadResponseError                an answer we can't interpret, e.g. HTTP 502/504 from a gateway, non-JSON body

NOTE: a connection that failed BEFORE anything was sent (e.g. DNS, connection refused) is a
RetryableRejectedError, not an UnknownOutcomeError, since the venue never saw the request.
NOTE: arguments rejected by pfund-blocks itself before sending (e.g. unsupported resolution,
account env mismatch) are NOT custom errors, they stay built-ins (ValueError, TypeError, KeyError).

How they are used (open)
------------------------
REST/WS APIs don't raise on venue or network errors, they return Reply/Message with success=False.
The intention is that the error class also becomes the error's kind in Reply/Message,
e.g. reply["error_type"] = OrderRejectedError (the class, not raised), so that
    - callers can branch with issubclass(reply["error_type"], UnknownOutcomeError)
    - callers that prefer exceptions can raise reply["error_type"](reply["error"])
Name and shape of that Reply/Message field are not decided yet.

Venue codes -> errors is data, not code: the venue's parser holds a table, like CCXT's
describe()["exceptions"]["exact"], e.g.
    error_codes = {10003: AuthenticationError, 10006: RateLimitedError, 110007: InsufficientFundsError}
An unmapped venue code falls back to the parent that is safe for its context
(RejectedError if the venue answered with an error code, UnknownOutcomeError otherwise).

Rules for adding a custom error
-------------------------------
1. Add a class only when a caller would handle it differently from its parent,
   otherwise raise/return the parent with a precise message.
2. Place it by outcome first (rejected vs unknown), then by what the caller does next.
3. When unsure whether the request took effect, it is UnknownOutcomeError, never RejectedError.
   Mistaking unknown for rejected can double an order, the opposite only costs one extra query.
4. Never venue-specific classes (no BybitError), the venue's code and message are attributes:
   source (e.g. "BYBIT"), code (the venue's error code, None if none) and the message.
5. Never for programming/argument errors, use built-ins (rule above).
6. Names end with "Error" and describe the situation, not the venue's wording,
   e.g. InsufficientFundsError, not "AbBalanceNotEnoughError".
"""
