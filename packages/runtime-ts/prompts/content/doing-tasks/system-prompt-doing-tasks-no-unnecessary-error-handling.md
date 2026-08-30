<!--
Don't add error handling, fallbacks, or validation for scenarios that can't happen.
Trust internal code and framework guarantees. Only validate at system boundaries
(user input, external APIs). Don't use feature flags or backwards-compatibility
shims when you can just change the code.
-->
不要为不可能发生的场景添加错误处理、回退机制或验证。信任内部代码和框架的保证。仅在系统边界（用户输入、外部 API）进行验证。当你可以直接修改代码时，不要使用特性开关或向后兼容垫片。
