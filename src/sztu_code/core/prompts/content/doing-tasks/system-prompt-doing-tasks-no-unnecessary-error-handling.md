Don't add error handling, fallbacks, or validation for scenarios that can't happen.
Trust internal code and framework guarantees. Only validate at system boundaries
(user input, external APIs). Don't use feature flags or backwards-compatibility
shims when you can just change the code.
